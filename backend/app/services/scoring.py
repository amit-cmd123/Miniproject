"""Marks and confidence - the arithmetic the model is not allowed to do.

Every number a student is shown is computed here, in ordinary Python, from
verdicts a provider supplied. The module has no network access, no model and
no database, which is what makes it exhaustively testable: the same verdicts
always produce the same marks.

### Scoring

    satisfied            -> the criterion's full marks
    partially_satisfied  -> coverage x max_marks, snapped to the mark grid,
                            or zero if the criterion forbids partial credit
    not_satisfied        -> zero

The total is the sum, clamped to the question's maximum. Nothing else can add
a mark, so every mark in a score traces to exactly one criterion.

### Confidence

Four signals, each *measured* rather than asked for:

| Signal | What it measures | Why it matters |
|---|---|---|
| `transcription` | how well the handwriting was read | marks derived from text we misread are wrong no matter how good the marker is |
| `agreement` | how far two independent markings coincide | a verdict that changes between readings is a guess |
| `grounding` | whether cited quotations really occur in the answer | a fabricated quotation means the verdict was not read off the page |
| `decisiveness` | how far verdicts sit from the partial-credit boundary | a criterion judged exactly half-met is a coin flip |

They are combined as a **weighted geometric mean**, not an average. One signal
collapsing has to drag the result down: an answer marked from an unreadable
transcription is untrustworthy however confidently the marker agreed with
itself, and an arithmetic mean would hide that behind three good numbers.

Published work on automated grading found most marking errors originate in
transcription rather than judgement, which is why `transcription` carries the
joint-largest weight and enters the product directly.

**These weights are a starting hypothesis, not a calibrated result.** They are
recorded with every evaluation so that a validation study can fit them against
examiner agreement and replace them with measured values.
"""

from __future__ import annotations

import difflib
import math
from collections import Counter
from dataclasses import dataclass, field

from app.providers.evaluation.base import (
    NOT_SATISFIED,
    PARTIAL,
    SATISFIED,
    CriterionJudgement,
    MarkingJudgement,
)

# Weights of the four confidence signals. They sum to 1; when a signal cannot
# be measured its weight is redistributed across the rest.
WEIGHTS: dict[str, float] = {
    "transcription": 0.30,
    "agreement": 0.30,
    "grounding": 0.25,
    "decisiveness": 0.15,
}

# A zero in a geometric mean annihilates everything. Signals are floored here
# so that one failed measurement yields a very low confidence rather than a
# meaningless exact zero.
SIGNAL_FLOOR = 0.02

# Share of a quotation that must be found in the answer for it to count as
# real. Below 1.0 on purpose: the answer is an automatic transcription, so a
# genuine quotation can differ from it by a misread character or two.
GROUNDING_MATCH = 0.70

# A load-bearing criterion counts double when judging decisiveness: being
# unsure about the final answer matters more than being unsure about a
# supporting remark.
LOAD_BEARING_WEIGHT = 2.0


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------


def quantise(value: float, step: float) -> float:
    """Snap a mark onto the grid the paper is marked on (halves, usually)."""
    if step <= 0:
        return round(value, 4)
    return round(round(value / step) * step, 4)


def criterion_marks(
    verdict: str,
    coverage: float,
    max_marks: float,
    *,
    allows_partial: bool,
    step: float = 0.5,
) -> float:
    """Marks for one criterion. The only place a criterion mark is decided."""
    if verdict == SATISFIED:
        return round(max_marks, 4)
    if verdict == PARTIAL and allows_partial:
        awarded = quantise(max(0.0, min(1.0, coverage)) * max_marks, step)
        return round(min(awarded, max_marks), 4)
    return 0.0


# ---------------------------------------------------------------------------
# Consensus across independent readings
# ---------------------------------------------------------------------------


@dataclass
class Consensus:
    """The agreed judgement, and how much the readings actually agreed."""

    judgement: MarkingJudgement
    # None when only one reading was taken, so agreement was not measured.
    agreement: float | None
    samples: int
    # Criteria where the readings disagreed, for the examiner's attention.
    disputed: list[int] = field(default_factory=list)


def _verdict_rank(verdict: str) -> int:
    """Order verdicts so ties resolve towards the lower mark."""
    return {NOT_SATISFIED: 0, PARTIAL: 1, SATISFIED: 2}.get(verdict, 0)


def consensus(samples: list[MarkingJudgement]) -> Consensus:
    """Combine independent readings into one judgement plus an agreement score.

    The modal verdict wins. A tie resolves to the *lower* verdict: where the
    marker cannot make up its mind, the student is not given the benefit of a
    mark that a human has not seen - the low confidence that results routes
    the answer to review, where a human can award it.
    """
    if not samples:
        raise ValueError("Consensus needs at least one reading.")

    if len(samples) == 1:
        return Consensus(judgement=samples[0], agreement=None, samples=1)

    primary = samples[0]
    merged = MarkingJudgement(summary=primary.summary)
    for sample in samples:
        merged.warnings.extend(sample.warnings)

    scores: list[float] = []
    disputed: list[int] = []

    for criterion in primary.criteria:
        position = criterion.position
        verdicts: list[str] = []
        for sample in samples:
            match = next((c for c in sample.criteria if c.position == position), None)
            if match is not None:
                verdicts.append(match.verdict)

        if not verdicts:
            merged.criteria.append(criterion)
            scores.append(0.0)
            continue

        counts = Counter(verdicts)
        top = max(counts.values())
        # Tie -> lowest verdict, by the rule above.
        winner = min(
            (v for v, n in counts.items() if n == top), key=_verdict_rank
        )
        scores.append(top / len(verdicts))
        if top < len(verdicts):
            disputed.append(position)

        # Average coverage over the readings that reached the winning verdict,
        # and cite the first of them, so the quotation matches the verdict.
        agreeing = [
            c
            for sample in samples
            for c in sample.criteria
            if c.position == position and c.verdict == winner
        ]
        coverage = (
            sum(c.coverage for c in agreeing) / len(agreeing) if agreeing else 0.0
        )
        source = agreeing[0] if agreeing else criterion

        reason = source.reason
        if position in disputed:
            others = sorted(set(verdicts) - {winner})
            reason = (
                f"{reason} (The readings disagreed: "
                f"{top} of {len(verdicts)} said {winner.replace('_', ' ')}, "
                f"the rest said {', '.join(o.replace('_', ' ') for o in others)}.)"
            ).strip()

        merged.criteria.append(
            CriterionJudgement(
                position=position,
                verdict=winner,
                coverage=round(coverage, 4),
                reason=reason,
                evidence_quote=source.evidence_quote,
            )
        )

    return Consensus(
        judgement=merged,
        agreement=round(sum(scores) / len(scores), 4) if scores else None,
        samples=len(samples),
        disputed=disputed,
    )


# ---------------------------------------------------------------------------
# Evidence grounding
# ---------------------------------------------------------------------------


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def grounding_ratio(quote: str, answer: str) -> float:
    """How much of a quotation actually occurs in the answer, 0-1.

    An exact (whitespace- and case-insensitive) substring scores 1. Otherwise
    the matching blocks between the quotation and the answer are summed, so a
    quotation that survives a few misread characters still counts - but one the
    marker composed itself does not.
    """
    needle, haystack = _normalise(quote), _normalise(answer)
    if not needle or not haystack:
        return 0.0
    if needle in haystack:
        return 1.0

    matcher = difflib.SequenceMatcher(None, needle, haystack, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return round(min(1.0, matched / len(needle)), 4)


def evidence_grounding(
    judgement: MarkingJudgement, answer_text: str
) -> tuple[float, list[int]]:
    """Share of mark-bearing verdicts supported by a quotation we can find.

    Only verdicts that *award* something are checked. A criterion found absent
    needs no quotation - there is nothing to cite - so demanding one would
    punish a correct judgement. A criterion marked satisfied with no quotation
    at all counts as ungrounded: it awarded marks without showing where from.
    """
    checked = 0
    grounded = 0
    fabricated: list[int] = []

    for criterion in judgement.criteria:
        if criterion.verdict == NOT_SATISFIED:
            continue
        checked += 1
        if not criterion.evidence_quote:
            continue
        if grounding_ratio(criterion.evidence_quote, answer_text) >= GROUNDING_MATCH:
            grounded += 1
        else:
            fabricated.append(criterion.position)

    if checked == 0:
        # Nothing was awarded, so there is nothing to ground. Treat as neutral
        # rather than perfect: an all-zero score is its own kind of claim.
        return 1.0, fabricated
    return round(grounded / checked, 4), fabricated


# ---------------------------------------------------------------------------
# Decisiveness
# ---------------------------------------------------------------------------


def decisiveness(
    judgement: MarkingJudgement,
    marks_by_position: dict[int, float],
    load_bearing: set[int] | None = None,
) -> float:
    """How far the verdicts sit from the partial-credit boundary.

    A clear satisfied or not-satisfied is decisive. A partial verdict at 50%
    coverage is a coin flip and scores zero; one at 10% or 90% is nearly a
    clear call. Weighted by what each criterion is worth, and double-weighted
    where the criterion is load-bearing.
    """
    load_bearing = load_bearing or set()
    total_weight = 0.0
    total = 0.0

    for criterion in judgement.criteria:
        weight = max(marks_by_position.get(criterion.position, 1.0), 0.01)
        if criterion.position in load_bearing:
            weight *= LOAD_BEARING_WEIGHT

        if criterion.verdict == PARTIAL:
            value = 2.0 * abs(criterion.coverage - 0.5)
        else:
            value = 1.0

        total += value * weight
        total_weight += weight

    if total_weight == 0:
        return 1.0
    return round(total / total_weight, 4)


# ---------------------------------------------------------------------------
# Composite confidence
# ---------------------------------------------------------------------------


def composite_confidence(signals: dict[str, float | None]) -> tuple[float, dict]:
    """Weighted geometric mean of the available signals.

    A signal passed as None was not measurable; its weight is redistributed
    over the others and the result records that it was missing, so a
    confidence computed from three signals is never mistaken for one computed
    from four.
    """
    usable = {
        name: max(float(value), SIGNAL_FLOOR)
        for name, value in signals.items()
        if value is not None and name in WEIGHTS
    }
    missing = sorted(set(WEIGHTS) - set(usable))

    if not usable:
        return 0.0, {
            "signals": {},
            "weights": {},
            "unmeasured": sorted(WEIGHTS),
            "method": "weighted_geometric_mean",
            "note": "No confidence signal could be measured.",
        }

    weight_total = sum(WEIGHTS[name] for name in usable)
    weights = {name: WEIGHTS[name] / weight_total for name in usable}

    log_sum = sum(weights[name] * math.log(value) for name, value in usable.items())
    confidence = max(0.0, min(1.0, math.exp(log_sum)))

    return round(confidence, 4), {
        "signals": {name: round(float(value), 4) for name, value in signals.items()
                    if value is not None},
        "weights": {name: round(weight, 4) for name, weight in weights.items()},
        "unmeasured": missing,
        "method": "weighted_geometric_mean",
        "floor": SIGNAL_FLOOR,
        "note": (
            "Weights are an uncalibrated starting hypothesis, stored so a "
            "validation study can replace them with measured values."
        ),
    }
