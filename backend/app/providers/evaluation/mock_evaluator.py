"""A deterministic stand-in marker.

Exists so that the whole pipeline - rubric, scoring, confidence, review,
analytics - can be exercised with no API key, no network and no cost, and so
that the tests covering it are reproducible.

It judges by keyword overlap: a criterion is satisfied when the answer
contains the words of one of its essential concepts, partially satisfied when
it contains some of them, not satisfied otherwise. That is a crude marker and
it is labelled as one; `is_mock` is true, the interface shows it, and every
result it produces records it as the provider.

It is useful for more than filling a gap. A keyword marker is the obvious
baseline any rubric-driven system should be measured against, so the
comparison "how much better is the model than counting words?" is available
by switching one setting.
"""

from __future__ import annotations

import re

from app.providers.evaluation.base import (
    NOT_SATISFIED,
    PARTIAL,
    SATISFIED,
    CriterionJudgement,
    EvaluationProvider,
    EvaluatorInfo,
    MarkingJudgement,
    MarkingTask,
)

PROMPT_VERSION = "keyword-overlap-v1"

# Words too common to be evidence of anything.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "it", "of", "on", "or", "that", "the", "then", "this", "to", "with", "we",
    "if", "its", "one", "will", "can", "which", "when", "there", "so", "not",
}


def tokens(text: str) -> set[str]:
    """Words and code symbols worth comparing."""
    words = re.findall(r"[a-zA-Z_][a-zA-Z_0-9]*|[0-9]+|[{}()\[\];=*&%<>+/-]+", text.lower())
    return {w for w in words if w not in STOPWORDS}


def overlap(concept: str, answer_tokens: set[str]) -> float:
    """Share of a concept's distinctive words present in the answer."""
    wanted = tokens(concept)
    if not wanted:
        return 0.0
    return len(wanted & answer_tokens) / len(wanted)


def _quote_for(concept: str, student_text: str) -> str | None:
    """The line of the answer that best matches a concept, as evidence."""
    best_line, best_score = None, 0.0
    for line in student_text.splitlines():
        if not line.strip():
            continue
        score = overlap(concept, tokens(line))
        if score > best_score:
            best_line, best_score = line.strip(), score
    return best_line if best_score > 0 else None


class MockEvaluationProvider(EvaluationProvider):
    name = "mock"
    is_mock = True

    # Thresholds on concept overlap. Deliberately generous on the partial
    # band: a baseline that never awards partial credit flatters the model
    # it is being compared against.
    SATISFIED_AT = 0.75
    PARTIAL_AT = 0.30

    def judge(self, task: MarkingTask, *, temperature: float = 0.0) -> MarkingJudgement:
        answer_tokens = tokens(task.student_text)
        judgement = MarkingJudgement()

        if not task.student_text.strip():
            for criterion in task.criteria:
                judgement.criteria.append(
                    CriterionJudgement(
                        position=criterion.position,
                        verdict=NOT_SATISFIED,
                        reason="The answer is empty.",
                    ).normalised()
                )
            judgement.summary = "No answer was written."
            return judgement

        for criterion in task.criteria:
            phrases = (
                list(criterion.essential_concepts)
                + list(criterion.acceptable_alternatives)
                or [criterion.description]
            )
            scores = [overlap(phrase, answer_tokens) for phrase in phrases]
            best = max(scores)
            matched = phrases[scores.index(best)]

            if best >= self.SATISFIED_AT:
                verdict, coverage = SATISFIED, 1.0
            elif best >= self.PARTIAL_AT and criterion.allows_partial:
                verdict, coverage = PARTIAL, round(best, 2)
            else:
                verdict, coverage = NOT_SATISFIED, 0.0

            judgement.criteria.append(
                CriterionJudgement(
                    position=criterion.position,
                    verdict=verdict,
                    coverage=coverage,
                    reason=(
                        f"Keyword overlap with '{matched}' was {best:.0%}."
                        if best > 0
                        else "None of the expected terms appear in the answer."
                    ),
                    evidence_quote=_quote_for(matched, task.student_text),
                ).normalised()
            )

        satisfied = sum(1 for c in judgement.criteria if c.verdict == SATISFIED)
        judgement.summary = (
            f"Keyword baseline: {satisfied} of {len(judgement.criteria)} criteria "
            f"matched outright."
        )
        judgement.warnings.append(
            "Marked by the keyword baseline, not a language model. These verdicts "
            "are a floor to compare against, not a result to report."
        )
        return judgement

    def info(self) -> EvaluatorInfo:
        return EvaluatorInfo(
            name=self.name,
            model_name="keyword-overlap",
            model_version="1.0",
            prompt_version=PROMPT_VERSION,
            is_ready=True,
            is_mock=True,
            detail=(
                "Deterministic keyword baseline. No network, no key, no cost. "
                "Used for tests and as the floor the model is measured against."
            ),
        )
