"""SQLAlchemy models for the whole EvalNova Core data model.

All entities are defined up front, including the ones Parts 2-4 will use, so
that the four workstreams share one schema instead of negotiating migrations
mid-project.

Two rules hold across this file:

1. `Evaluation` and `Review` rows are **append-only**. A human correction
   never overwrites the AI result - it is written as a new row. The entire
   validation study depends on that separation.
2. Every table that could one day belong to an institution carries a nullable
   `organization_id`. It is unused today and costs nothing; it means
   multi-tenancy will not require rewriting the schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.schemas.enums import AnswerStatus


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    role: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------------------
# Academic context - Part 2 owns the write side of these
# ---------------------------------------------------------------------------


class Exam(Base, TimestampMixin):
    __tablename__ = "exams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300))
    subject: Mapped[str] = mapped_column(String(120))
    subject_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    term: Mapped[str | None] = mapped_column(String(80), nullable=True)

    questions: Mapped[list["Question"]] = relationship(back_populates="exam")


class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"))
    number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(String(160), nullable=True)
    question_type: Mapped[str] = mapped_column(String(40), default="theory")
    max_marks: Mapped[float] = mapped_column(Float)

    exam: Mapped[Exam] = relationship(back_populates="questions")
    answers: Mapped[list["Answer"]] = relationship(back_populates="question")
    answer_keys: Mapped[list["AnswerKey"]] = relationship(back_populates="question")
    rubrics: Mapped[list["Rubric"]] = relationship(back_populates="question")


class AnswerKey(Base, TimestampMixin):
    __tablename__ = "answer_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"))
    reference_answer: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    question: Mapped[Question] = relationship(back_populates="answer_keys")


class Rubric(Base, TimestampMixin):
    __tablename__ = "rubrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    marking_scheme: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Rules the scoring engine applies deterministically, outside the model.
    scoring_rules: Mapped[dict] = mapped_column(JSON, default=dict)

    question: Mapped[Question] = relationship(back_populates="rubrics")
    criteria: Mapped[list["RubricCriterion"]] = relationship(
        back_populates="rubric", order_by="RubricCriterion.position"
    )


class RubricCriterion(Base, TimestampMixin):
    __tablename__ = "rubric_criteria"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rubric_id: Mapped[str] = mapped_column(ForeignKey("rubrics.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text)
    max_marks: Mapped[float] = mapped_column(Float)
    essential_concepts: Mapped[list] = mapped_column(JSON, default=list)
    acceptable_alternatives: Mapped[list] = mapped_column(JSON, default=list)
    common_mistakes: Mapped[list] = mapped_column(JSON, default=list)
    allows_partial: Mapped[bool] = mapped_column(Boolean, default=True)

    rubric: Mapped[Rubric] = relationship(back_populates="criteria")


# ---------------------------------------------------------------------------
# Answers and transcription - Part 1
# ---------------------------------------------------------------------------


class Answer(Base, TimestampMixin):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    question_id: Mapped[str | None] = mapped_column(
        ForeignKey("questions.id"), nullable=True
    )
    # Anonymous booklet reference. Deliberately not a student identifier.
    booklet_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Set when this answer came from one page of an uploaded document. Pages of
    # the same upload share a document_ref, so a booklet stays together without
    # the data model needing a separate Document entity yet.
    document_ref: Mapped[str | None] = mapped_column(String(36), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)

    image_path: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=AnswerStatus.REGISTERED)

    question: Mapped[Question | None] = relationship(back_populates="answers")
    ocr_results: Mapped[list["OCRResult"]] = relationship(
        back_populates="answer", order_by="OCRResult.created_at"
    )

    @property
    def latest_ocr(self) -> "OCRResult | None":
        return self.ocr_results[-1] if self.ocr_results else None


class OCRResult(Base, TimestampMixin):
    """One transcription attempt for one answer.

    Carries both the machine output and any human correction. Evaluation reads
    `effective_text`, which prefers the corrected version - that is what stops
    weak handwriting recognition from blocking Parts 2-4.
    """

    __tablename__ = "ocr_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    answer_id: Mapped[str] = mapped_column(ForeignKey("answers.id"))

    extracted_text: Mapped[str] = mapped_column(Text, default="")
    corrected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    corrected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    transcription_band: Mapped[str] = mapped_column(String(32))
    needs_verification: Mapped[bool] = mapped_column(Boolean, default=True)

    line_count: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)

    provider: Mapped[str] = mapped_column(String(60))
    model_name: Mapped[str] = mapped_column(String(160))
    model_version: Mapped[str] = mapped_column(String(60), default="unknown")
    device: Mapped[str] = mapped_column(String(20), default="cpu")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Per-line detail and preprocessing steps, kept for debugging and for the
    # failure taxonomy Part 1 has to produce.
    lines: Mapped[list] = mapped_column(JSON, default=list)
    preprocessing: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    answer: Mapped[Answer] = relationship(back_populates="ocr_results")

    @property
    def effective_text(self) -> str:
        return self.corrected_text if self.corrected_text is not None else self.extracted_text

    @property
    def text_source(self) -> str:
        return "human_corrected" if self.corrected_text is not None else "machine"


# ---------------------------------------------------------------------------
# Evaluation and review - Parts 3 and 4. Tables exist; services do not yet.
# ---------------------------------------------------------------------------


class Evaluation(Base, TimestampMixin):
    """Append-only. Never updated once written."""

    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    answer_id: Mapped[str] = mapped_column(ForeignKey("answers.id"))
    rubric_id: Mapped[str | None] = mapped_column(ForeignKey("rubrics.id"), nullable=True)
    ocr_result_id: Mapped[str | None] = mapped_column(
        ForeignKey("ocr_results.id"), nullable=True
    )

    score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    review_band: Mapped[str] = mapped_column(String(32))
    overall_explanation: Mapped[str] = mapped_column(Text, default="")

    # Signals that made up the composite confidence, kept so calibration work
    # in Phase 3 can see which one was responsible for a bad call.
    confidence_signals: Mapped[dict] = mapped_column(JSON, default=dict)

    provider: Mapped[str] = mapped_column(String(60))
    model_name: Mapped[str] = mapped_column(String(160))
    model_version: Mapped[str] = mapped_column(String(60), default="unknown")
    prompt_version: Mapped[str] = mapped_column(String(60), default="unknown")
    rubric_version: Mapped[int] = mapped_column(Integer, default=1)
    text_source: Mapped[str] = mapped_column(String(32), default="machine")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    criteria: Mapped[list["EvaluationCriterion"]] = relationship(
        back_populates="evaluation", order_by="EvaluationCriterion.position"
    )


class EvaluationCriterion(Base, TimestampMixin):
    __tablename__ = "evaluation_criteria"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"))
    rubric_criterion_id: Mapped[str | None] = mapped_column(
        ForeignKey("rubric_criteria.id"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text)
    awarded_marks: Mapped[float] = mapped_column(Float, default=0.0)
    max_marks: Mapped[float] = mapped_column(Float, default=0.0)
    verdict: Mapped[str] = mapped_column(String(32), default="not_satisfied")
    reason: Mapped[str] = mapped_column(Text, default="")
    # The student's own words that justified this verdict.
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)

    evaluation: Mapped[Evaluation] = relationship(back_populates="criteria")


class Review(Base, TimestampMixin):
    """Append-only human decision. A separate row, never an overwrite."""

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    answer_id: Mapped[str] = mapped_column(ForeignKey("answers.id"))
    evaluation_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluations.id"), nullable=True
    )
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(20))
    final_score: Mapped[float] = mapped_column(Float)
    ai_score_at_review: Mapped[float | None] = mapped_column(Float, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class GroundTruth(Base, TimestampMixin):
    """The human-labelled set every metric is measured against."""

    __tablename__ = "ground_truth"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    answer_id: Mapped[str] = mapped_column(ForeignKey("answers.id"))
    verified_transcription: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_marks: Mapped[float | None] = mapped_column(Float, nullable=True)
    marker_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConfigSetting(Base, TimestampMixin):
    """Runtime-tunable values. Thresholds belong here, not in the code."""

    __tablename__ = "config_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(160), default="system")
    action: Mapped[str] = mapped_column(String(80))
    object_type: Mapped[str] = mapped_column(String(60))
    object_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
