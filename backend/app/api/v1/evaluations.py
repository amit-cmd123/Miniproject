"""Marking, review and validation endpoints - Parts 3 and 4."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.thresholds import classify_evaluation
from app.db.models import Answer, Evaluation, Question
from app.db.session import get_db
from app.providers.evaluation.base import EvaluationProvider
from app.providers.evaluation.registry import get_evaluation_provider
from app.schemas.enums import ReviewBand
from app.schemas.evaluation import (
    AnalyticsOut,
    BookletResultOut,
    BookletSegmentationOut,
    EvaluateBookletIn,
    EvaluateIn,
    EvaluationCriterionOut,
    EvaluationOut,
    EvaluatorInfoOut,
    QuestionSegmentOut,
    ReviewIn,
    ReviewOut,
)
from app.services import (
    analytics_service,
    evaluation_service,
    review_service,
    rubric_service,
    scoring,
)
from app.services.evaluation_service import EvaluationError, Segment
from app.services.review_service import ReviewError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["evaluation & review"])


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _evaluation_out(db: Session, record: Evaluation) -> EvaluationOut:
    answer = db.get(Answer, record.answer_id)
    question = (
        db.get(Question, answer.question_id) if answer and answer.question_id else None
    )
    band = classify_evaluation(record.confidence)
    signals = dict(record.confidence_signals or {})
    warnings = list(signals.pop("warnings", []) or [])

    ungrounded = set(signals.get("ungrounded_criteria") or [])

    return EvaluationOut(
        id=record.id,
        answer_id=record.answer_id,
        question_id=question.id if question else None,
        question_number=question.number if question else None,
        rubric_id=record.rubric_id,
        rubric_version=record.rubric_version,
        ocr_result_id=record.ocr_result_id,
        score=record.score,
        max_score=record.max_score,
        percentage=(
            round(100.0 * record.score / record.max_score, 2) if record.max_score else 0.0
        ),
        confidence=record.confidence,
        review_band=record.review_band,
        band_label=band.label,
        band_description=band.description,
        needs_review=record.review_band != ReviewBand.AUTO_ACCEPT,
        overall_explanation=record.overall_explanation,
        confidence_signals=signals,
        criteria=[
            EvaluationCriterionOut(
                id=criterion.id,
                position=criterion.position,
                description=criterion.description,
                awarded_marks=criterion.awarded_marks,
                max_marks=criterion.max_marks,
                verdict=criterion.verdict,
                reason=criterion.reason,
                evidence_quote=criterion.evidence_quote,
                evidence_found=criterion.position not in ungrounded,
            )
            for criterion in sorted(record.criteria, key=lambda c: c.position)
        ],
        warnings=warnings,
        provider=record.provider,
        model_name=record.model_name,
        prompt_version=record.prompt_version,
        text_source=record.text_source,
        duration_ms=record.duration_ms,
        created_at=record.created_at,
    )


def _segment_out(segment: Segment) -> QuestionSegmentOut:
    return QuestionSegmentOut(
        question_id=segment.question.id,
        question_number=segment.question.number,
        question_text=segment.question.text,
        max_marks=segment.question.max_marks,
        text=segment.text,
        page_numbers=segment.page_numbers,
        located_by=segment.located_by,
        transcription_confidence=segment.transcription_confidence,
        found=segment.found,
    )


def _review_out(review) -> ReviewOut:
    delta = (
        round(review.final_score - review.ai_score_at_review, 4)
        if review.ai_score_at_review is not None
        else None
    )
    return ReviewOut(
        id=review.id,
        answer_id=review.answer_id,
        evaluation_id=review.evaluation_id,
        reviewer_id=review.reviewer_id,
        action=review.action,
        final_score=review.final_score,
        ai_score_at_review=review.ai_score_at_review,
        delta=delta,
        comments=review.comments,
        duration_ms=review.duration_ms,
        created_at=review.created_at,
    )


def _resolve_exam(db: Session, exam_id: str | None):
    """The exam to mark against: the one asked for, or the only one there is."""
    if exam_id:
        exam = rubric_service.get_exam(db, exam_id)
        if exam is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No exam with that id.")
        return exam

    exams = rubric_service.list_exams(db)
    if not exams:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No exam has been defined yet, so there is no rubric to mark against. "
            "Load the bundled paper with POST /exams/seed.",
        )
    if len(exams) > 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"There are {len(exams)} exams defined. Say which one to mark "
            f"against with exam_id.",
        )
    return exams[0]


# ---------------------------------------------------------------------------
# The marker
# ---------------------------------------------------------------------------


@router.get("/evaluations/provider", response_model=EvaluatorInfoOut)
def evaluator_info(
    provider: EvaluationProvider = Depends(get_evaluation_provider),
) -> EvaluatorInfoOut:
    """Which marker is configured, and is it usable?"""
    return EvaluatorInfoOut(**provider.info().__dict__)


@router.get("/config/confidence-weights")
def confidence_weights() -> dict:
    """The confidence signals and their weights, served rather than hard-coded.

    Published so the interface can explain a confidence score, and so the
    weights can be seen to be an uncalibrated hypothesis.
    """
    return {
        "weights": scoring.WEIGHTS,
        "method": "weighted_geometric_mean",
        "floor": scoring.SIGNAL_FLOOR,
        "grounding_match_threshold": scoring.GROUNDING_MATCH,
        "signals": {
            "transcription": "How well the handwriting was read. A human-corrected "
            "transcription scores 1.0.",
            "agreement": "How far two independent markings of the same answer "
            "coincided, criterion by criterion.",
            "grounding": "Share of mark-bearing verdicts whose quoted evidence "
            "was actually found in the transcription.",
            "decisiveness": "How far the verdicts sit from the partial-credit "
            "boundary, weighted by marks.",
        },
        "note": "Uncalibrated starting values. Stored with every evaluation so a "
        "validation study can replace them with measured weights.",
    }


# ---------------------------------------------------------------------------
# Marking one answer
# ---------------------------------------------------------------------------


@router.post(
    "/evaluations", response_model=EvaluationOut, status_code=status.HTTP_201_CREATED
)
def create_evaluation(
    payload: EvaluateIn,
    db: Session = Depends(get_db),
    provider: EvaluationProvider = Depends(get_evaluation_provider),
) -> EvaluationOut:
    """Mark one transcribed answer against its question's rubric."""
    answer = db.get(Answer, payload.answer_id)
    if answer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No answer with that id.")

    record = answer.latest_ocr
    if record is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This answer has not been transcribed yet. Transcribe it first.",
        )

    question_id = payload.question_id or answer.question_id
    if not question_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This answer is not attached to a question, so there is no rubric "
            "to mark it against. Pass question_id.",
        )
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No question with that id.")

    try:
        evaluation = evaluation_service.evaluate_answer(
            db, answer, question, record, provider, samples=payload.samples
        )
    except EvaluationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return _evaluation_out(db, evaluation)


@router.get("/answers/{answer_id}/evaluations", response_model=list[EvaluationOut])
def list_answer_evaluations(
    answer_id: str, db: Session = Depends(get_db)
) -> list[EvaluationOut]:
    """Every marking run for one answer, newest first.

    More than one is normal: re-marking after a transcription correction, or
    after a rubric revision, writes a new row rather than replacing the old.
    """
    if db.get(Answer, answer_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No answer with that id.")
    return [
        _evaluation_out(db, record)
        for record in evaluation_service.evaluations_for_answer(db, answer_id)
    ]


@router.get("/evaluations", response_model=list[EvaluationOut])
def list_evaluations(
    needs_review: bool = Query(
        default=False,
        description="Only those whose confidence band asks for a human.",
    ),
    unreviewed: bool = Query(
        default=False, description="Only those no examiner has decided on yet."
    ),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[EvaluationOut]:
    """The marking queue, newest first.

    Only the latest evaluation per answer is listed: re-marking after a
    transcription fix writes a new row, and an examiner should be shown the
    current score rather than every attempt at it.
    """
    from sqlalchemy import select as sa_select

    records = list(
        db.scalars(sa_select(Evaluation).order_by(Evaluation.created_at.desc()))
    )

    latest_per_answer: dict[str, Evaluation] = {}
    for record in records:
        latest_per_answer.setdefault(record.answer_id, record)

    chosen = list(latest_per_answer.values())
    if needs_review:
        chosen = [r for r in chosen if r.review_band != ReviewBand.AUTO_ACCEPT]
    if unreviewed:
        chosen = [r for r in chosen if review_service.latest_review(db, r.id) is None]

    return [_evaluation_out(db, record) for record in chosen[:limit]]


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationOut)
def get_evaluation(evaluation_id: str, db: Session = Depends(get_db)) -> EvaluationOut:
    record = db.get(Evaluation, evaluation_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No evaluation with that id.")
    return _evaluation_out(db, record)


# ---------------------------------------------------------------------------
# Booklets
# ---------------------------------------------------------------------------


@router.get(
    "/documents/{document_ref}/segmentation", response_model=BookletSegmentationOut
)
def preview_segmentation(
    document_ref: str,
    exam_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BookletSegmentationOut:
    """Which part of a booklet answers which question, without marking it.

    Worth looking at before marking: if the split is wrong, every mark below
    it is wrong too, and this is the cheap place to catch that.
    """
    exam = _resolve_exam(db, exam_id)
    try:
        segments, leftover, warnings = evaluation_service.segment_booklet(
            db, document_ref, exam
        )
    except EvaluationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return BookletSegmentationOut(
        document_ref=document_ref,
        exam_id=exam.id,
        segments=[_segment_out(segment) for segment in segments],
        unmatched_text=leftover,
        warnings=warnings,
    )


@router.post(
    "/documents/evaluate",
    response_model=BookletResultOut,
    status_code=status.HTTP_201_CREATED,
)
def evaluate_booklet(
    payload: EvaluateBookletIn,
    db: Session = Depends(get_db),
    provider: EvaluationProvider = Depends(get_evaluation_provider),
) -> BookletResultOut:
    """Mark a whole transcribed booklet, question by question.

    The booklet must already be transcribed (POST /documents/transcribe). A
    question that cannot be marked is reported in `warnings` and the rest are
    marked anyway - one bad rubric must not cost a whole script.
    """
    started = time.perf_counter()
    exam = _resolve_exam(db, payload.exam_id)

    try:
        evaluations, segments, leftover, warnings = evaluation_service.evaluate_booklet(
            db,
            payload.document_ref,
            exam,
            provider,
            booklet_ref=payload.booklet_ref,
            samples=payload.samples,
        )
    except EvaluationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    totals = evaluation_service.booklet_totals(evaluations, segments)

    return BookletResultOut(
        document_ref=payload.document_ref,
        exam_id=exam.id,
        exam_title=exam.title,
        booklet_ref=payload.booklet_ref,
        total_score=float(totals["total_score"]),
        total_max=float(totals["total_max"]),
        percentage=float(totals["percentage"]),
        overall_confidence=float(totals["overall_confidence"]),
        review_band=str(totals["review_band"]),
        band_label=str(totals["band_label"]),
        questions_marked=len(evaluations),
        questions_total=len(segments),
        needs_review=list(totals["needs_review"]),
        evaluations=[_evaluation_out(db, record) for record in evaluations],
        segmentation=BookletSegmentationOut(
            document_ref=payload.document_ref,
            exam_id=exam.id,
            segments=[_segment_out(segment) for segment in segments],
            unmatched_text=leftover,
            warnings=warnings,
        ),
        duration_ms=int((time.perf_counter() - started) * 1000),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Examiner review - Part 4
# ---------------------------------------------------------------------------


@router.post("/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    payload: ReviewIn, db: Session = Depends(get_db)
) -> ReviewOut:
    """Record an examiner accepting or changing a machine score.

    Written as a new row. The machine score is never overwritten, which is
    what allows machine-examiner agreement to be measured afterwards.
    """
    evaluation = db.get(Evaluation, payload.evaluation_id)
    if evaluation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No evaluation with that id.")

    try:
        review = review_service.create_review(
            db,
            evaluation,
            action=payload.action,
            final_score=payload.final_score,
            comments=payload.comments,
            reviewer_id=payload.reviewer_id,
            duration_ms=payload.duration_ms,
        )
    except ReviewError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return _review_out(review)


@router.get("/evaluations/{evaluation_id}/reviews", response_model=list[ReviewOut])
def list_reviews(evaluation_id: str, db: Session = Depends(get_db)) -> list[ReviewOut]:
    if db.get(Evaluation, evaluation_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No evaluation with that id.")
    return [
        _review_out(review)
        for review in review_service.reviews_for_evaluation(db, evaluation_id)
    ]


@router.get("/analytics/summary", response_model=AnalyticsOut)
def analytics_summary(db: Session = Depends(get_db)) -> AnalyticsOut:
    """What has been measured so far, with its denominators.

    The `by_band` table is the one that matters: it shows whether the
    confidence bands actually predict examiner disagreement, which is the
    claim the whole confidence design rests on.
    """
    return analytics_service.summary(db)
