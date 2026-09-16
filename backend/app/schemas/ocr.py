"""Transcription contracts - Part 1's output, Part 3's input.

This is the handoff the team agreed on:
    answer_id + question_id + extracted_text + confidence + image reference
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import AnswerStatus, TranscriptionBand


class LineResult(BaseModel):
    """One segmented handwriting line and what we read from it."""

    index: int
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    # Bounding box in the preprocessed image: x, y, width, height.
    bbox: tuple[int, int, int, int]

    model_config = ConfigDict(from_attributes=True)


class PreprocessingReport(BaseModel):
    """What we did to the image before reading it, and what we saw.

    Kept because Part 1 has to explain *why* a transcription failed, not just
    that it did.
    """

    steps: list[str] = Field(default_factory=list)
    original_size: tuple[int, int] | None = None
    processed_size: tuple[int, int] | None = None
    deskew_angle_deg: float = 0.0
    estimated_ink_coverage: float = 0.0
    detected_lines: int = 0
    blur_score: float = 0.0
    is_low_contrast: bool = False
    # "handwriting", or "printed_form" for a cover/form page that is skipped.
    page_kind: str = "handwriting"
    ruling_removed: bool = False


class OCRResultOut(BaseModel):
    id: str
    answer_id: str

    extracted_text: str
    corrected_text: str | None = None
    effective_text: str
    text_source: str

    confidence: float = Field(ge=0.0, le=1.0)
    transcription_band: TranscriptionBand
    band_label: str
    band_description: str
    needs_verification: bool

    line_count: int
    word_count: int

    provider: str
    model_name: str
    model_version: str
    device: str
    duration_ms: int

    lines: list[LineResult] = Field(default_factory=list)
    preprocessing: PreprocessingReport | None = None
    warnings: list[str] = Field(default_factory=list)

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnswerOut(BaseModel):
    id: str
    question_id: str | None = None
    booklet_ref: str | None = None
    document_ref: str | None = None
    page_number: int | None = None
    source_filename: str | None = None
    original_filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    status: AnswerStatus
    image_url: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnswerDetailOut(AnswerOut):
    latest_ocr: OCRResultOut | None = None


class AnswerWithOCROut(BaseModel):
    """Returned by the upload-and-transcribe convenience endpoint."""

    answer: AnswerOut
    ocr: OCRResultOut


class PageResultOut(BaseModel):
    """One page of an uploaded document, transcribed.

    `error` is populated instead of `ocr` when that single page failed - one
    unreadable page must not discard the rest of the booklet.
    """

    page_number: int
    answer: AnswerOut | None = None
    ocr: OCRResultOut | None = None
    error: str | None = None


class DocumentTranscriptionOut(BaseModel):
    """The result of reading a whole PDF."""

    document_ref: str
    filename: str | None = None
    total_pages: int
    pages_processed: int
    pages: list[PageResultOut] = Field(default_factory=list)

    combined_text: str
    overall_confidence: float = Field(ge=0.0, le=1.0)
    transcription_band: TranscriptionBand
    band_label: str
    total_lines: int
    total_words: int
    duration_ms: int
    warnings: list[str] = Field(default_factory=list)


class PdfInspectionOut(BaseModel):
    """What we can tell about a PDF before committing to reading it.

    Recognition costs several seconds per page, so a booklet can take minutes.
    This lets the interface say so before starting.
    """

    filename: str | None = None
    total_pages: int
    estimated_seconds: int
    note: str


class CorrectionIn(BaseModel):
    """A human fixing the machine transcription.

    Note this never edits `extracted_text`. The machine output stays intact so
    that character error rate can still be computed after the fix.
    """

    corrected_text: str = Field(min_length=0, max_length=50_000)
    corrected_by: str | None = None


class AccuracyIn(BaseModel):
    """Compare a transcription against a known-correct reference."""

    reference_text: str = Field(min_length=1, max_length=50_000)


class AccuracyOut(BaseModel):
    character_error_rate: float
    word_error_rate: float
    reference_characters: int
    reference_words: int
    hypothesis_characters: int
    hypothesis_words: int
    compared_against: str


class BandOut(BaseModel):
    band: str
    min_confidence: float
    label: str
    description: str


class ThresholdsOut(BaseModel):
    transcription: list[BandOut]
    evaluation: list[BandOut]


class ProviderInfoOut(BaseModel):
    name: str
    model_name: str
    model_version: str
    device: str
    is_ready: bool
    is_mock: bool
    detail: str
