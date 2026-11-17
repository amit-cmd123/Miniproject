"""Validation metrics - Part 4.

This module exists to let the project be wrong in public. Everything else in
EvalNova produces scores and confidences; this computes whether any of it
worked, from the rows the system wrote while being used.

The headline number is not accuracy. It is **the relationship between
confidence and examiner disagreement**, broken down by band. The design claim
is that a high-confidence score rarely needs changing and a low-confidence one
often does. If the modification rate is flat across the bands, the confidence
measure is not informative - no matter how principled its components look -
and `by_band` is where that shows up.

Every figure here is computed over reviewed evaluations only, and the count is
always reported beside the figure. An agreement rate over four reviews is not
evidence, and presenting it without its denominator would be the kind of
claim this module is meant to prevent.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.thresholds import EVALUATION_BANDS
from app.db.models import Answer, Evaluation, OCRResult, Review
from app.schemas.enums import ReviewAction
from app.schemas.evaluation import AnalyticsOut, BandAgreementOut

# A mark within this of the examiner's counts as agreement on a paper marked
# in half-marks. Reported separately from exact agreement, never instead of it.
HALF_MARK = 0.5
# Below this many reviews, a rate is noise. Still computed, but the note says so.
MEANINGFUL_SAMPLE = 20


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summary(db: Session) -> AnalyticsOut:
    """Everything measured so far, with its denominators attached."""
    answers_uploaded = db.scalar(select(func.count()).select_from(Answer)) or 0
    answers_transcribed = (
        db.scalar(select(func.count(func.distinct(OCRResult.answer_id)))) or 0
    )

    ocr_confidences = [
        float(value)
        for (value,) in db.execute(select(OCRResult.confidence)).all()
        if value is not None
    ]

    evaluations = list(db.scalars(select(Evaluation)))
    reviews = list(db.scalars(select(Review).order_by(Review.created_at)))

    # The latest review per evaluation is the decision that stands.
    latest: dict[str, Review] = {}
    for review in reviews:
        if review.evaluation_id:
            latest[review.evaluation_id] = review

    pairs: list[tuple[Evaluation, Review]] = [
        (evaluation, latest[evaluation.id])
        for evaluation in evaluations
        if evaluation.id in latest
    ]

    deltas = [abs(review.final_score - float(evaluation.score)) for evaluation, review in pairs]
    exact = sum(1 for d in deltas if d < 1e-6)
    within_half = sum(1 for d in deltas if d <= HALF_MARK + 1e-6)

    note_parts: list[str] = []
    if not pairs:
        note_parts.append(
            "No evaluation has been reviewed yet, so there is nothing to measure "
            "machine judgement against. Review some answers to populate this."
        )
    elif len(pairs) < MEANINGFUL_SAMPLE:
        note_parts.append(
            f"Only {len(pairs)} evaluation(s) have been reviewed. These figures "
            f"are an early indication, not a result - treat anything below "
            f"{MEANINGFUL_SAMPLE} reviews as noise."
        )
    if evaluations and any(e.provider == "mock" for e in evaluations):
        mock_count = sum(1 for e in evaluations if e.provider == "mock")
        note_parts.append(
            f"{mock_count} of {len(evaluations)} evaluations were produced by the "
            f"keyword baseline rather than a language model."
        )

    review_seconds = [r.duration_ms / 1000 for r in reviews if r.duration_ms > 0]

    return AnalyticsOut(
        answers_uploaded=answers_uploaded,
        answers_transcribed=answers_transcribed,
        evaluations=len(evaluations),
        reviews=len(reviews),
        mean_transcription_confidence=_mean(ocr_confidences),
        mean_evaluation_confidence=_mean([float(e.confidence) for e in evaluations]),
        reviewed_evaluations=len(pairs),
        exact_agreement=round(exact / len(pairs), 4) if pairs else None,
        within_half_mark=round(within_half / len(pairs), 4) if pairs else None,
        mean_absolute_error=_mean(deltas),
        by_band=_by_band(evaluations, latest),
        mean_review_seconds=_mean(review_seconds),
        note=" ".join(note_parts),
    )


def _by_band(
    evaluations: list[Evaluation], latest: dict[str, Review]
) -> list[BandAgreementOut]:
    """Does each confidence band predict whether a human changed the score?

    Reported for every band, including empty ones, so a band nothing has
    landed in is visibly untested rather than quietly absent.
    """
    rows: list[BandAgreementOut] = []

    for band in EVALUATION_BANDS:
        in_band = [e for e in evaluations if e.review_band == band.band]
        reviewed = [(e, latest[e.id]) for e in in_band if e.id in latest]

        modified = sum(
            1
            for _, review in reviewed
            if review.action == ReviewAction.MODIFY.value
            or abs(review.final_score - (review.ai_score_at_review or 0.0)) > 1e-6
        )
        accepted = len(reviewed) - modified
        deltas = [
            abs(review.final_score - float(evaluation.score))
            for evaluation, review in reviewed
        ]

        rows.append(
            BandAgreementOut(
                band=band.band,
                label=band.label,
                evaluations=len(in_band),
                reviewed=len(reviewed),
                accepted=accepted,
                modified=modified,
                modification_rate=(
                    round(modified / len(reviewed), 4) if reviewed else None
                ),
                mean_absolute_delta=_mean(deltas),
            )
        )
    return rows
