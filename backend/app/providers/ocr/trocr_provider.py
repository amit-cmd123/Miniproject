"""Handwriting recognition with TrOCR.

TrOCR is an encoder-decoder model: a vision transformer reads a *single line*
of handwriting and a text decoder generates characters one token at a time.
Line segmentation therefore happens before we get here (see
`services/preprocessing.py`); this provider only turns line images into text.

### Where the confidence number comes from

The decoder produces a probability distribution over the vocabulary at every
step. We take the log-probability of each token it actually chose, average
those across the line, and exponentiate - giving the geometric mean per-token
probability:

    confidence = exp( (1/N) * sum log P(token_i) )

This is a real measurement of how certain the decoder was, not a number the
model was asked to invent. It is still *not* a calibrated probability of being
correct - a confidently misread word scores high - which is exactly why Phase 3
has to measure calibration against ground truth before these numbers are
trusted operationally.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

from app.providers.ocr.base import (
    OCRProvider,
    ProviderInfo,
    RecognisedLine,
    RecognitionResult,
)

logger = logging.getLogger(__name__)

# Lines are processed in batches to keep CPU inference tolerable.
BATCH_SIZE = 8
MAX_NEW_TOKENS = 64
MIN_NEW_TOKENS = 16


def token_budget(box: tuple[int, int, int, int]) -> int:
    """Upper bound on tokens worth generating for one line.

    A line's width-to-height ratio bounds how many characters it can hold. On
    an unreadable crop the decoder does not stop - it repeats itself until it
    hits the limit ("0005000500050005..."), which made garbage lines the
    slowest lines on the page. Bounding the budget by what could physically
    fit costs nothing on real text and cuts those runaways short.
    """
    _, _, width, height = box
    aspect = width / max(height, 1)
    return int(min(MAX_NEW_TOKENS, max(MIN_NEW_TOKENS, aspect * 0.9 + 10)))


class TrOCRProvider(OCRProvider):
    name = "trocr"
    is_mock = False

    def __init__(
        self,
        model_name: str = "microsoft/trocr-small-handwritten",
        device: str = "auto",
    ) -> None:
        self._model_name = model_name
        self._requested_device = device
        self._device = "cpu"
        self._model = None
        self._processor = None
        self._load_error: str | None = None
        self._lock = threading.Lock()

    # -- loading -----------------------------------------------------------

    def _resolve_device(self) -> str:
        import torch

        if self._requested_device == "cpu":
            return "cpu"
        if self._requested_device == "cuda":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _ensure_loaded(self) -> None:
        """Load weights on first use.

        Deliberately lazy: importing torch and pulling ~1.4 GB of weights must
        not happen at application start, or the API would be unreachable for
        minutes after a deploy.
        """
        if self._model is not None or self._load_error is not None:
            return
        with self._lock:
            if self._model is not None or self._load_error is not None:
                return
            try:
                import torch
                from transformers import TrOCRProcessor, VisionEncoderDecoderModel

                self._device = self._resolve_device()
                logger.info(
                    "Loading %s on %s (first run downloads the weights)",
                    self._model_name,
                    self._device,
                )
                processor = TrOCRProcessor.from_pretrained(self._model_name)
                model = VisionEncoderDecoderModel.from_pretrained(self._model_name)
                model.to(self._device)
                model.eval()
                torch.set_grad_enabled(False)
                # int8 dynamic quantisation was measured and rejected: ~25%
                # faster, but character error rate rose from 2% to over 80%.

                self._processor = processor
                self._model = model
                logger.info("Handwriting model ready on %s", self._device)
            except Exception as exc:  # pragma: no cover - environment dependent
                self._load_error = str(exc)
                logger.exception("Could not load the handwriting model")

    def warmup(self) -> None:
        self._ensure_loaded()

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    # -- recognition -------------------------------------------------------

    def recognise(
        self,
        line_images: list[np.ndarray],
        boxes: list[tuple[int, int, int, int]],
    ) -> RecognitionResult:
        self._ensure_loaded()
        result = RecognitionResult()

        if self._model is None:
            raise RuntimeError(
                f"Handwriting model unavailable: {self._load_error or 'not loaded'}"
            )
        if not line_images:
            result.warnings.append("No handwriting lines were found in this image.")
            return result

        import torch
        from PIL import Image

        # A batch runs until its longest line finishes, so short lines batched
        # with long ones wait idle. Grouping lines of similar width keeps every
        # batch about as long as its members need; results are put back in
        # page order afterwards.
        order = sorted(range(len(line_images)), key=lambda i: token_budget(boxes[i]))
        recognised: dict[int, RecognisedLine] = {}

        for start in range(0, len(order), BATCH_SIZE):
            members = order[start : start + BATCH_SIZE]
            pil_images = [Image.fromarray(line_images[i]) for i in members]

            inputs = self._processor(images=pil_images, return_tensors="pt")
            pixel_values = inputs.pixel_values.to(self._device)

            with torch.inference_mode():
                generated = self._model.generate(
                    pixel_values,
                    max_new_tokens=max(token_budget(boxes[i]) for i in members),
                    num_beams=1,  # greedy keeps transition scores interpretable
                    output_scores=True,
                    return_dict_in_generate=True,
                )

            texts = self._processor.batch_decode(
                generated.sequences, skip_special_tokens=True
            )
            confidences = self._token_confidences(generated)

            for index, text, confidence in zip(members, texts, confidences):
                recognised[index] = RecognisedLine(
                    index=index,
                    text=text.strip(),
                    confidence=confidence,
                    bbox=boxes[index],
                )

        result.lines = [recognised[i] for i in range(len(line_images))]
        return result

    def _token_confidences(self, generated) -> list[float]:
        """Geometric mean of per-token probabilities, one value per line."""
        import torch

        try:
            transition_scores = self._model.compute_transition_scores(
                generated.sequences, generated.scores, normalize_logits=True
            )
        except Exception:  # pragma: no cover - defensive
            logger.warning("Transition scores unavailable; falling back to a flat value")
            return [0.5] * generated.sequences.shape[0]

        # sequences carries the decoder-start token at position 0; the scores
        # line up with everything after it.
        tokens = generated.sequences[:, 1:]
        pad_id = self._model.config.decoder.pad_token_id
        mask = tokens != pad_id if pad_id is not None else torch.ones_like(tokens).bool()

        confidences: list[float] = []
        for row in range(transition_scores.shape[0]):
            valid = mask[row][: transition_scores.shape[1]]
            scores = transition_scores[row][: valid.shape[0]][valid]
            scores = scores[torch.isfinite(scores)]
            if scores.numel() == 0:
                confidences.append(0.0)
                continue
            confidences.append(round(float(scores.mean().exp().clamp(0.0, 1.0)), 4))
        return confidences

    # -- description -------------------------------------------------------

    def info(self) -> ProviderInfo:
        if self._model is not None:
            detail = "Handwriting model loaded and ready."
        elif self._load_error:
            detail = f"Model could not be loaded: {self._load_error}"
        else:
            detail = "Model not loaded yet; it loads on the first transcription."
        return ProviderInfo(
            name=self.name,
            model_name=self._model_name,
            model_version=self._model_name.split("/")[-1],
            device=self._device,
            is_ready=self.is_ready,
            is_mock=False,
            detail=detail,
        )
