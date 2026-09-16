"""Tests for the Gemini page-level engine, the local fallback, and page handling.

No network: `httpx.post` is replaced with canned replies shaped like the
generateContent REST response.
"""

from __future__ import annotations

import unittest
from unittest import mock

import cv2
import numpy as np

from app.providers.ocr.base import OCRProvider, ProviderInfo, RecognisedLine, RecognitionResult
from app.providers.ocr.fallback import FallbackOCRProvider
from app.providers.ocr.gemini_provider import (
    GeminiError,
    GeminiOCRProvider,
    line_confidences_from_agreement,
    line_confidences_from_logprobs,
    split_lines,
)
from app.services.preprocessing import PAGE_HANDWRITING, PAGE_PRINTED_FORM, preprocess


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def reply(text: str, tokens: list[tuple[str, float]] | None = None) -> FakeResponse:
    candidate: dict = {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
    if tokens is not None:
        candidate["logprobsResult"] = {
            "chosenCandidates": [{"token": t, "logProbability": lp} for t, lp in tokens]
        }
    return FakeResponse(200, {"candidates": [candidate]})


def error(status: int, message: str) -> FakeResponse:
    return FakeResponse(status, {"error": {"code": status, "message": message}})


PAGE = np.full((400, 300, 3), 250, dtype=np.uint8)


class ParsingTests(unittest.TestCase):
    def test_blank_lines_and_fences_are_dropped(self) -> None:
        self.assertEqual(split_lines("```\nGiven:\n\nBit Rate = 4 kbps\n```"), ["Given:", "Bit Rate = 4 kbps"])

    def test_no_handwriting_sentinel_means_no_lines(self) -> None:
        self.assertEqual(split_lines("NO_HANDWRITING"), [])

    def test_logprobs_are_attributed_to_their_lines(self) -> None:
        tokens = [("To", -0.01), (" Find", -0.01), ("\n", -0.0), ("Frame", -2.0), (" Size", -2.0)]
        confidences = line_confidences_from_logprobs("To Find\nFrame Size", tokens)
        self.assertEqual(len(confidences), 2)
        self.assertGreater(confidences[0], 0.95)
        self.assertLess(confidences[1], 0.2)

    def test_a_token_opening_a_line_counts_for_that_line(self) -> None:
        tokens = [("sure", -0.0), ("\nguess", -3.0)]
        confidences = line_confidences_from_logprobs("sure\nguess", tokens)
        self.assertGreater(confidences[0], 0.99)
        self.assertLess(confidences[1], 0.1)

    def test_misaligned_tokens_give_no_answer_rather_than_a_guess(self) -> None:
        self.assertIsNone(line_confidences_from_logprobs("abc\ndef", [("abc", -0.1)]))

    def test_agreement_rewards_identical_readings(self) -> None:
        scores = line_confidences_from_agreement(
            ["Propagation delay = 20ms", "Efficiency = 50%"],
            ["Propagation delay = 20ms", "Effiuency = 30%"],
        )
        self.assertEqual(scores[0], 1.0)
        self.assertLess(scores[1], 0.95)

    def test_agreement_with_nothing_is_zero(self) -> None:
        self.assertEqual(line_confidences_from_agreement(["a"], []), [0.0])


class GeminiProviderTests(unittest.TestCase):
    def provider(self) -> GeminiOCRProvider:
        return GeminiOCRProvider(api_key="test-key", model="gemini-test")

    def test_reads_lines_with_token_confidence(self) -> None:
        text = "Given: Propagation delay = 20ms\nBit Rate = 4 kbps"
        tokens = [("Given: Propagation delay = 20ms", -0.02), ("\n", 0.0), ("Bit Rate = 4 kbps", -0.3)]
        with mock.patch("httpx.post", return_value=reply(text, tokens)) as post:
            result = self.provider().recognise_page(PAGE, [], [])
        self.assertEqual([line.text for line in result.lines], text.split("\n"))
        self.assertEqual(result.confidence_method, "token_probability")
        self.assertGreater(result.lines[0].confidence, result.lines[1].confidence)
        body = post.call_args.kwargs["json"]
        self.assertTrue(body["generationConfig"]["responseLogprobs"])
        self.assertEqual(body["generationConfig"]["temperature"], 0.0)
        # The key travels in a header, never in the URL where it could be logged.
        self.assertNotIn("test-key", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "test-key")

    def test_falls_back_to_self_consistency_without_logprobs(self) -> None:
        replies = [
            error(400, "Logprobs is not enabled for models/gemini-test"),
            reply("Frame Size = 80 Kb\nAns: 80 X 10^3 bits"),
            reply("Frame Size = 80 Kb\nAns: 80 X 10^8 bits"),
        ]
        provider = self.provider()
        with mock.patch("httpx.post", side_effect=replies):
            result = provider.recognise_page(PAGE, [], [])
        self.assertEqual(result.confidence_method, "self_consistency")
        self.assertEqual(result.lines[0].confidence, 1.0)
        self.assertLess(result.lines[1].confidence, 1.0)
        self.assertFalse(provider._logprobs_supported)

    def test_rejected_thinking_config_is_dropped_and_retried(self) -> None:
        replies = [error(400, "thinkingConfig is not supported"), reply("x = 1", [("x = 1", -0.1)])]
        with mock.patch("httpx.post", side_effect=replies) as post:
            result = self.provider().recognise_page(PAGE, [], [])
        self.assertEqual(result.lines[0].text, "x = 1")
        self.assertNotIn("thinkingConfig", post.call_args.kwargs["json"]["generationConfig"])

    def test_transient_errors_are_retried(self) -> None:
        replies = [error(503, "overloaded"), reply("ok", [("ok", -0.1)])]
        with mock.patch("httpx.post", side_effect=replies), mock.patch("time.sleep"):
            result = self.provider().recognise_page(PAGE, [], [])
        self.assertEqual(result.lines[0].text, "ok")

    def test_bad_key_fails_loudly(self) -> None:
        with mock.patch("httpx.post", return_value=error(403, "API key not valid")):
            with self.assertRaises(GeminiError) as caught:
                self.provider().recognise_page(PAGE, [], [])
        self.assertIn("API key", str(caught.exception))

    def test_blank_page(self) -> None:
        with mock.patch("httpx.post", return_value=reply("NO_HANDWRITING", [("NO_HANDWRITING", -0.01)])):
            result = self.provider().recognise_page(PAGE, [], [])
        self.assertEqual(result.lines, [])
        self.assertTrue(result.warnings)

    def test_without_a_key_it_is_not_ready(self) -> None:
        info = GeminiOCRProvider(api_key=None).info()
        self.assertFalse(info.is_ready)
        self.assertEqual(info.device, "cloud")


class StubLocal(OCRProvider):
    name = "stub-local"

    def recognise(self, line_images, boxes) -> RecognitionResult:
        return RecognitionResult(
            lines=[RecognisedLine(i, "local", 0.8, box) for i, box in enumerate(boxes)]
        )

    def info(self) -> ProviderInfo:
        return ProviderInfo("stub-local", "stub", "1", "cpu", True, False, "")


class FallbackTests(unittest.TestCase):
    def test_cloud_failure_is_read_locally_and_says_so(self) -> None:
        cloud = GeminiOCRProvider(api_key="k")
        provider = FallbackOCRProvider(cloud, StubLocal)
        with mock.patch("httpx.post", return_value=error(403, "API key not valid")):
            result = provider.recognise_page(PAGE, [PAGE], [(0, 0, 10, 10)])
        self.assertEqual(result.lines[0].text, "local")
        self.assertEqual(result.engine.name, "stub-local")
        self.assertIn("local engine", result.warnings[0])

    def test_local_engine_is_not_built_until_needed(self) -> None:
        factory = mock.Mock(side_effect=StubLocal)
        cloud = GeminiOCRProvider(api_key="k")
        provider = FallbackOCRProvider(cloud, factory)
        with mock.patch("httpx.post", return_value=reply("fine", [("fine", -0.1)])):
            provider.recognise_page(PAGE, [], [])
        factory.assert_not_called()


def ruled_page(ink=(150, 60, 20), print_colour=None) -> np.ndarray:
    """Blue handwriting-like text on ruled paper, optionally with coloured print."""
    page = np.full((1100, 1400, 3), 235, dtype=np.uint8)
    for y in range(80, 1100, 60):
        cv2.line(page, (0, y), (1399, y), (90, 90, 90), 2)
    cv2.line(page, (100, 0), (100, 1099), (90, 90, 90), 2)
    for i in range(6):
        cv2.putText(page, "the quick brown fox jumps", (140, 130 + i * 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.3, ink, 3, cv2.LINE_AA)
    if print_colour is not None:
        for i in range(14):
            cv2.putText(page, "INSTRUCTIONS TO THE CANDIDATES", (60, 60 + i * 75),
                        cv2.FONT_HERSHEY_DUPLEX, 1.4, print_colour, 3, cv2.LINE_AA)
    return page


class RealPageTests(unittest.TestCase):
    def test_ruling_is_not_mistaken_for_lines_of_writing(self) -> None:
        clean, boxes, report = preprocess(ruled_page())
        self.assertEqual(len(boxes), 6)
        self.assertTrue(report.ruling_removed)
        # No box should run the full width of the page the way a rule does.
        self.assertTrue(all(w < 1300 for _, _, w, _ in boxes))

    def test_orange_printed_cover_page_is_recognised(self) -> None:
        _, _, report = preprocess(ruled_page(print_colour=(40, 120, 240)))
        self.assertEqual(report.page_kind, PAGE_PRINTED_FORM)

    def test_answer_page_is_not_mistaken_for_a_form(self) -> None:
        _, _, report = preprocess(ruled_page())
        self.assertEqual(report.page_kind, PAGE_HANDWRITING)


if __name__ == "__main__":
    unittest.main()
