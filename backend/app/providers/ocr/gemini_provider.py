"""Handwriting recognition with a Gemini vision-language model.

TrOCR reads one segmented line at a time and was trained on Western English
cursive. Real answer booklets defeat that: stacked fractions, exponents, Indian
handwriting, ruled paper. A vision-language model reads the whole page at once,
does its own layout analysis, and handles all of these far better - at the cost
of sending the page to Google. That trade is a configuration decision
(`EVALNOVA_OCR_PROVIDER=gemini`), never a default.

Called over plain REST with httpx, so there is no vendor SDK to install and the
request is visible in full here.

### Where the confidence number comes from

Asking the model how sure it is gives a number that means little. Two measured
signals are used instead, in order of preference:

1. **Token probability.** When the API returns log-probabilities for the tokens
   it generated, each line's confidence is the geometric mean probability of
   its tokens - the same measure TrOCR uses, so the two engines' numbers are
   comparable.
2. **Self-consistency.** Not every model and API version returns
   log-probabilities. Then the page is read a second time with sampling
   switched on, and each line's confidence is how closely the two independent
   readings agree. A line the model reads identically twice is one it can
   actually see; a line it reads two different ways is one it is guessing at.

The method used is recorded with every result.
"""

from __future__ import annotations

import base64
import difflib
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from app.providers.ocr.base import (
    OCRProvider,
    ProviderInfo,
    RecognisedLine,
    RecognitionResult,
)

logger = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
NO_HANDWRITING = "NO_HANDWRITING"
# Long side of the image sent. Past this, detail stops helping and upload and
# image tokens keep growing.
MAX_IMAGE_SIDE = 2400
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

PROMPT_VERSION = "ocr-page-v1"
INSTRUCTIONS = """You transcribe photographed pages of handwritten university examination answer booklets.

Transcribe ONLY the student's handwriting, exactly as written, top to bottom, one output line per handwritten line.

Rules:
- Copy the student's words, spelling, grammar and mistakes exactly. Never correct, complete, summarise or explain.
- Ignore: printed text and printed form labels; ruling lines and margins; the examiner's marks (red ticks, circles, crosses, scores, remarks); faint mirror-image writing showing through from the back of the paper.
- Leave out anything the student has struck through.
- Mathematics goes on one line in plain text: exponents with ^ (4 X 10^3), fractions as (numerator)/(denominator), symbols such as =, +, X, ≈, ∴ only where written.
- A word you cannot read becomes [illegible]. A drawn diagram becomes [diagram].
- Output the transcription only: no preamble, no commentary, no markdown, no code fences.
- If the page holds no student handwriting at all, output exactly: NO_HANDWRITING"""


class GeminiError(RuntimeError):
    """The request failed in a way retrying will not fix."""


def _encode_jpeg(page: np.ndarray) -> str:
    import cv2

    height, width = page.shape[:2]
    scale = min(1.0, MAX_IMAGE_SIDE / max(height, width))
    if scale < 1.0:
        page = cv2.resize(
            page, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA
        )
    ok, buffer = cv2.imencode(".jpg", page, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:  # pragma: no cover - defensive
        raise GeminiError("The page image could not be encoded for upload.")
    return base64.b64encode(buffer.tobytes()).decode("ascii")


def split_lines(text: str) -> list[str]:
    """The model's reply as clean transcription lines."""
    cleaned = text.replace("\r\n", "\n").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
    lines = [line.strip() for line in cleaned.split("\n")]
    lines = [line for line in lines if line]
    if len(lines) == 1 and lines[0].strip(". ") == NO_HANDWRITING:
        return []
    return lines


def line_confidences_from_logprobs(
    text: str, tokens: list[tuple[str, float]]
) -> list[float] | None:
    """Geometric-mean token probability for each non-empty line of `text`.

    Tokens are walked in order and attributed to the line their characters fall
    in; a token spanning a line break counts towards the line it starts in.
    Returns None when the tokens do not reassemble into the text, rather than
    guessing an alignment.
    """
    if not tokens:
        return None
    joined = "".join(token for token, _ in tokens)
    offset = joined.find(text.strip()[:20]) if text.strip() else 0
    if offset < 0:
        return None

    per_line: list[list[float]] = [[]]
    position = 0
    for token, logprob in tokens:
        start = position
        position += len(token)
        if start < offset:
            continue
        # A token such as "\nFrame" belongs to the line it opens, not the one
        # it closes.
        leading = len(token) - len(token.lstrip("\r\n"))
        for _ in range(token[:leading].count("\n")):
            per_line.append([])
        if token.strip() and math.isfinite(logprob):
            per_line[-1].append(logprob)
        for _ in range(token[leading:].count("\n")):
            per_line.append([])

    raw_lines = text.replace("\r\n", "\n").strip().split("\n")
    kept: list[float] = []
    for index, raw in enumerate(raw_lines):
        if not raw.strip():
            continue
        values = per_line[index] if index < len(per_line) else []
        if not values:
            return None
        kept.append(round(float(min(1.0, math.exp(sum(values) / len(values)))), 4))
    return kept


def line_confidences_from_agreement(
    primary: list[str], second: list[str]
) -> list[float]:
    """How closely a second, independent reading reproduces each line.

    Each primary line is compared with the second reading's lines near the same
    position (readings can differ by a line or two when one splits a line the
    other joins), and scored by its best character-level similarity.
    """
    if not second:
        return [0.0] * len(primary)
    scores: list[float] = []
    for index, line in enumerate(primary):
        centre = round(index * len(second) / max(len(primary), 1))
        window = second[max(0, centre - 3) : centre + 4] or second
        best = max(
            difflib.SequenceMatcher(None, line.lower(), other.lower()).ratio()
            for other in window
        )
        scores.append(round(float(best), 4))
    return scores


class GeminiOCRProvider(OCRProvider):
    name = "gemini"
    is_mock = False
    reads_full_page = True

    def __init__(
        self,
        api_key: str | None,
        model: str = "gemini-3.5-flash",
        timeout_seconds: float = 90.0,
        thinking_level: str | None = "low",
    ) -> None:
        self._api_key = (api_key or "").strip() or None
        self._model = model
        self._timeout = timeout_seconds
        self._thinking_level = thinking_level
        # Optional request features are switched off for the rest of the
        # session the first time the API rejects them.
        self._logprobs_supported: bool | None = None
        self._thinking_supported = bool(thinking_level)

    # -- the request -------------------------------------------------------

    def _body(self, image_b64: str, temperature: float, logprobs: bool) -> dict:
        config: dict = {"temperature": temperature, "maxOutputTokens": 8192}
        if logprobs:
            config["responseLogprobs"] = True
        if self._thinking_supported and self._thinking_level:
            config["thinkingConfig"] = {"thinkingLevel": self._thinking_level}
        return {
            "systemInstruction": {"parts": [{"text": INSTRUCTIONS}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
                        {"text": "Transcribe the student's handwriting on this page."},
                    ],
                }
            ],
            "generationConfig": config,
        }

    def _post(self, body: dict) -> dict:
        import httpx

        url = f"{API_ROOT}/{self._model}:generateContent"
        headers = {"x-goog-api-key": self._api_key or "", "Content-Type": "application/json"}
        delay = 2.0
        for attempt in range(3):
            try:
                response = httpx.post(url, json=body, headers=headers, timeout=self._timeout)
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise GeminiError(f"Could not reach Gemini: {exc}") from exc
                time.sleep(delay)
                delay *= 2
                continue
            if response.status_code == 200:
                return response.json()
            message = _error_message(response)
            if response.status_code in RETRYABLE_STATUS and attempt < 2:
                logger.warning("Gemini returned %s (%s); retrying", response.status_code, message)
                time.sleep(delay)
                delay *= 2
                continue
            raise GeminiError(_explain(response.status_code, message, self._model))
        raise GeminiError("Gemini did not respond.")  # pragma: no cover

    def _read(self, image_b64: str, temperature: float, want_logprobs: bool) -> dict:
        """One reading, shedding optional features the API refuses."""
        logprobs = want_logprobs and self._logprobs_supported is not False
        while True:
            try:
                return self._post(self._body(image_b64, temperature, logprobs))
            except GeminiError as exc:
                text = str(exc).lower()
                if logprobs and "logprob" in text:
                    logger.info("Gemini model %s does not return logprobs", self._model)
                    self._logprobs_supported = False
                    logprobs = False
                    continue
                if self._thinking_supported and "thinking" in text:
                    logger.info("Gemini model %s rejects thinkingConfig", self._model)
                    self._thinking_supported = False
                    continue
                raise

    # -- recognition -------------------------------------------------------

    def recognise(self, line_images, boxes) -> RecognitionResult:
        raise GeminiError(
            "The Gemini engine reads whole pages; call recognise_page instead."
        )

    def recognise_page(self, page, line_images, boxes) -> RecognitionResult:
        if not self._api_key:
            raise GeminiError("No Gemini API key is configured.")

        image_b64 = _encode_jpeg(page)
        second_future = None
        pool = None
        if self._logprobs_supported is False:
            # Already known: confidence must come from a second reading, so
            # start it now and let both requests run at the same time.
            pool = ThreadPoolExecutor(max_workers=1)
            second_future = pool.submit(self._read, image_b64, 1.0, False)

        try:
            reply = self._read(image_b64, 0.0, True)
            text, tokens = _parse(reply)
            lines = split_lines(text)
            result = RecognitionResult(engine=self.info())

            confidences = None
            if lines and tokens:
                confidences = line_confidences_from_logprobs(text, tokens)
                if confidences is not None:
                    self._logprobs_supported = True
            if lines and confidences is None:
                if second_future is None:
                    pool = ThreadPoolExecutor(max_workers=1)
                    second_future = pool.submit(self._read, image_b64, 1.0, False)
                try:
                    second_text, _ = _parse(second_future.result())
                    confidences = line_confidences_from_agreement(
                        lines, split_lines(second_text)
                    )
                    result.confidence_method = "self_consistency"
                except GeminiError as exc:
                    logger.warning("Second Gemini reading failed: %s", exc)
                    confidences = [0.5] * len(lines)
                    result.confidence_method = "unmeasured"
                    result.warnings.append(
                        "Confidence could not be measured for this page (the "
                        "second reading failed), so it is shown as 50%. Check "
                        "the text by eye."
                    )
        finally:
            if pool is not None:
                pool.shutdown(wait=False, cancel_futures=True)

        for index, (line, confidence) in enumerate(zip(lines, confidences or [])):
            result.lines.append(
                RecognisedLine(index=index, text=line, confidence=confidence, bbox=(0, 0, 0, 0))
            )
        if not lines:
            result.warnings.append("Gemini found no student handwriting on this page.")
        return result

    # -- description -------------------------------------------------------

    def info(self) -> ProviderInfo:
        if not self._api_key:
            detail = "No Gemini API key set. Add EVALNOVA_GEMINI_API_KEY to .env."
        else:
            detail = (
                f"Cloud handwriting recognition with {self._model}. Page images "
                "are sent to Google."
            )
        return ProviderInfo(
            name=self.name,
            model_name=self._model,
            model_version=f"{self._model}/{PROMPT_VERSION}",
            device="cloud",
            is_ready=bool(self._api_key),
            is_mock=False,
            detail=detail,
        )


def _parse(reply: dict) -> tuple[str, list[tuple[str, float]]]:
    """Transcription text and (token, logprob) pairs from a generateContent reply."""
    feedback = reply.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise GeminiError(f"Gemini refused the page ({feedback['blockReason']}).")
    candidates = reply.get("candidates") or []
    if not candidates:
        raise GeminiError("Gemini returned no transcription.")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
    finish = candidate.get("finishReason")
    if finish not in (None, "STOP", "MAX_TOKENS") and not text.strip():
        raise GeminiError(f"Gemini stopped without a transcription ({finish}).")

    tokens = [
        (item.get("token", ""), float(item.get("logProbability", float("nan"))))
        for item in (candidate.get("logprobsResult") or {}).get("chosenCandidates") or []
    ]
    return text, tokens


def _error_message(response) -> str:
    try:
        return str(response.json().get("error", {}).get("message", "")) or response.text[:300]
    except Exception:
        return response.text[:300]


def _explain(status: int, message: str, model: str) -> str:
    if status in (401, 403):
        return f"Gemini rejected the API key ({status}): {message}"
    if status == 404:
        return (
            f"Gemini model '{model}' is not available to this key: {message}. "
            "Set EVALNOVA_GEMINI_MODEL to a model your key can use."
        )
    if status == 429:
        return f"Gemini rate limit or quota reached: {message}"
    return f"Gemini request failed ({status}): {message}"
