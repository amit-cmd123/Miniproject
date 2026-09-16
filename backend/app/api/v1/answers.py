"""Answer upload and transcription endpoints - Part 1's public surface."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.thresholds import classify_transcription, describe_bands
from app.db.models import Answer, OCRResult
from app.db.session import get_db
from app.providers.ocr.base import OCRProvider
from app.providers.ocr.registry import get_ocr_provider
from app.schemas.ocr import (
    AccuracyIn,
    AccuracyOut,
    AnswerDetailOut,
    AnswerOut,
    AnswerWithOCROut,
    CorrectionIn,
    DocumentTranscriptionOut,
    OCRResultOut,
    PageResultOut,
    PdfInspectionOut,
    ProviderInfoOut,
    ThresholdsOut,
)
from app.services import answer_service, ocr_service, pdf_service
from app.services.answer_service import UploadRejected
from app.services.ocr_service import TranscriptionError
from app.services.pdf_service import PdfError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["answers"])

# Measured on a dense real answer page; used only for the wait shown upfront.
LOCAL_SECONDS_PER_PAGE = 10.0
CLOUD_SECONDS_PER_PAGE = 15.0


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _answer_out(answer: Answer) -> AnswerOut:
    return AnswerOut(
        id=answer.id,
        question_id=answer.question_id,
        booklet_ref=answer.booklet_ref,
        document_ref=answer.document_ref,
        page_number=answer.page_number,
        source_filename=answer.source_filename,
        original_filename=answer.original_filename,
        content_type=answer.content_type,
        size_bytes=answer.size_bytes,
        status=answer.status,
        image_url=f"{settings.api_prefix}/answers/{answer.id}/image",
        created_at=answer.created_at,
    )


def _ocr_out(record: OCRResult) -> OCRResultOut:
    band = classify_transcription(record.confidence)
    preprocessing = dict(record.preprocessing or {})
    preprocessing.pop("confidence_signals", None)

    return OCRResultOut(
        id=record.id,
        answer_id=record.answer_id,
        extracted_text=record.extracted_text,
        corrected_text=record.corrected_text,
        effective_text=record.effective_text,
        text_source=record.text_source,
        confidence=record.confidence,
        transcription_band=record.transcription_band,
        band_label=band.label,
        band_description=band.description,
        needs_verification=record.needs_verification,
        line_count=record.line_count,
        word_count=record.word_count,
        provider=record.provider,
        model_name=record.model_name,
        model_version=record.model_version,
        device=record.device,
        duration_ms=record.duration_ms,
        lines=[
            {
                "index": line["index"],
                "text": line["text"],
                "confidence": line["confidence"],
                "bbox": tuple(line["bbox"]),
            }
            for line in (record.lines or [])
        ],
        preprocessing=preprocessing or None,
        warnings=record.warnings or [],
        created_at=record.created_at,
    )


def _get_answer(db: Session, answer_id: str) -> Answer:
    answer = db.get(Answer, answer_id)
    if answer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No answer with that id.")
    return answer


def _get_latest_ocr(db: Session, answer: Answer) -> OCRResult:
    record = answer.latest_ocr
    if record is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This answer has not been transcribed yet. Run transcription first.",
        )
    return record


# ---------------------------------------------------------------------------
# Engine and configuration
# ---------------------------------------------------------------------------


@router.get("/ocr/provider", response_model=ProviderInfoOut)
def provider_info(provider: OCRProvider = Depends(get_ocr_provider)) -> ProviderInfoOut:
    """Which recognition engine is loaded, and is it ready?"""
    info = provider.info()
    return ProviderInfoOut(**info.__dict__)


@router.get("/config/thresholds", response_model=ThresholdsOut)
def thresholds() -> ThresholdsOut:
    """Confidence bands, served rather than hard-coded into the interface."""
    return ThresholdsOut(**describe_bands())


# ---------------------------------------------------------------------------
# Upload and transcription
# ---------------------------------------------------------------------------


@router.post(
    "/answers",
    response_model=AnswerOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_answer(
    file: UploadFile = File(...),
    question_id: str | None = Form(default=None),
    booklet_ref: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> AnswerOut:
    """Register a handwritten answer image without transcribing it."""
    data = await file.read()
    try:
        answer = answer_service.register_answer(
            db,
            data=data,
            content_type=file.content_type,
            original_filename=file.filename,
            question_id=question_id,
            booklet_ref=booklet_ref,
        )
    except UploadRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _answer_out(answer)


@router.post("/answers/{answer_id}/ocr", response_model=OCRResultOut)
def transcribe(
    answer_id: str,
    db: Session = Depends(get_db),
    provider: OCRProvider = Depends(get_ocr_provider),
) -> OCRResultOut:
    """Read the handwriting on a registered answer."""
    answer = _get_answer(db, answer_id)
    try:
        record = ocr_service.transcribe_answer(db, answer, provider)
    except TranscriptionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _ocr_out(record)


@router.post(
    "/answers/transcribe",
    response_model=AnswerWithOCROut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_and_transcribe(
    file: UploadFile = File(...),
    question_id: str | None = Form(default=None),
    booklet_ref: str | None = Form(default=None),
    db: Session = Depends(get_db),
    provider: OCRProvider = Depends(get_ocr_provider),
) -> AnswerWithOCROut:
    """Upload and read in one call - what the interface uses."""
    data = await file.read()
    try:
        answer = answer_service.register_answer(
            db,
            data=data,
            content_type=file.content_type,
            original_filename=file.filename,
            question_id=question_id,
            booklet_ref=booklet_ref,
        )
    except UploadRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        record = ocr_service.transcribe_answer(db, answer, provider)
    except TranscriptionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return AnswerWithOCROut(answer=_answer_out(answer), ocr=_ocr_out(record))


# ---------------------------------------------------------------------------
# PDF documents
# ---------------------------------------------------------------------------


@router.post("/documents/inspect", response_model=PdfInspectionOut)
async def inspect_pdf(
    file: UploadFile = File(...),
    provider: OCRProvider = Depends(get_ocr_provider),
) -> PdfInspectionOut:
    """How many pages, and roughly how long will reading them take?

    Called before transcription so the interface can warn about a long wait
    rather than appearing to hang.
    """
    data = await file.read()
    if not pdf_service.is_pdf(file.content_type, data):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "That file is not a PDF."
        )
    try:
        total = pdf_service.page_count(data)
    except PdfError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # Deliberately rough figures, and described as such. A cloud engine reads
    # a page in one request; the local engine reads a densely written A4 side
    # of roughly 25 lines at the measured CPU rate per line.
    per_page = CLOUD_SECONDS_PER_PAGE if provider.reads_full_page else LOCAL_SECONDS_PER_PAGE
    estimate = int(total * per_page)
    return PdfInspectionOut(
        filename=file.filename,
        total_pages=total,
        estimated_seconds=estimate,
        note=(
            f"{total} page{'s' if total != 1 else ''}. Reading every page takes "
            f"roughly {estimate // 60} min {estimate % 60} s on this machine. "
            "Select a page range to read fewer."
        ),
    )


@router.post(
    "/documents/transcribe",
    response_model=DocumentTranscriptionOut,
    status_code=status.HTTP_201_CREATED,
)
async def transcribe_document(
    file: UploadFile = File(...),
    pages: str | None = Form(default=None, description="e.g. 1-3 or 2,5. Blank = all."),
    booklet_ref: str | None = Form(default=None),
    db: Session = Depends(get_db),
    provider: OCRProvider = Depends(get_ocr_provider),
) -> DocumentTranscriptionOut:
    """Read a scanned PDF answer booklet.

    Each page becomes its own `Answer` with its own transcription, sharing a
    `document_ref`. A page that fails is reported in place rather than
    discarding the rest of the booklet.
    """
    started = time.perf_counter()
    data = await file.read()

    if not pdf_service.is_pdf(file.content_type, data):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That file is not a PDF. Upload an image on the single-answer screen instead.",
        )
    if len(data) > settings.max_pdf_bytes:
        limit_mb = settings.max_pdf_bytes / (1024 * 1024)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"That PDF is larger than the {limit_mb:.0f} MB limit. "
            "Re-scan at a lower resolution or split it.",
        )

    try:
        total = pdf_service.page_count(data)
        wanted = pdf_service.parse_page_range(pages, total)
    except PdfError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if len(wanted) > settings.max_pdf_pages:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"That selection is {len(wanted)} pages and the limit is "
            f"{settings.max_pdf_pages}. Give a page range such as 1-5.",
        )

    try:
        rendered = pdf_service.render_pages(data, wanted)
    except PdfError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    document_ref = str(uuid.uuid4())
    results: list[PageResultOut] = []
    records: list[OCRResult] = []
    warnings: list[str] = []

    for page in rendered:
        try:
            png = pdf_service.encode_png(page.image)
            answer = answer_service.register_answer(
                db,
                data=png,
                content_type="image/png",
                original_filename=f"{file.filename or 'document'} p{page.page_number}",
                booklet_ref=booklet_ref,
                document_ref=document_ref,
                page_number=page.page_number,
                source_filename=file.filename,
                skip_validation=True,
            )
            record = ocr_service.transcribe_answer(db, answer, provider)
            records.append(record)
            results.append(
                PageResultOut(
                    page_number=page.page_number,
                    answer=_answer_out(answer),
                    ocr=_ocr_out(record),
                )
            )
        except (TranscriptionError, PdfError) as exc:
            # One bad page must not lose the whole booklet.
            logger.warning("Page %s failed: %s", page.page_number, exc)
            warnings.append(f"Page {page.page_number} could not be read: {exc}")
            results.append(PageResultOut(page_number=page.page_number, error=str(exc)))

    if not records:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No page of this PDF could be read. "
            + (warnings[0] if warnings else ""),
        )

    combined = ocr_service.combine_pages(records)
    band = classify_transcription(float(combined["overall_confidence"]))

    if len(wanted) < total:
        warnings.append(
            f"Read {len(wanted)} of {total} pages. Clear the page range to read all."
        )

    return DocumentTranscriptionOut(
        document_ref=document_ref,
        filename=file.filename,
        total_pages=total,
        pages_processed=len(records),
        pages=results,
        combined_text=str(combined["combined_text"]),
        overall_confidence=float(combined["overall_confidence"]),
        transcription_band=band.band,
        band_label=band.label,
        total_lines=int(combined["total_lines"]),
        total_words=int(combined["total_words"]),
        duration_ms=int((time.perf_counter() - started) * 1000),
        warnings=warnings,
    )


@router.get("/documents/{document_ref}", response_model=list[AnswerDetailOut])
def get_document_pages(
    document_ref: str, db: Session = Depends(get_db)
) -> list[AnswerDetailOut]:
    """Every page of one uploaded document, in order."""
    answers = (
        db.query(Answer)
        .filter(Answer.document_ref == document_ref)
        .order_by(Answer.page_number)
        .all()
    )
    if not answers:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No document with that reference.")
    return [
        AnswerDetailOut(
            **_answer_out(answer).model_dump(),
            latest_ocr=_ocr_out(answer.latest_ocr) if answer.latest_ocr else None,
        )
        for answer in answers
    ]


# ---------------------------------------------------------------------------
# Reading results
# ---------------------------------------------------------------------------


@router.get("/answers", response_model=list[AnswerDetailOut])
def list_answers(limit: int = 100, db: Session = Depends(get_db)) -> list[AnswerDetailOut]:
    results: list[AnswerDetailOut] = []
    for answer in answer_service.list_answers(db, limit=limit):
        latest = answer.latest_ocr
        results.append(
            AnswerDetailOut(
                **_answer_out(answer).model_dump(),
                latest_ocr=_ocr_out(latest) if latest else None,
            )
        )
    return results


@router.get("/answers/{answer_id}", response_model=AnswerDetailOut)
def get_answer(answer_id: str, db: Session = Depends(get_db)) -> AnswerDetailOut:
    answer = _get_answer(db, answer_id)
    latest = answer.latest_ocr
    return AnswerDetailOut(
        **_answer_out(answer).model_dump(),
        latest_ocr=_ocr_out(latest) if latest else None,
    )


@router.get("/answers/{answer_id}/image")
def get_image(answer_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """The original handwriting. It must stay reachable at every later stage."""
    answer = _get_answer(db, answer_id)
    path = Path(answer.image_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The stored image is missing.")
    return FileResponse(path, media_type=answer.content_type or "image/png")


@router.get("/answers/{answer_id}/segmentation")
def get_segmentation(answer_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """The page with detected line boxes drawn on it.

    Lets a human see whether segmentation or recognition is what went wrong.
    """
    _get_answer(db, answer_id)
    path = Path(settings.debug_dir) / f"{answer_id}_lines.png"
    if not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No segmentation overlay for this answer. Run transcription first.",
        )
    return FileResponse(path, media_type="image/png")


# ---------------------------------------------------------------------------
# Human correction and measurement
# ---------------------------------------------------------------------------


@router.patch("/answers/{answer_id}/ocr/verify", response_model=OCRResultOut)
def correct_transcription(
    answer_id: str, payload: CorrectionIn, db: Session = Depends(get_db)
) -> OCRResultOut:
    """Save a human-corrected transcription.

    The machine output is preserved, so error rates stay computable and the
    correction becomes ground-truth data.
    """
    answer = _get_answer(db, answer_id)
    record = _get_latest_ocr(db, answer)
    updated = ocr_service.apply_correction(
        db, record, payload.corrected_text, payload.corrected_by
    )
    return _ocr_out(updated)


@router.post("/answers/{answer_id}/ocr/accuracy", response_model=AccuracyOut)
def measure_accuracy(
    answer_id: str, payload: AccuracyIn, db: Session = Depends(get_db)
) -> AccuracyOut:
    """Character and word error rate against a known-correct transcription."""
    answer = _get_answer(db, answer_id)
    record = _get_latest_ocr(db, answer)
    return AccuracyOut(**ocr_service.accuracy_against(record, payload.reference_text))
