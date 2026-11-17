"""Marking, review and validation contracts - Parts 3 and 4.

A score leaves this system with its whole derivation attached: which criterion
awarded each mark, the student's own words that justified it, which signals
produced the confidence, and which model and rubric version were used. An
examiner must be able to disagree with a specific judgement, not just a total.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import ReviewAction, ReviewBand


class EvaluationCriterionOut(BaseModel):
    """One criterion's outcome: the mark, and why."""

    id: str
    position: int
    description: str
    awarded_marks: float
    max_marks: float
    verdict: str
    reason: str
    evidence_quote: str | None = None
    # False when the quotation could not be found in the transcription, which
    # means the judgement was not read off the page. Shown in the interface.
    evidence_found: bool = True

    model_config = ConfigDict(from_attributes=True)


class EvaluationOut(BaseModel):
    id: str
    answer_id: str
    question_id: str | None = None
    question_number: str | None = None
    rubric_id: str | None = None
    rubric_version: int
    ocr_result_id: str | None = None

    score: float
    max_score: float
    percentage: float

    confidence: float = Field(ge=0.0, le=1.0)
    review_band: ReviewBand
    band_label: str
    band_description: str
    # True unless the band says the score may be accepted without a human.
    needs_review: bool

    overall_explanation: str
    confidence_signals: dict = Field(default_factory=dict)
    criteria: list[EvaluationCriterionOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    provider: str
    model_name: str
    prompt_version: str
    text_source: str
    duration_ms: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluateIn(BaseModel):
    """Mark one already-transcribed answer."""

    answer_id: str
    # Needed when the answer was not uploaded against a question. Ignored when
    # the answer already carries one.
    question_id: str | None = None
    # Overrides the configured number of independent readings. More readings
    # make the agreement signal sharper and cost proportionally more.
    samples: int | None = Field(default=None, ge=1, le=5)


class QuestionSegmentOut(BaseModel):
    """One question's answer, located within a booklet's transcription."""

    question_id: str
    question_number: str | None = None
    question_text: str
    max_marks: float
    text: str
    # Which transcribed pages this answer was found on.
    page_numbers: list[int] = Field(default_factory=list)
    # How the segment was located: "marker" (the student numbered it),
    # "model" (a model split the booklet), or "whole_page".
    located_by: str
    # Transcription confidence for the pages the segment came from.
    transcription_confidence: float
    found: bool = True


class BookletSegmentationOut(BaseModel):
    """A booklet's transcription split into per-question answers."""

    document_ref: str
    exam_id: str
    segments: list[QuestionSegmentOut] = Field(default_factory=list)
    unmatched_text: str = ""
    warnings: list[str] = Field(default_factory=list)


class EvaluateBookletIn(BaseModel):
    """Mark every question of one transcribed booklet."""

    document_ref: str
    exam_id: str | None = None
    booklet_ref: str | None = None
    samples: int | None = Field(default=None, ge=1, le=5)


class BookletResultOut(BaseModel):
    """A whole marked booklet - what an examiner actually opens."""

    document_ref: str
    exam_id: str
    exam_title: str
    booklet_ref: str | None = None

    total_score: float
    total_max: float
    percentage: float
    # Length-weighted mean of the per-question confidences.
    overall_confidence: float
    review_band: ReviewBand
    band_label: str
    questions_marked: int
    questions_total: int
    # Questions whose confidence puts them below auto-accept.
    needs_review: list[str] = Field(default_factory=list)

    evaluations: list[EvaluationOut] = Field(default_factory=list)
    segmentation: BookletSegmentationOut | None = None
    duration_ms: int
    warnings: list[str] = Field(default_factory=list)


class ReviewIn(BaseModel):
    """An examiner accepting or changing a machine score.

    Written as a new row; the machine score is never overwritten. That
    separation is what lets agreement be measured after the fact.
    """

    evaluation_id: str
    action: ReviewAction
    # Required for "modify", ignored for "accept".
    final_score: float | None = Field(default=None, ge=0)
    comments: str | None = Field(default=None, max_length=5000)
    reviewer_id: str | None = None
    # Seconds the examiner spent. Part of the time-saving claim, so it is
    # recorded rather than estimated.
    duration_ms: int = Field(default=0, ge=0)


class ReviewOut(BaseModel):
    id: str
    answer_id: str
    evaluation_id: str | None = None
    reviewer_id: str | None = None
    action: ReviewAction
    final_score: float
    ai_score_at_review: float | None = None
    # final_score - ai_score_at_review. The quantity the validation study is
    # actually about.
    delta: float | None = None
    comments: str | None = None
    duration_ms: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluatorInfoOut(BaseModel):
    name: str
    model_name: str
    model_version: str
    prompt_version: str
    is_ready: bool
    is_mock: bool
    detail: str


class BandAgreementOut(BaseModel):
    """Does the confidence band predict whether a human changed the score?

    This is the table the whole confidence design has to justify itself
    against. If scores in the top band are modified as often as those in the
    bottom one, the confidence measure is not informative, however reasonable
    its components look.
    """

    band: str
    label: str
    evaluations: int
    reviewed: int
    accepted: int
    modified: int
    modification_rate: float | None = None
    mean_absolute_delta: float | None = None


class AnalyticsOut(BaseModel):
    answers_uploaded: int
    answers_transcribed: int
    evaluations: int
    reviews: int

    mean_transcription_confidence: float | None = None
    mean_evaluation_confidence: float | None = None

    # Agreement between machine and examiner, over reviewed evaluations only.
    reviewed_evaluations: int = 0
    exact_agreement: float | None = None
    within_half_mark: float | None = None
    mean_absolute_error: float | None = None

    by_band: list[BandAgreementOut] = Field(default_factory=list)
    mean_review_seconds: float | None = None
    note: str = ""
