"""Tests for the arithmetic the model is not allowed to do.

`app.services.scoring` has no network, no model and no database, so every
claim the project makes about marks and confidence can be tested exhaustively
and deterministically. These are the tests that matter most: a bug here
produces wrong marks that look entirely reasonable.
"""

from __future__ import annotations

import unittest

from app.providers.evaluation.base import (
    NOT_SATISFIED,
    PARTIAL,
    SATISFIED,
    CriterionJudgement,
    MarkingJudgement,
)
from app.services import scoring


def judgement(*specs: tuple[int, str, float, str | None]) -> MarkingJudgement:
    """A judgement from (position, verdict, coverage, quote) tuples."""
    result = MarkingJudgement()
    for position, verdict, coverage, quote in specs:
        result.criteria.append(
            CriterionJudgement(
                position=position,
                verdict=verdict,
                coverage=coverage,
                reason="because",
                evidence_quote=quote,
            ).normalised()
        )
    return result


class QuantiseTests(unittest.TestCase):
    def test_snaps_to_the_half_mark_grid(self) -> None:
        self.assertEqual(scoring.quantise(1.26, 0.5), 1.5)
        self.assertEqual(scoring.quantise(1.24, 0.5), 1.0)
        self.assertEqual(scoring.quantise(0.2, 0.5), 0.0)

    def test_a_step_of_zero_leaves_the_value_alone(self) -> None:
        self.assertEqual(scoring.quantise(1.234, 0), 1.234)


class CriterionMarkTests(unittest.TestCase):
    def test_satisfied_awards_the_full_criterion(self) -> None:
        self.assertEqual(
            scoring.criterion_marks(SATISFIED, 1.0, 2.0, allows_partial=True), 2.0
        )

    def test_not_satisfied_awards_nothing(self) -> None:
        self.assertEqual(
            scoring.criterion_marks(NOT_SATISFIED, 0.9, 2.0, allows_partial=True), 0.0
        )

    def test_partial_is_coverage_times_the_maximum(self) -> None:
        self.assertEqual(
            scoring.criterion_marks(PARTIAL, 0.5, 2.0, allows_partial=True), 1.0
        )

    def test_partial_on_an_all_or_nothing_criterion_awards_nothing(self) -> None:
        """A half-stated fact is not half correct where the rubric says so."""
        self.assertEqual(
            scoring.criterion_marks(PARTIAL, 0.9, 2.0, allows_partial=False), 0.0
        )

    def test_a_criterion_can_never_exceed_its_maximum(self) -> None:
        # A provider returning coverage above 1 must not be able to inflate a mark.
        self.assertEqual(
            scoring.criterion_marks(PARTIAL, 5.0, 2.0, allows_partial=True), 2.0
        )

    def test_an_unknown_verdict_awards_nothing(self) -> None:
        """An unparseable verdict must lose a mark, never award one."""
        self.assertEqual(
            scoring.criterion_marks("probably?", 1.0, 2.0, allows_partial=True), 0.0
        )


class VerdictNormalisationTests(unittest.TestCase):
    def test_synonyms_are_accepted(self) -> None:
        for raw in ("Satisfied", "yes", "MET", "correct"):
            self.assertEqual(
                CriterionJudgement(position=1, verdict=raw).normalised().verdict,
                SATISFIED,
            )

    def test_nonsense_becomes_not_satisfied(self) -> None:
        self.assertEqual(
            CriterionJudgement(position=1, verdict="banana").normalised().verdict,
            NOT_SATISFIED,
        )

    def test_coverage_is_forced_to_match_the_verdict(self) -> None:
        satisfied = CriterionJudgement(position=1, verdict=SATISFIED, coverage=0.3)
        self.assertEqual(satisfied.normalised().coverage, 1.0)
        absent = CriterionJudgement(position=1, verdict=NOT_SATISFIED, coverage=0.8)
        self.assertEqual(absent.normalised().coverage, 0.0)


class ConsensusTests(unittest.TestCase):
    def test_one_reading_leaves_agreement_unmeasured(self) -> None:
        """One reading of the same thing measures nothing about agreement."""
        result = scoring.consensus([judgement((1, SATISFIED, 1.0, "x"))])
        self.assertIsNone(result.agreement)
        self.assertEqual(result.samples, 1)

    def test_identical_readings_agree_completely(self) -> None:
        one = judgement((1, SATISFIED, 1.0, "x"), (2, NOT_SATISFIED, 0.0, None))
        two = judgement((1, SATISFIED, 1.0, "x"), (2, NOT_SATISFIED, 0.0, None))
        result = scoring.consensus([one, two])
        self.assertEqual(result.agreement, 1.0)
        self.assertEqual(result.disputed, [])

    def test_disagreement_is_recorded_and_resolves_downwards(self) -> None:
        """A tie must not award a mark a human has not seen."""
        one = judgement((1, SATISFIED, 1.0, "x"))
        two = judgement((1, NOT_SATISFIED, 0.0, None))
        result = scoring.consensus([one, two])
        self.assertEqual(result.judgement.criteria[0].verdict, NOT_SATISFIED)
        self.assertEqual(result.agreement, 0.5)
        self.assertEqual(result.disputed, [1])

    def test_a_majority_wins(self) -> None:
        readings = [
            judgement((1, SATISFIED, 1.0, "x")),
            judgement((1, SATISFIED, 1.0, "x")),
            judgement((1, NOT_SATISFIED, 0.0, None)),
        ]
        result = scoring.consensus(readings)
        self.assertEqual(result.judgement.criteria[0].verdict, SATISFIED)
        self.assertAlmostEqual(result.agreement, 2 / 3, places=3)

    def test_the_disagreement_is_explained_in_the_reason(self) -> None:
        result = scoring.consensus(
            [judgement((1, SATISFIED, 1.0, "x")), judgement((1, PARTIAL, 0.5, "x"))]
        )
        self.assertIn("disagreed", result.judgement.criteria[0].reason)

    def test_partial_coverage_is_averaged_over_agreeing_readings(self) -> None:
        result = scoring.consensus(
            [judgement((1, PARTIAL, 0.4, "x")), judgement((1, PARTIAL, 0.8, "x"))]
        )
        self.assertAlmostEqual(result.judgement.criteria[0].coverage, 0.6, places=3)


class GroundingTests(unittest.TestCase):
    ANSWER = "a pointer is a variable which stores the address of another variable"

    def test_an_exact_quotation_is_fully_grounded(self) -> None:
        self.assertEqual(scoring.grounding_ratio("stores the address", self.ANSWER), 1.0)

    def test_case_and_spacing_do_not_matter(self) -> None:
        self.assertEqual(
            scoring.grounding_ratio("STORES   THE  ADDRESS", self.ANSWER), 1.0
        )

    def test_a_quotation_with_a_misread_character_still_counts(self) -> None:
        """The answer is an automatic transcription, so near-misses are real."""
        ratio = scoring.grounding_ratio("stores the addres5", self.ANSWER)
        self.assertGreaterEqual(ratio, scoring.GROUNDING_MATCH)

    def test_an_invented_quotation_is_not_grounded(self) -> None:
        ratio = scoring.grounding_ratio(
            "the student correctly explained pointer arithmetic in detail", self.ANSWER
        )
        self.assertLess(ratio, scoring.GROUNDING_MATCH)

    def test_awarding_marks_without_a_quotation_counts_as_ungrounded(self) -> None:
        value, fabricated = scoring.evidence_grounding(
            judgement((1, SATISFIED, 1.0, None)), self.ANSWER
        )
        self.assertEqual(value, 0.0)
        self.assertEqual(fabricated, [])

    def test_absent_criteria_need_no_quotation(self) -> None:
        """There is nothing to cite for a point the student never made."""
        value, _ = scoring.evidence_grounding(
            judgement((1, NOT_SATISFIED, 0.0, None)), self.ANSWER
        )
        self.assertEqual(value, 1.0)

    def test_a_fabricated_quotation_is_named(self) -> None:
        _, fabricated = scoring.evidence_grounding(
            judgement(
                (1, SATISFIED, 1.0, "stores the address"),
                (2, SATISFIED, 1.0, "explained recursion with a worked example"),
            ),
            self.ANSWER,
        )
        self.assertEqual(fabricated, [2])


class DecisivenessTests(unittest.TestCase):
    MARKS = {1: 2.0, 2: 1.0}

    def test_clear_verdicts_are_fully_decisive(self) -> None:
        value = scoring.decisiveness(
            judgement((1, SATISFIED, 1.0, "x"), (2, NOT_SATISFIED, 0.0, None)), self.MARKS
        )
        self.assertEqual(value, 1.0)

    def test_a_half_covered_partial_is_a_coin_flip(self) -> None:
        value = scoring.decisiveness(judgement((1, PARTIAL, 0.5, "x")), {1: 2.0})
        self.assertEqual(value, 0.0)

    def test_a_nearly_complete_partial_is_nearly_decisive(self) -> None:
        value = scoring.decisiveness(judgement((1, PARTIAL, 0.9, "x")), {1: 2.0})
        self.assertAlmostEqual(value, 0.8, places=3)

    def test_marks_weight_the_result(self) -> None:
        """Uncertainty on a 2-mark criterion matters more than on a 1-mark one."""
        heavy = scoring.decisiveness(
            judgement((1, PARTIAL, 0.5, "x"), (2, SATISFIED, 1.0, "y")), self.MARKS
        )
        light = scoring.decisiveness(
            judgement((1, SATISFIED, 1.0, "x"), (2, PARTIAL, 0.5, "y")), self.MARKS
        )
        self.assertLess(heavy, light)

    def test_a_load_bearing_criterion_counts_double(self) -> None:
        plain = scoring.decisiveness(
            judgement((1, PARTIAL, 0.5, "x"), (2, SATISFIED, 1.0, "y")), self.MARKS
        )
        weighted = scoring.decisiveness(
            judgement((1, PARTIAL, 0.5, "x"), (2, SATISFIED, 1.0, "y")),
            self.MARKS,
            load_bearing={1},
        )
        self.assertLess(weighted, plain)


class CompositeConfidenceTests(unittest.TestCase):
    ALL_GOOD = {
        "transcription": 0.95,
        "agreement": 1.0,
        "grounding": 1.0,
        "decisiveness": 1.0,
    }

    def test_everything_perfect_is_one(self) -> None:
        value, _ = scoring.composite_confidence(
            {name: 1.0 for name in scoring.WEIGHTS}
        )
        self.assertEqual(value, 1.0)

    def test_a_single_collapsed_signal_drags_the_whole_result_down(self) -> None:
        """The reason this is a geometric mean, not an average.

        A perfect marking of an unreadable transcription must not score well.
        An arithmetic mean of (0.02, 1, 1, 1) with these weights is about 0.71;
        the geometric mean is far lower, which is the honest answer.
        """
        signals = dict(self.ALL_GOOD)
        signals["transcription"] = 0.02
        value, _ = scoring.composite_confidence(signals)
        self.assertLess(value, 0.35)

    def test_an_unmeasured_signal_is_named_and_its_weight_redistributed(self) -> None:
        signals = dict(self.ALL_GOOD)
        signals["agreement"] = None
        value, detail = scoring.composite_confidence(signals)
        self.assertEqual(detail["unmeasured"], ["agreement"])
        self.assertAlmostEqual(sum(detail["weights"].values()), 1.0, places=6)
        self.assertNotIn("agreement", detail["weights"])
        self.assertGreater(value, 0.9)

    def test_a_zero_signal_does_not_annihilate_the_product(self) -> None:
        signals = dict(self.ALL_GOOD)
        signals["grounding"] = 0.0
        value, _ = scoring.composite_confidence(signals)
        self.assertGreater(value, 0.0)
        self.assertLess(value, 0.5)

    def test_no_measurable_signal_is_zero_and_says_so(self) -> None:
        value, detail = scoring.composite_confidence({name: None for name in scoring.WEIGHTS})
        self.assertEqual(value, 0.0)
        self.assertEqual(len(detail["unmeasured"]), len(scoring.WEIGHTS))

    def test_the_weights_sum_to_one(self) -> None:
        self.assertAlmostEqual(sum(scoring.WEIGHTS.values()), 1.0, places=6)

    def test_confidence_is_monotonic_in_each_signal(self) -> None:
        """Improving any one signal must never lower the confidence."""
        base, _ = scoring.composite_confidence(
            {name: 0.6 for name in scoring.WEIGHTS}
        )
        for name in scoring.WEIGHTS:
            better = {key: 0.6 for key in scoring.WEIGHTS}
            better[name] = 0.9
            value, _ = scoring.composite_confidence(better)
            self.assertGreater(value, base, f"raising {name} did not raise confidence")


if __name__ == "__main__":
    unittest.main()
