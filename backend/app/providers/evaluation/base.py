"""The marking provider boundary - Part 3.

The same rule as the OCR boundary holds: nothing above this layer imports a
vendor SDK, and nothing in this layer knows what a mark is worth.

### Why the model is never shown the marks

A provider receives the question, the answer key and the rubric criteria *with
the mark values stripped out*, and returns a verdict per criterion. The marks
are attached afterwards, in Python, by `evaluation_service`.

That is deliberate. A model told "this criterion is worth 2 of 5 marks"
anchors on the total it thinks the answer deserves and then distributes marks
to reach it - which produces a believable score with unbelievable reasoning,
and makes the criterion breakdown decorative. Hiding the marks forces every
judgement to stand on the criterion alone, and makes the arithmetic
reproducible: the same judgements always yield the same score, because a
deterministic function computes it.

It also means a marking run can be re-scored against a corrected rubric
without re-reading the answer.

### What a provider must return

One verdict per criterion, each carrying a quotation from the student's own
writing. The quotation is not decoration - `evaluation_service` checks it
really occurs in the transcription, and treats a fabricated quote as evidence
that the judgement cannot be trusted.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

# Verdicts a provider may return. Anything else is coerced to NOT_SATISFIED,
# because an unparseable verdict must never award marks.
SATISFIED = "satisfied"
PARTIAL = "partially_satisfied"
NOT_SATISFIED = "not_satisfied"
VERDICTS = (SATISFIED, PARTIAL, NOT_SATISFIED)


@dataclass
class CriterionSpec:
    """One rubric criterion, as the marker sees it - without its mark value."""

    position: int
    description: str
    essential_concepts: list[str] = field(default_factory=list)
    acceptable_alternatives: list[str] = field(default_factory=list)
    common_mistakes: list[str] = field(default_factory=list)
    # False means the criterion is all-or-nothing; the provider is told so,
    # and the scorer enforces it regardless of what comes back.
    allows_partial: bool = True


@dataclass
class MarkingTask:
    """Everything needed to judge one answer against one rubric."""

    question_number: str
    question_text: str
    question_type: str
    student_text: str
    criteria: list[CriterionSpec]
    answer_key: str | None = None
    # Marking conventions from the rubric: whether spelling is penalised, and
    # so on. Passed through to the prompt as instructions to the marker.
    rules: dict = field(default_factory=dict)


@dataclass
class CriterionJudgement:
    """A provider's verdict on one criterion."""

    position: int
    verdict: str
    # How much of the criterion the answer covers, 0-1. Only consulted for a
    # PARTIAL verdict; SATISFIED is 1.0 and NOT_SATISFIED is 0.0 by definition.
    coverage: float = 0.0
    reason: str = ""
    # The student's own words that justify this verdict, or None when the
    # provider found nothing to cite. Verified downstream.
    evidence_quote: str | None = None

    def normalised(self) -> "CriterionJudgement":
        """Coerce anything a model invented into the agreed contract."""
        verdict = (self.verdict or "").strip().lower().replace(" ", "_")
        if verdict in ("partial", "partially", "partly_satisfied"):
            verdict = PARTIAL
        if verdict in ("yes", "met", "correct", "full"):
            verdict = SATISFIED
        if verdict in ("no", "unmet", "incorrect", "none", "missing"):
            verdict = NOT_SATISFIED
        if verdict not in VERDICTS:
            verdict = NOT_SATISFIED

        coverage = float(self.coverage or 0.0)
        if verdict == SATISFIED:
            coverage = 1.0
        elif verdict == NOT_SATISFIED:
            coverage = 0.0
        coverage = max(0.0, min(1.0, coverage))

        return CriterionJudgement(
            position=self.position,
            verdict=verdict,
            coverage=coverage,
            reason=(self.reason or "").strip(),
            evidence_quote=(self.evidence_quote or None),
        )


@dataclass
class MarkingJudgement:
    """One complete reading of one answer. No marks anywhere in it."""

    criteria: list[CriterionJudgement] = field(default_factory=list)
    summary: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class EvaluatorInfo:
    name: str
    model_name: str
    model_version: str
    prompt_version: str
    is_ready: bool
    is_mock: bool
    detail: str


class EvaluationProvider(abc.ABC):
    """Judges an answer against a rubric. Knows nothing about marks."""

    name: str = "base"
    is_mock: bool = False

    @abc.abstractmethod
    def judge(self, task: MarkingTask, *, temperature: float = 0.0) -> MarkingJudgement:
        """Produce one independent reading of the answer.

        `temperature` exists so the service can request a second, genuinely
        independent reading and measure how far the two agree. A provider that
        is deterministic may ignore it, and should say so through `info()`.
        """

    @abc.abstractmethod
    def info(self) -> EvaluatorInfo:
        """Describe the marker for result metadata and the interface."""

    def warmup(self) -> None:
        return None
