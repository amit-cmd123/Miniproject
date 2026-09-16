"""Transcription orchestration.

Sits between the API and the recognition provider. Owns everything the
provider must not know about: preprocessing, how a page-level confidence is
composed from line-level ones, trust banding, persistence and audit.

### How page confidence is composed

A page is not the average of its lines. A confident two-word line should not
outweigh a hesitant thirty-word one, and a blurred photograph should drag the
whole page down even if the decoder sounds sure of itself. So:

    page = (length-weighted mean of line confidences) x sharpness_penalty

and the result is floored at zero when nothing legible came back. The
components are stored alongside the result so Phase 3 can see which one was
responsible when a confident transcription turns out to be wrong.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.thresholds import classify_transcription
from app.db.models import Answer, OCRResult
from app.providers.ocr.base import OCRProvider, RecognitionResult
from app.schemas.enums import AnswerStatus, TranscriptionBand
from app.services import audit
from app.services.preprocessing import (
    PAGE_PRINTED_FORM,
    ImageLoadError,
    crop_line,
    line_ink_fraction,
    load_image,
    preprocess,
    render_debug_overlay,
    sharpness_penalty,
)

logger = logging.getLogger(__name__)

# Share of a line box that must be ink before it is worth reading.
MIN_LINE_INK = 0.004


class TranscriptionError(RuntimeError):
    """Recognition could not be completed. Surfaced to the caller as 4xx/5xx,
    never swallowed into a plausible-looking empty transcription."""


def _page_confidence(
    result: RecognitionResult, blur_score: float
) -> tuple[float, dict[str, float]]:
    """Combine line confidences into one page number, plus its components."""
    texts = [line.text.strip() for line in result.lines]
    if not any(texts):
        return 0.0, {
            "weighted_line_mean": 0.0,
            "sharpness_penalty": sharpness_penalty(blur_score),
            "lines_considered": 0,
        }

    weights = np.array([max(len(text), 1) for text in texts], dtype=np.float64)
    values = np.array([line.confidence for line in result.lines], dtype=np.float64)
    weighted_mean = float((values * weights).sum() / weights.sum())

    penalty = sharpness_penalty(blur_score)
    page = max(0.0, min(1.0, weighted_mean * penalty))

    return round(page, 4), {
        "weighted_line_mean": round(weighted_mean, 4),
        "sharpness_penalty": round(penalty, 4),
        "lines_considered": len(result.lines),
    }


def _collect_warnings(
    result: RecognitionResult, report, page_confidence: float
) -> list[str]:
    warnings = list(result.warnings)

    if report.page_kind == PAGE_PRINTED_FORM:
        warnings.append(
            "This looks like a printed cover or form page (mostly coloured print), "
            "so it was not read. If it does hold an answer written in red or "
            "orange ink, correct the transcription by hand."
        )
        return warnings
    if report.detected_lines == 0:
        warnings.append(
            "No handwriting lines were detected. The page may be blank, very "
            "faint, or photographed at an extreme angle."
        )
    if report.is_low_contrast:
        warnings.append(
            "Low contrast between ink and paper. Better lighting will improve "
            "the transcription."
        )
    if report.blur_score < 90.0:
        warnings.append(
            f"The image is soft (sharpness {report.blur_score:.0f}). "
            "A sharper photograph would raise confidence."
        )
    if abs(report.deskew_angle_deg) > 4.0:
        warnings.append(
            f"The page was rotated by {report.deskew_angle_deg:.1f} degrees "
            "before reading."
        )
    if 0 < page_confidence < 0.70:
        warnings.append(
            "Confidence is low enough that this text should be corrected by "
            "hand before any marks depend on it."
        )
    return warnings


def transcribe_answer(
    db: Session,
    answer: Answer,
    provider: OCRProvider,
    *,
    save_debug_overlay: bool = True,
) -> OCRResult:
    """Run the full pipeline for one answer and persist the result."""
    started = time.perf_counter()

    answer.status = AnswerStatus.OCR_RUNNING
    db.commit()

    try:
        image = load_image(answer.image_path)
    except ImageLoadError as exc:
        answer.status = AnswerStatus.OCR_FAILED
        db.commit()
        raise TranscriptionError(str(exc)) from exc

    try:
        gray, boxes, report = preprocess(image, max_lines=settings.ocr_max_lines)
        # A box with almost no ink is a stray mark, not a line. Sent to the
        # recogniser it costs a full decode and comes back as invented text.
        boxes = [box for box in boxes if line_ink_fraction(gray, box) >= MIN_LINE_INK]
        if report.page_kind == PAGE_PRINTED_FORM:
            result = RecognitionResult(engine=provider.info())
        else:
            line_images = [crop_line(gray, box) for box in boxes]
            if provider.reads_full_page:
                result = provider.recognise_page(image, line_images, boxes)
            else:
                result = provider.recognise(line_images, boxes)
    except Exception as exc:
        answer.status = AnswerStatus.OCR_FAILED
        db.commit()
        logger.exception("Transcription failed for answer %s", answer.id)
        raise TranscriptionError(str(exc)) from exc

    if save_debug_overlay:
        _write_overlay(answer.id, gray, boxes)

    confidence, signals = _page_confidence(result, report.blur_score)
    signals["confidence_method"] = result.confidence_method
    band = classify_transcription(confidence)
    warnings = _collect_warnings(result, report, confidence)

    text = result.text
    duration_ms = int((time.perf_counter() - started) * 1000)
    info = result.engine or provider.info()

    preprocessing_payload = report.model_dump()
    preprocessing_payload["confidence_signals"] = signals

    record = OCRResult(
        answer_id=answer.id,
        extracted_text=text,
        confidence=confidence,
        transcription_band=band.band,
        needs_verification=band.band != TranscriptionBand.RELIABLE,
        line_count=len(result.lines),
        word_count=len(text.split()),
        provider=info.name,
        model_name=info.model_name,
        model_version=info.model_version,
        device=info.device,
        duration_ms=duration_ms,
        lines=[
            {
                "index": line.index,
                "text": line.text,
                "confidence": line.confidence,
                "bbox": list(line.bbox),
            }
            for line in result.lines
        ],
        preprocessing=preprocessing_payload,
        warnings=warnings,
    )

    db.add(record)
    answer.status = AnswerStatus.OCR_DONE
    db.commit()
    db.refresh(record)

    audit.record(
        db,
        action="ocr.completed",
        object_type="answer",
        object_id=answer.id,
        details={
            "confidence": confidence,
            "band": band.band,
            "lines": len(result.lines),
            "provider": info.name,
            "model": info.model_name,
            "duration_ms": duration_ms,
        },
    )

    return record


def combine_pages(records: list[OCRResult]) -> dict[str, object]:
    """Roll per-page transcriptions up into one document-level result.

    The document confidence is weighted by how much text each page carries, for
    the same reason the page score weights lines: a near-blank final page should
    not drag down - or prop up - a booklet of dense writing.
    """
    if not records:
        return {
            "combined_text": "",
            "overall_confidence": 0.0,
            "total_lines": 0,
            "total_words": 0,
        }

    parts: list[str] = []
    weights: list[float] = []
    values: list[float] = []

    for record in records:
        text = record.effective_text.strip()
        if text:
            parts.append(text)
        weights.append(float(max(len(text), 1)))
        values.append(float(record.confidence))

    combined = "\n\n".join(parts)
    weight_array = np.array(weights)
    overall = float((np.array(values) * weight_array).sum() / weight_array.sum())

    return {
        "combined_text": combined,
        "overall_confidence": round(max(0.0, min(1.0, overall)), 4),
        "total_lines": sum(r.line_count for r in records),
        "total_words": len(combined.split()),
    }


def _write_overlay(answer_id: str, gray: np.ndarray, boxes) -> None:
    """Save the segmentation overlay so the UI can show what was detected."""
    import cv2

    try:
        overlay = render_debug_overlay(gray, boxes)
        target = Path(settings.debug_dir) / f"{answer_id}_lines.png"
        success, buffer = cv2.imencode(".png", overlay)
        if success:
            buffer.tofile(str(target))
    except Exception:  # pragma: no cover - debug output is never critical
        logger.warning("Could not write the segmentation overlay", exc_info=True)


def apply_correction(
    db: Session,
    record: OCRResult,
    corrected_text: str,
    corrected_by: str | None = None,
) -> OCRResult:
    """Store a human transcription without destroying the machine one.

    `extracted_text` is left exactly as the model produced it, so character
    error rate remains computable after the correction - this is what turns
    routine examiner work into free ground-truth data.
    """
    from datetime import datetime, timezone

    record.corrected_text = corrected_text
    record.corrected_by = corrected_by
    record.corrected_at = datetime.now(timezone.utc)
    record.needs_verification = False
    db.commit()
    db.refresh(record)

    audit.record(
        db,
        action="ocr.corrected",
        object_type="ocr_result",
        object_id=record.id,
        actor_id=corrected_by,
        details={
            "machine_characters": len(record.extracted_text),
            "corrected_characters": len(corrected_text),
        },
    )
    return record


def accuracy_against(record: OCRResult, reference_text: str) -> dict[str, float | int | str]:
    """Character and word error rate for this transcription.

    Compares the *machine* output against the reference - never the corrected
    text, which would trivially score zero.
    """
    import jiwer

    hypothesis = record.extracted_text or ""
    reference = reference_text

    # Punctuation is stripped *before* whitespace is collapsed. The other order
    # leaves a double space behind every removed mark, which splits one word
    # into two and inflates word error rate - recognisers commonly emit
    # "forms ." where the reference has "forms.", and that is a spacing
    # difference, not a misread word.
    normalise = jiwer.Compose(
        [
            jiwer.ToLowerCase(),
            jiwer.RemovePunctuation(),
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
        ]
    )
    ref_norm = normalise(reference)
    hyp_norm = normalise(hypothesis)

    cer = float(jiwer.cer(ref_norm, hyp_norm)) if ref_norm else 1.0
    wer = float(jiwer.wer(ref_norm, hyp_norm)) if ref_norm else 1.0

    return {
        "character_error_rate": round(cer, 4),
        "word_error_rate": round(wer, 4),
        "reference_characters": len(reference),
        "reference_words": len(reference.split()),
        "hypothesis_characters": len(hypothesis),
        "hypothesis_words": len(hypothesis.split()),
        "compared_against": "machine_transcription",
    }
