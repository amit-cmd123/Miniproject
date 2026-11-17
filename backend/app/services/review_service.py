"""Examiner review - Part 4's service layer.

One rule governs this entire file: **a human decision is a new row, never an
edit.** `Evaluation` is append-only and so is `Review`, so after an examiner
has worked, the database still holds what the machine said, what the human
said, and the difference between them.

That is not bookkeeping fussiness. The whole claim of this project - that
confidence predicts when a human is needed - can only be tested against pairs
of (machine score, human score). A system that overwrote the machine score to
show the corrected one would destroy its own evidence on first use, and would
do so invisibly.

The second consequence is that every examiner correction is free training and
calibration data, collected as a by-product of work the examiner had to do
anyway.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Answer, Evaluation, Review
from app.schemas.enums import AnswerStatus, ReviewAction
from app.services import audit

logger = logging.getLogger(__name__)


class ReviewError(ValueError):
    """The review cannot be recorded. Message is shown to the examiner."""


def create_review(
    db: Session,
    evaluation: Evaluation,
    *,
    action: ReviewAction,
    final_score: float | None,
    comments: str | None = None,
    reviewer_id: str | None = None,
    duration_ms: int = 0,
) -> Review:
    """Record an examiner's decision on one evaluation."""
    if action == ReviewAction.ACCEPT:
        score = float(evaluation.score)
        if final_score is not None and abs(final_score - score) > 1e-6:
            raise ReviewError(
                f"An accepted score cannot differ from the machine score "
                f"({score:g}). Use 'modify' to change it."
            )
    else:
        if final_score is None:
            raise ReviewError("A modified score needs a final_score.")
        score = float(final_score)
        if score < 0 or score > evaluation.max_score:
            raise ReviewError(
                f"A score of {score:g} is outside the range for this question "
                f"(0 to {evaluation.max_score:g})."
            )

    review = Review(
        answer_id=evaluation.answer_id,
        evaluation_id=evaluation.id,
        reviewer_id=reviewer_id,
        action=action.value if isinstance(action, ReviewAction) else str(action),
        final_score=round(score, 4),
        # Captured at review time, so a later re-marking of the same answer
        # cannot retrospectively change what the examiner was shown.
        ai_score_at_review=float(evaluation.score),
        comments=comments,
        duration_ms=max(0, int(duration_ms)),
    )
    db.add(review)

    answer = db.get(Answer, evaluation.answer_id)
    if answer is not None:
        answer.status = AnswerStatus.FINALIZED

    db.commit()
    db.refresh(review)

    audit.record(
        db,
        action=f"review.{review.action}",
        object_type="evaluation",
        object_id=evaluation.id,
        actor_id=reviewer_id,
        details={
            "machine_score": float(evaluation.score),
            "final_score": review.final_score,
            "delta": round(review.final_score - float(evaluation.score), 4),
            "confidence": float(evaluation.confidence),
            "band": evaluation.review_band,
            "seconds": round(review.duration_ms / 1000, 1),
        },
    )
    return review


def reviews_for_evaluation(db: Session, evaluation_id: str) -> list[Review]:
    return list(
        db.scalars(
            select(Review)
            .where(Review.evaluation_id == evaluation_id)
            .order_by(Review.created_at.desc())
        )
    )


def latest_review(db: Session, evaluation_id: str) -> Review | None:
    """The examiner's most recent decision, which is the one that stands."""
    return db.scalars(
        select(Review)
        .where(Review.evaluation_id == evaluation_id)
        .order_by(Review.created_at.desc())
        .limit(1)
    ).first()


def final_score_for(db: Session, evaluation: Evaluation) -> tuple[float, str]:
    """The score of record for one evaluation, and where it came from.

    An examiner's decision supersedes the machine's. Where none exists the
    machine score stands, and is labelled as unreviewed rather than final.
    """
    review = latest_review(db, evaluation.id)
    if review is not None:
        return review.final_score, "examiner"
    return float(evaluation.score), "machine_unreviewed"
