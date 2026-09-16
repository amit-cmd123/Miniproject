"""Tests for confidence composition, banding, and the transcription API.

These run against the mock recognition engine, so they are fast and need no
model download - which is the reason the mock exists.
"""

from __future__ import annotations

import io
import unittest

import numpy as np
from PIL import Image

from app.core.thresholds import classify_transcription
from app.providers.ocr.base import RecognisedLine, RecognitionResult
from app.providers.ocr.mock_provider import MockOCRProvider
from app.schemas.enums import TranscriptionBand
from app.services.ocr_service import _page_confidence


def lines(*pairs: tuple[str, float]) -> RecognitionResult:
    result = RecognitionResult()
    for index, (text, confidence) in enumerate(pairs):
        result.lines.append(
            RecognisedLine(index=index, text=text, confidence=confidence, bbox=(0, 0, 10, 10))
        )
    return result


class PageConfidenceTests(unittest.TestCase):
    SHARP = 1000.0  # well above the blur threshold, so no penalty applies

    def test_single_line_passes_through(self) -> None:
        value, _ = _page_confidence(lines(("hello world", 0.9)), self.SHARP)
        self.assertAlmostEqual(value, 0.9, places=3)

    def test_longer_lines_carry_more_weight(self) -> None:
        # A confident two-character line should not rescue a long hesitant one.
        value, _ = _page_confidence(
            lines(("a" * 100, 0.60), ("ab", 1.00)), self.SHARP
        )
        self.assertLess(value, 0.70)

    def test_empty_transcription_scores_zero(self) -> None:
        value, signals = _page_confidence(lines(("", 0.99), ("   ", 0.99)), self.SHARP)
        self.assertEqual(value, 0.0)
        self.assertEqual(signals["lines_considered"], 0)

    def test_no_lines_at_all_scores_zero(self) -> None:
        self.assertEqual(_page_confidence(RecognitionResult(), self.SHARP)[0], 0.0)

    def test_a_soft_image_reduces_confidence(self) -> None:
        sharp, _ = _page_confidence(lines(("some text here", 0.95)), self.SHARP)
        soft, signals = _page_confidence(lines(("some text here", 0.95)), 10.0)
        self.assertLess(soft, sharp)
        self.assertLess(signals["sharpness_penalty"], 1.0)

    def test_result_is_always_in_range(self) -> None:
        for confidence in (0.0, 0.5, 1.0):
            value, _ = _page_confidence(lines(("text", confidence)), 5.0)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_signals_are_reported(self) -> None:
        _, signals = _page_confidence(lines(("abc", 0.8)), self.SHARP)
        self.assertIn("weighted_line_mean", signals)
        self.assertIn("sharpness_penalty", signals)
        self.assertIn("lines_considered", signals)


class BandingTests(unittest.TestCase):
    def test_each_band_is_reachable(self) -> None:
        cases = [
            (0.99, TranscriptionBand.RELIABLE),
            (0.95, TranscriptionBand.RELIABLE),
            (0.90, TranscriptionBand.SPOT_CHECK),
            (0.85, TranscriptionBand.SPOT_CHECK),
            (0.80, TranscriptionBand.VERIFY),
            (0.70, TranscriptionBand.VERIFY),
            (0.40, TranscriptionBand.UNUSABLE),
            (0.00, TranscriptionBand.UNUSABLE),
        ]
        for confidence, expected in cases:
            with self.subTest(confidence=confidence):
                self.assertEqual(classify_transcription(confidence).band, expected)

    def test_bands_never_gap(self) -> None:
        for step in range(0, 101):
            self.assertIsNotNone(classify_transcription(step / 100).label)


class MockProviderTests(unittest.TestCase):
    def test_returns_one_line_per_image(self) -> None:
        images = [np.full((48, 200, 3), 200, dtype=np.uint8) for _ in range(4)]
        boxes = [(0, i * 50, 200, 48) for i in range(4)]
        result = MockOCRProvider().recognise(images, boxes)
        self.assertEqual(len(result.lines), 4)

    def test_output_is_deterministic(self) -> None:
        images = [np.full((48, 200, 3), 123, dtype=np.uint8)]
        boxes = [(0, 0, 200, 48)]
        first = MockOCRProvider().recognise(images, boxes)
        second = MockOCRProvider().recognise(images, boxes)
        self.assertEqual(first.text, second.text)
        self.assertEqual(first.lines[0].confidence, second.lines[0].confidence)

    def test_it_says_that_it_is_a_mock(self) -> None:
        info = MockOCRProvider().info()
        self.assertTrue(info.is_mock)
        result = MockOCRProvider().recognise([], [])
        self.assertTrue(any("Mock" in w for w in result.warnings))

    def test_confidence_stays_in_range(self) -> None:
        images = [np.random.default_rng(i).integers(0, 255, (48, 200, 3), dtype=np.uint8)
                  for i in range(6)]
        boxes = [(0, 0, 200, 48)] * 6
        for line in MockOCRProvider().recognise(images, boxes).lines:
            self.assertGreaterEqual(line.confidence, 0.0)
            self.assertLessEqual(line.confidence, 1.0)


class ApiTests(unittest.TestCase):
    """End-to-end through the HTTP layer, using the mock engine."""

    @classmethod
    def setUpClass(cls) -> None:
        import os
        import tempfile

        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["EVALNOVA_OCR_PROVIDER"] = "mock"
        os.environ["EVALNOVA_DATABASE_URL"] = f"sqlite:///{cls._tmp.name}/test.db"
        os.environ["EVALNOVA_STORAGE_DIR"] = cls._tmp.name

        from app.core.config import get_settings

        get_settings.cache_clear()

        from fastapi.testclient import TestClient

        from app.db.session import init_db
        from app.main import app

        init_db()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        # Windows will not delete a file SQLAlchemy still holds open, so the
        # connection pool has to go first.
        from app.db.session import engine

        engine.dispose()
        try:
            cls._tmp.cleanup()
        except OSError:
            pass  # a stray lock must not fail an otherwise passing run

    @staticmethod
    def png_bytes(width: int = 1200, height: int = 400, lines: int = 3) -> bytes:
        """A page with real rendered glyphs.

        Solid filled rectangles are not a valid stand-in for text: adaptive
        thresholding compares each pixel to its local mean, so the interior of
        a large solid block matches its surroundings and only the block's edges
        survive. Stroked characters are what the pipeline is built for.
        """
        import cv2

        array = np.full((height, width, 3), 245, dtype=np.uint8)
        for i in range(lines):
            cv2.putText(
                array,
                "the quick brown fox jumps over the lazy dog",
                (60, 90 + i * 95),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.1,
                (30, 30, 30),
                2,
                cv2.LINE_AA,
            )
        buffer = io.BytesIO()
        Image.fromarray(array).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_health(self) -> None:
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_upload_and_transcribe(self) -> None:
        response = self.client.post(
            "/api/v1/answers/transcribe",
            files={"file": ("answer.png", self.png_bytes(), "image/png")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["answer"]["status"], "ocr_done")

        ocr = body["ocr"]
        self.assertGreater(len(ocr["extracted_text"]), 0)
        self.assertGreaterEqual(ocr["confidence"], 0.0)
        self.assertLessEqual(ocr["confidence"], 1.0)
        self.assertIn(ocr["transcription_band"], {b.value for b in TranscriptionBand})
        self.assertEqual(ocr["text_source"], "machine")
        self.assertEqual(len(ocr["lines"]), ocr["line_count"])

    def test_printed_cover_page_is_skipped_and_says_why(self) -> None:
        import cv2

        page = np.full((1100, 1400, 3), 240, dtype=np.uint8)
        for i in range(14):
            cv2.putText(page, "INSTRUCTIONS TO THE CANDIDATES", (60, 60 + i * 75),
                        cv2.FONT_HERSHEY_DUPLEX, 1.4, (40, 120, 240), 3, cv2.LINE_AA)
        buffer = io.BytesIO()
        Image.fromarray(page[:, :, ::-1]).save(buffer, format="PNG")

        response = self.client.post(
            "/api/v1/answers/transcribe",
            files={"file": ("cover.png", buffer.getvalue(), "image/png")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        ocr = response.json()["ocr"]
        self.assertEqual(ocr["line_count"], 0)
        self.assertEqual(ocr["preprocessing"]["page_kind"], "printed_form")
        self.assertTrue(any("cover or form page" in w for w in ocr["warnings"]))

    def test_non_image_is_rejected_with_advice(self) -> None:
        response = self.client.post(
            "/api/v1/answers/transcribe",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not a supported image type", response.json()["detail"])

    def test_empty_file_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/answers/transcribe",
            files={"file": ("empty.png", b"", "image/png")},
        )
        self.assertEqual(response.status_code, 400)

    def test_corrupt_image_fails_loudly(self) -> None:
        """A broken file must error, never yield a plausible empty transcription."""
        response = self.client.post(
            "/api/v1/answers/transcribe",
            files={"file": ("broken.png", b"\x89PNG\r\n\x1a\n garbage", "image/png")},
        )
        self.assertEqual(response.status_code, 422)

    def test_correction_preserves_the_machine_output(self) -> None:
        created = self.client.post(
            "/api/v1/answers/transcribe",
            files={"file": ("answer.png", self.png_bytes(), "image/png")},
        ).json()
        answer_id = created["answer"]["id"]
        original = created["ocr"]["extracted_text"]

        response = self.client.patch(
            f"/api/v1/answers/{answer_id}/ocr/verify",
            json={"corrected_text": "what the student really wrote"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["extracted_text"], original)  # untouched
        self.assertEqual(body["corrected_text"], "what the student really wrote")
        self.assertEqual(body["effective_text"], "what the student really wrote")
        self.assertEqual(body["text_source"], "human_corrected")
        self.assertFalse(body["needs_verification"])

    def test_accuracy_scores_a_perfect_match_at_zero(self) -> None:
        created = self.client.post(
            "/api/v1/answers/transcribe",
            files={"file": ("answer.png", self.png_bytes(), "image/png")},
        ).json()
        answer_id = created["answer"]["id"]

        response = self.client.post(
            f"/api/v1/answers/{answer_id}/ocr/accuracy",
            json={"reference_text": created["ocr"]["extracted_text"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["character_error_rate"], 0.0)
        self.assertEqual(response.json()["word_error_rate"], 0.0)

    def test_accuracy_compares_against_the_machine_not_the_correction(self) -> None:
        created = self.client.post(
            "/api/v1/answers/transcribe",
            files={"file": ("answer.png", self.png_bytes(), "image/png")},
        ).json()
        answer_id = created["answer"]["id"]
        self.client.patch(
            f"/api/v1/answers/{answer_id}/ocr/verify",
            json={"corrected_text": "totally different words entirely"},
        )
        response = self.client.post(
            f"/api/v1/answers/{answer_id}/ocr/accuracy",
            json={"reference_text": "totally different words entirely"},
        )
        # If it compared against the correction this would be 0.0.
        self.assertGreater(response.json()["character_error_rate"], 0.0)
        self.assertEqual(response.json()["compared_against"], "machine_transcription")

    def test_unknown_answer_is_404(self) -> None:
        self.assertEqual(self.client.get("/api/v1/answers/nope").status_code, 404)

    def test_planned_endpoints_name_their_workstream(self) -> None:
        response = self.client.post("/api/v1/evaluations")
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["detail"]["workstream"], "Part 3")

    def test_thresholds_are_served_not_hard_coded(self) -> None:
        body = self.client.get("/api/v1/config/thresholds").json()
        self.assertEqual(len(body["transcription"]), 4)
        self.assertEqual(len(body["evaluation"]), 4)


if __name__ == "__main__":
    unittest.main()
