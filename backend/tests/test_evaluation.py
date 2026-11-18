"""Tests for Parts 2, 3 and 4: rubrics, marking, review and validation.

Run against the keyword baseline marker, so they are fast, free, offline and
deterministic. What they check is not whether the marker is clever - it is not
- but whether the machinery around it is correct: that a bad rubric is refused
rather than silently capping every student, that a booklet is split where the
student numbered it, that marks are traceable to criteria, and that a human
correction is stored beside the machine score instead of on top of it.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT
from app.db.models import Answer, OCRResult, Rubric
from app.db.session import SessionLocal, init_db
from app.main import app
from app.providers.evaluation.mock_evaluator import MockEvaluationProvider
from app.providers.segmentation import find_markers, split_by_markers
from app.schemas.enums import AnswerStatus
from app.services import rubric_service

SEED = REPO_ROOT / "data" / "exam" / "seed_exam.json"


class BookletSplittingTests(unittest.TestCase):
    """Finding where one answer stops and the next starts."""

    QUESTIONS = {1, 2, 3, 4, 5, 6}

    def test_q_prefixed_markers_are_found(self) -> None:
        lines = ["Q1", "a while loop checks first", "Q2", "the output is 9"]
        ranges, _ = split_by_markers(lines, self.QUESTIONS)
        self.assertEqual(ranges[1], (0, 2))
        self.assertEqual(ranges[2], (2, 4))

    def test_many_marker_spellings_are_accepted(self) -> None:
        for marker in ["Q3", "Q.3", "Q 3", "3)", "3.", "(3)", "Ans 3", "Answer 3:", "Ques 3"]:
            found = find_markers([marker, "some answer text"], self.QUESTIONS)
            self.assertEqual(
                [b.question_number for b in found], [3], f"failed on {marker!r}"
            )

    def test_the_marker_line_belongs_to_its_own_answer(self) -> None:
        """Students write the answer on the same line as the number."""
        lines = ["Q1 a while loop is entry controlled", "Q2 nine"]
        ranges, _ = split_by_markers(lines, self.QUESTIONS)
        self.assertEqual(ranges[1], (0, 1))

    def test_a_numbered_list_inside_an_answer_is_not_a_boundary(self) -> None:
        """The trap: '1. declare the variable' looks exactly like a marker."""
        lines = [
            "Q4",
            "1. declare the variables",
            "2. loop from 2 to n",
            "3. print the result",
            "Q5",
            "a pointer stores an address",
        ]
        ranges, _ = split_by_markers(lines, self.QUESTIONS)
        # Q4 must own its whole numbered list, not lose it to questions 1-3.
        self.assertEqual(ranges[4], (0, 4))
        self.assertEqual(ranges[5], (4, 6))
        self.assertNotIn(1, ranges)

    def test_markers_outside_the_paper_are_ignored(self) -> None:
        found = find_markers(["Q9 something"], self.QUESTIONS)
        self.assertEqual(found, [])

    def test_missing_questions_are_reported_not_invented(self) -> None:
        _, result = split_by_markers(["Q1", "answer"], self.QUESTIONS)
        self.assertTrue(any("2, 3, 4, 5, 6" in w for w in result.warnings))

    def test_no_markers_at_all_is_reported(self) -> None:
        ranges, result = split_by_markers(["just some prose", "and more"], self.QUESTIONS)
        self.assertEqual(ranges, {})
        self.assertTrue(result.warnings)


class RubricValidationTests(unittest.TestCase):
    """A rubric that does not add up must be refused, not applied."""

    def setUp(self) -> None:
        init_db()
        self.db = SessionLocal()

    def tearDown(self) -> None:
        self.db.close()

    def seed(self) -> object:
        document = json.loads(SEED.read_text(encoding="utf-8"))
        payload = rubric_service.exam_from_seed(document)
        payload.subject_code = f"TEST-{id(self)}"
        return rubric_service.create_exam(self.db, payload)

    def test_the_bundled_paper_is_valid(self) -> None:
        report = rubric_service.validate_exam(self.db, self.seed())
        errors = [p for p in report.problems if p.severity == "error"]
        self.assertTrue(report.is_valid, f"unexpected errors: {errors}")
        self.assertEqual(report.questions_checked, 6)
        self.assertEqual(report.total_marks, 30.0)

    def test_criteria_that_do_not_sum_to_the_question_are_an_error(self) -> None:
        exam = self.seed()
        question = rubric_service.questions_for(self.db, exam.id)[0]
        rubric = rubric_service.active_rubric(self.db, question.id)
        # Quietly cap every student at 90% of this question.
        rubric.criteria[0].max_marks -= 0.5
        self.db.commit()

        report = rubric_service.validate_exam(self.db, exam)
        self.assertFalse(report.is_valid)
        self.assertTrue(
            any("capped or over-awarded" in p.message for p in report.problems)
        )

    def test_the_bundled_paper_raises_no_warnings_either(self) -> None:
        """Every criterion has concepts, every question has a key, none dominates."""
        report = rubric_service.validate_exam(self.db, self.seed())
        self.assertEqual(report.problems, [])

    def test_a_criterion_worth_half_the_question_warns_without_blocking(self) -> None:
        """One judgement deciding half a question is worth saying out loud."""
        exam = self.seed()
        question = rubric_service.questions_for(self.db, exam.id)[0]
        rubric = rubric_service.active_rubric(self.db, question.id)

        # Move all the marks onto criterion 1: still sums correctly, so it is
        # valid, but the whole question now turns on a single verdict.
        rubric.criteria[0].max_marks = question.max_marks
        for criterion in rubric.criteria[1:]:
            criterion.max_marks = 0.0
        self.db.commit()

        report = rubric_service.validate_exam(self.db, exam)
        warnings = [p for p in report.problems if p.severity == "warning"]
        self.assertTrue(report.is_valid)
        self.assertTrue(
            any("decides half the question" in p.message for p in warnings),
            f"expected a dominance warning, got {[p.message for p in warnings]}",
        )

    def test_load_bearing_criteria_survive_the_round_trip(self) -> None:
        exam = self.seed()
        questions = rubric_service.questions_for(self.db, exam.id)
        q2 = next(q for q in questions if q.number == "Q2")
        rubric = rubric_service.active_rubric(self.db, q2.id)
        # The seed marks Q2 criterion 1 ("the output is 9") as load-bearing.
        self.assertEqual(rubric_service.load_bearing_positions(rubric), {1})

    def test_replacing_a_rubric_versions_it_rather_than_mutating_it(self) -> None:
        from app.schemas.rubrics import CriterionIn, RubricIn

        exam = self.seed()
        question = rubric_service.questions_for(self.db, exam.id)[0]
        first = rubric_service.active_rubric(self.db, question.id)

        replacement = RubricIn(
            criteria=[
                CriterionIn(
                    position=1,
                    description="Everything, in one criterion",
                    max_marks=question.max_marks,
                )
            ]
        )
        second = rubric_service.replace_rubric(self.db, question, replacement)

        self.assertEqual(second.version, first.version + 1)
        self.assertTrue(second.is_active)
        self.db.refresh(first)
        self.assertFalse(first.is_active)
        # The old rubric still exists, so an evaluation citing it still resolves.
        self.assertEqual(len(first.criteria), 4)


class MockMarkerTests(unittest.TestCase):
    """The keyword baseline, which is also the floor the model is measured against."""

    def setUp(self) -> None:
        self.provider = MockEvaluationProvider()

    def task(self, student_text: str):
        from app.providers.evaluation.base import CriterionSpec, MarkingTask

        return MarkingTask(
            question_number="Q5",
            question_text="What is a pointer?",
            question_type="theory",
            student_text=student_text,
            criteria=[
                CriterionSpec(
                    position=1,
                    description="States that a pointer stores the address of another variable",
                    essential_concepts=["stores an address", "of another variable"],
                )
            ],
        )

    def test_a_matching_answer_is_satisfied(self) -> None:
        result = self.provider.judge(
            self.task("a pointer stores an address of another variable")
        )
        self.assertEqual(result.criteria[0].verdict, "satisfied")

    def test_an_empty_answer_satisfies_nothing(self) -> None:
        result = self.provider.judge(self.task("   "))
        self.assertEqual(result.criteria[0].verdict, "not_satisfied")

    def test_it_labels_itself_as_a_baseline(self) -> None:
        self.assertTrue(self.provider.info().is_mock)
        result = self.provider.judge(self.task("a pointer stores an address"))
        self.assertTrue(any("baseline" in w for w in result.warnings))

    def test_evidence_is_quoted_from_the_answer_itself(self) -> None:
        answer = "int x = 10;\na pointer stores an address of another variable"
        result = self.provider.judge(self.task(answer))
        quote = result.criteria[0].evidence_quote
        self.assertIsNotNone(quote)
        self.assertIn(quote, answer)


class EndToEndMarkingTests(unittest.TestCase):
    """Upload text, mark it, review it, and read the validation metrics."""

    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)
        cls.exam = cls.client.post("/api/v1/exams/seed").json()

    def setUp(self) -> None:
        self.db = SessionLocal()

    def tearDown(self) -> None:
        self.db.close()

    def question(self, number: str) -> dict:
        return next(q for q in self.exam["questions"] if q["number"] == number)

    def answer_with_text(self, text: str, question_id: str) -> str:
        """A transcribed answer, written straight to the database.

        Going through an image upload would test the recognition pipeline,
        which has its own tests; this isolates marking from transcription.
        """
        answer = Answer(
            question_id=question_id,
            image_path="(none - test fixture)",
            status=AnswerStatus.OCR_DONE,
        )
        self.db.add(answer)
        self.db.flush()
        self.db.add(
            OCRResult(
                answer_id=answer.id,
                extracted_text=text,
                confidence=0.97,
                transcription_band="reliable",
                needs_verification=False,
                line_count=len(text.splitlines()),
                word_count=len(text.split()),
                provider="test",
                model_name="fixture",
            )
        )
        self.db.commit()
        return answer.id

    def test_the_seeded_paper_validates(self) -> None:
        report = self.client.get(f"/api/v1/exams/{self.exam['id']}/validate").json()
        self.assertTrue(report["is_valid"])
        self.assertEqual(report["total_marks"], 30.0)

    def test_seeding_twice_does_not_duplicate_the_paper(self) -> None:
        again = self.client.post("/api/v1/exams/seed").json()
        self.assertEqual(again["id"], self.exam["id"])
        # Counted by subject code: other test classes create their own exams
        # in the same scratch database.
        same_code = [
            exam
            for exam in self.client.get("/api/v1/exams").json()
            if exam["subject_code"] == self.exam["subject_code"]
        ]
        self.assertEqual(len(same_code), 1)

    def test_a_good_answer_scores_and_explains_every_mark(self) -> None:
        q5 = self.question("Q5")
        answer_id = self.answer_with_text(
            "a pointer stores an address of another variable\n"
            "the & gives the address\n"
            "the * gives the value at that address\n"
            "int x = 10; int *p = &x; printf(*p);",
            q5["id"],
        )
        result = self.client.post(
            "/api/v1/evaluations", json={"answer_id": answer_id, "samples": 1}
        )
        self.assertEqual(result.status_code, 201, result.text)
        body = result.json()

        self.assertEqual(body["max_score"], 5.0)
        self.assertGreater(body["score"], 0.0)
        self.assertLessEqual(body["score"], 5.0)

        # Every mark traces to exactly one criterion, and the parts sum to the whole.
        self.assertEqual(len(body["criteria"]), 4)
        self.assertAlmostEqual(
            sum(c["awarded_marks"] for c in body["criteria"]), body["score"], places=3
        )
        for criterion in body["criteria"]:
            self.assertTrue(criterion["reason"])

    def test_an_empty_transcription_is_refused_rather_than_scored_zero(self) -> None:
        """A score of zero and 'there was nothing to mark' are different facts."""
        answer_id = self.answer_with_text("   ", self.question("Q1")["id"])
        result = self.client.post("/api/v1/evaluations", json={"answer_id": answer_id})
        self.assertEqual(result.status_code, 422)
        self.assertIn("nothing", result.json()["detail"].lower())

    def test_marking_needs_a_question(self) -> None:
        answer = Answer(image_path="(none)", status=AnswerStatus.OCR_DONE)
        self.db.add(answer)
        self.db.flush()
        self.db.add(
            OCRResult(
                answer_id=answer.id,
                extracted_text="some words",
                confidence=0.9,
                transcription_band="spot_check",
                provider="test",
                model_name="fixture",
            )
        )
        self.db.commit()

        result = self.client.post("/api/v1/evaluations", json={"answer_id": answer.id})
        self.assertEqual(result.status_code, 400)
        self.assertIn("question_id", result.json()["detail"])

    def test_a_rubric_that_does_not_add_up_blocks_marking(self) -> None:
        q1 = self.question("Q1")
        rubric_id = self.client.get(f"/api/v1/questions/{q1['id']}/rubric").json()["id"]
        rubric = self.db.get(Rubric, rubric_id)
        original = rubric.criteria[0].max_marks
        rubric.criteria[0].max_marks = original - 0.5
        self.db.commit()
        try:
            answer_id = self.answer_with_text("a while loop checks first", q1["id"])
            result = self.client.post(
                "/api/v1/evaluations", json={"answer_id": answer_id, "samples": 1}
            )
            self.assertEqual(result.status_code, 422)
            self.assertIn("rubric", result.json()["detail"].lower())
        finally:
            rubric.criteria[0].max_marks = original
            self.db.commit()

    def test_review_is_appended_and_the_machine_score_survives(self) -> None:
        q2 = self.question("Q2")
        answer_id = self.answer_with_text(
            "the output is 9 because continue skips even values, 1 + 3 + 5 = 9",
            q2["id"],
        )
        evaluation = self.client.post(
            "/api/v1/evaluations", json={"answer_id": answer_id, "samples": 1}
        ).json()
        machine_score = evaluation["score"]

        review = self.client.post(
            "/api/v1/reviews",
            json={
                "evaluation_id": evaluation["id"],
                "action": "modify",
                "final_score": 5.0,
                "comments": "Fully correct; the baseline missed the explanation.",
                "duration_ms": 12_000,
            },
        )
        self.assertEqual(review.status_code, 201, review.text)
        self.assertEqual(review.json()["final_score"], 5.0)
        self.assertEqual(review.json()["ai_score_at_review"], machine_score)

        # The machine's own score is untouched - that is what makes the
        # agreement measurement possible at all.
        unchanged = self.client.get(f"/api/v1/evaluations/{evaluation['id']}").json()
        self.assertEqual(unchanged["score"], machine_score)

    def test_an_accepted_score_cannot_quietly_differ(self) -> None:
        q3 = self.question("Q3")
        answer_id = self.answer_with_text("missing semicolon", q3["id"])
        evaluation = self.client.post(
            "/api/v1/evaluations", json={"answer_id": answer_id, "samples": 1}
        ).json()
        result = self.client.post(
            "/api/v1/reviews",
            json={
                "evaluation_id": evaluation["id"],
                "action": "accept",
                "final_score": evaluation["score"] + 1,
            },
        )
        self.assertEqual(result.status_code, 400)

    def test_a_score_outside_the_question_is_refused(self) -> None:
        q3 = self.question("Q3")
        answer_id = self.answer_with_text("missing semicolon", q3["id"])
        evaluation = self.client.post(
            "/api/v1/evaluations", json={"answer_id": answer_id, "samples": 1}
        ).json()
        result = self.client.post(
            "/api/v1/reviews",
            json={"evaluation_id": evaluation["id"], "action": "modify", "final_score": 9},
        )
        self.assertEqual(result.status_code, 400)
        self.assertIn("outside the range", result.json()["detail"])

    def test_analytics_report_their_own_sample_size(self) -> None:
        body = self.client.get("/api/v1/analytics/summary").json()
        self.assertGreater(body["evaluations"], 0)
        self.assertEqual(len(body["by_band"]), 4)
        # With a handful of reviews the note must say the figures are not a result.
        self.assertTrue(body["note"])
        self.assertIn("baseline", body["note"])

    def test_confidence_weights_are_served_and_declared_uncalibrated(self) -> None:
        body = self.client.get("/api/v1/config/confidence-weights").json()
        self.assertAlmostEqual(sum(body["weights"].values()), 1.0, places=6)
        self.assertIn("ncalibrated", body["note"])

    def test_one_reading_records_agreement_as_unmeasured(self) -> None:
        q6 = self.question("Q6")
        answer_id = self.answer_with_text("max = arr[0]; loop; return max;", q6["id"])
        body = self.client.post(
            "/api/v1/evaluations", json={"answer_id": answer_id, "samples": 1}
        ).json()
        self.assertIn("agreement", body["confidence_signals"]["unmeasured"])
        self.assertEqual(body["confidence_signals"]["samples"], 1)


if __name__ == "__main__":
    unittest.main()
