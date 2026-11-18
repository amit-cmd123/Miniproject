"""Every endpoint the interface calls must exist and answer.

The frontend keeps its types by hand, so a renamed route or a dropped field is
a runtime blank screen rather than a compile error. This walks the whole
sequence the interface performs - the same calls, in the same order - and
asserts the fields each view actually reads.

It is deliberately shallow on behaviour and strict on shape. Whether the marks
are right is tested in `test_evaluation.py` and `test_scoring.py`; what is
tested here is that the contract the interface was written against is the
contract the application serves.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.db.models import Answer, OCRResult
from app.db.session import SessionLocal, init_db
from app.main import app
from app.schemas.enums import AnswerStatus


class FrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.db = SessionLocal()

    def tearDown(self) -> None:
        self.db.close()

    def get(self, path: str) -> dict | list:
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, f"{path} -> {response.text[:200]}")
        return response.json()

    def assert_has(self, body: dict, *fields: str) -> None:
        missing = [field for field in fields if field not in body]
        self.assertEqual(missing, [], f"missing fields: {missing}")

    # -- header and configuration, read on every page load ----------------

    def test_shell_reads_the_engine_badge(self) -> None:
        body = self.get("/api/v1/ocr/provider")
        self.assert_has(body, "name", "model_name", "device", "is_ready", "is_mock",
                        "detail")

    def test_thresholds_and_weights_are_served(self) -> None:
        bands = self.get("/api/v1/config/thresholds")
        self.assertEqual(len(bands["transcription"]), 4)
        self.assertEqual(len(bands["evaluation"]), 4)

        weights = self.get("/api/v1/config/confidence-weights")
        self.assert_has(weights, "weights", "method", "signals", "note",
                        "grounding_match_threshold")

    def test_marker_info_is_served(self) -> None:
        body = self.get("/api/v1/evaluations/provider")
        self.assert_has(body, "name", "model_name", "prompt_version", "is_ready",
                        "is_mock", "detail")

    # -- the Rubrics view --------------------------------------------------

    def test_rubrics_view_sequence(self) -> None:
        """exams -> seed if empty -> exam detail -> validate."""
        exams = self.get("/api/v1/exams")
        if not exams:
            seeded = self.client.post("/api/v1/exams/seed")
            self.assertEqual(seeded.status_code, 200, seeded.text)
            exams = self.get("/api/v1/exams")
        self.assertTrue(exams)

        summary = exams[0]
        self.assert_has(summary, "id", "title", "subject", "subject_code",
                        "question_count", "total_marks", "created_at")

        detail = self.get(f"/api/v1/exams/{summary['id']}")
        self.assertTrue(detail["questions"])
        question = detail["questions"][0]
        self.assert_has(question, "id", "number", "text", "topic", "question_type",
                        "max_marks", "answer_key", "has_rubric", "rubric")

        rubric = question["rubric"]
        self.assertIsNotNone(rubric, "the view renders question.rubric inline")
        self.assert_has(rubric, "id", "version", "criteria", "total_criterion_marks",
                        "scoring_rules")
        criterion = rubric["criteria"][0]
        self.assert_has(criterion, "id", "position", "description", "max_marks",
                        "essential_concepts", "acceptable_alternatives",
                        "common_mistakes", "allows_partial", "load_bearing")

        validation = self.get(f"/api/v1/exams/{summary['id']}/validate")
        self.assert_has(validation, "is_valid", "questions_checked",
                        "criteria_checked", "total_marks", "problems")

    def test_rubric_endpoint_is_reachable_on_its_own(self) -> None:
        exams = self.get("/api/v1/exams") or [
            self.client.post("/api/v1/exams/seed").json()
        ]
        detail = self.get(f"/api/v1/exams/{exams[0]['id']}")
        question = detail["questions"][0]
        self.get(f"/api/v1/questions/{question['id']}/rubric")
        self.get(f"/api/v1/questions/{question['id']}")
        self.get(f"/api/v1/questions?exam_id={exams[0]['id']}&include_rubric=true")

    # -- the Evaluate view -------------------------------------------------

    def test_booklet_picker_has_the_fields_it_groups_by(self) -> None:
        """The view groups answers into booklets by document_ref and page_number."""
        answer = Answer(
            image_path="(fixture)",
            status=AnswerStatus.OCR_DONE,
            document_ref="doc-contract-test",
            page_number=1,
            source_filename="contract.pdf",
        )
        self.db.add(answer)
        self.db.commit()

        answers = self.get("/api/v1/answers")
        self.assertTrue(answers)
        self.assert_has(
            answers[0],
            "id", "question_id", "booklet_ref", "document_ref", "page_number",
            "source_filename", "original_filename", "status", "image_url",
            "created_at", "latest_ocr",
        )

    def test_marking_and_review_sequence(self) -> None:
        """evaluate -> queue -> review, with every field the views read."""
        exams = self.get("/api/v1/exams") or [
            self.client.post("/api/v1/exams/seed").json()
        ]
        detail = self.get(f"/api/v1/exams/{exams[0]['id']}")
        question = next(q for q in detail["questions"] if q["number"] == "Q2")

        answer = Answer(
            question_id=question["id"],
            image_path="(fixture)",
            status=AnswerStatus.OCR_DONE,
        )
        self.db.add(answer)
        self.db.flush()
        self.db.add(
            OCRResult(
                answer_id=answer.id,
                extracted_text="the output is 9, continue skips even values, 1 + 3 + 5",
                confidence=0.96,
                transcription_band="reliable",
                provider="test",
                model_name="fixture",
            )
        )
        self.db.commit()

        created = self.client.post(
            "/api/v1/evaluations", json={"answer_id": answer.id, "samples": 1}
        )
        self.assertEqual(created.status_code, 201, created.text)
        evaluation = created.json()

        self.assert_has(
            evaluation,
            "id", "answer_id", "question_id", "question_number", "rubric_version",
            "score", "max_score", "percentage", "confidence", "review_band",
            "band_label", "band_description", "needs_review",
            "overall_explanation", "confidence_signals", "criteria", "warnings",
            "provider", "model_name", "prompt_version", "text_source",
            "duration_ms", "created_at",
        )
        self.assert_has(
            evaluation["criteria"][0],
            "id", "position", "description", "awarded_marks", "max_marks",
            "verdict", "reason", "evidence_quote", "evidence_found",
        )
        # The confidence panel renders these four keys by name.
        signals = evaluation["confidence_signals"]
        self.assert_has(signals, "signals", "weights", "unmeasured", "samples")

        # The queue the review screen loads.
        queue = self.get("/api/v1/evaluations?unreviewed=true")
        self.assertIn(evaluation["id"], [item["id"] for item in queue])
        self.get("/api/v1/evaluations?needs_review=true")
        self.get(f"/api/v1/evaluations/{evaluation['id']}")
        self.get(f"/api/v1/answers/{answer.id}/evaluations")

        # Accepting it.
        review = self.client.post(
            "/api/v1/reviews",
            json={
                "evaluation_id": evaluation["id"],
                "action": "accept",
                "duration_ms": 4200,
            },
        )
        self.assertEqual(review.status_code, 201, review.text)
        self.assert_has(
            review.json(),
            "id", "answer_id", "evaluation_id", "action", "final_score",
            "ai_score_at_review", "delta", "comments", "duration_ms", "created_at",
        )
        self.get(f"/api/v1/evaluations/{evaluation['id']}/reviews")

        # And it leaves the unreviewed queue.
        after = self.get("/api/v1/evaluations?unreviewed=true")
        self.assertNotIn(evaluation["id"], [item["id"] for item in after])

    # -- the Validation view -----------------------------------------------

    def test_analytics_has_every_field_the_view_renders(self) -> None:
        body = self.get("/api/v1/analytics/summary")
        self.assert_has(
            body,
            "answers_uploaded", "answers_transcribed", "evaluations", "reviews",
            "mean_transcription_confidence", "mean_evaluation_confidence",
            "reviewed_evaluations", "exact_agreement", "within_half_mark",
            "mean_absolute_error", "by_band", "mean_review_seconds", "note",
        )
        self.assertEqual(len(body["by_band"]), 4, "every band is shown, even empty ones")
        self.assert_has(
            body["by_band"][0],
            "band", "label", "evaluations", "reviewed", "accepted", "modified",
            "modification_rate", "mean_absolute_delta",
        )

    # -- the Rubrics view's editing controls -------------------------------

    def test_the_rubric_editor_sequence(self) -> None:
        """add question -> edit it -> write a rubric -> history -> key -> delete.

        The editor is the only way to change a marking scheme without editing
        a JSON file and restarting, so every call it makes is pinned here.
        """
        exam = self.client.post(
            "/api/v1/exams",
            json={
                "title": "Contract editing paper",
                "subject": "Computer Science",
                "subject_code": "CONTRACT-EDIT",
                "questions": [],
            },
        )
        self.assertEqual(exam.status_code, 201, exam.text)
        exam_id = exam.json()["id"]

        created = self.client.post(
            f"/api/v1/exams/{exam_id}/questions",
            json={
                "number": "Q1",
                "text": "A question added through the editor.",
                "topic": "Testing",
                "question_type": "theory",
                "max_marks": 4.0,
                "answer_key": "A reference answer.",
                "rubric": None,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        question = created.json()
        self.assert_has(
            question,
            "id", "exam_id", "number", "text", "topic", "question_type",
            "max_marks", "answer_key", "has_rubric", "rubric", "created_at",
        )
        self.assertFalse(question["has_rubric"])

        patched = self.client.patch(
            f"/api/v1/questions/{question['id']}", json={"topic": "Edited"}
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["topic"], "Edited")

        saved = self.client.put(
            f"/api/v1/questions/{question['id']}/rubric",
            json={
                "marking_scheme": "A note for a human marker.",
                "scoring_rules": {},
                "criteria": [
                    {
                        "position": 1,
                        "description": "The first thing being tested here",
                        "max_marks": 2.5,
                        "essential_concepts": ["one"],
                        "acceptable_alternatives": ["uno"],
                        "common_mistakes": ["zero"],
                        "allows_partial": True,
                        "load_bearing": True,
                    },
                    {
                        "position": 2,
                        "description": "The second thing being tested here",
                        "max_marks": 1.5,
                        "essential_concepts": [],
                        "acceptable_alternatives": [],
                        "common_mistakes": [],
                        "allows_partial": False,
                        "load_bearing": False,
                    },
                ],
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        rubric = saved.json()
        self.assert_has(
            rubric, "id", "version", "criteria", "total_criterion_marks",
            "scoring_rules", "is_active", "marking_scheme",
        )
        self.assertEqual(rubric["total_criterion_marks"], 4.0)
        self.assertTrue(rubric["criteria"][0]["load_bearing"])
        self.assertFalse(rubric["criteria"][1]["allows_partial"])

        versions = self.get(f"/api/v1/questions/{question['id']}/rubric/versions")
        self.assertTrue(versions)
        self.assert_has(
            versions[0],
            "id", "version", "is_active", "criteria_count",
            "total_criterion_marks", "marking_scheme", "created_at",
        )

        key = self.client.put(
            f"/api/v1/questions/{question['id']}/answer-key",
            json={"reference_answer": "A revised reference answer."},
        )
        self.assertEqual(key.status_code, 200, key.text)
        self.assert_has(
            key.json(),
            "id", "question_id", "version", "is_active", "reference_answer",
            "created_at",
        )
        self.get(f"/api/v1/questions/{question['id']}/answer-key")

        exported = self.get(f"/api/v1/exams/{exam_id}/export")
        self.assertIn("questions", exported)
        self.assertIn("exam", exported)

        removed = self.client.delete(f"/api/v1/questions/{question['id']}")
        self.assertEqual(removed.status_code, 204, removed.text)

    def test_roadmap_drives_the_navigation_labels(self) -> None:
        body = self.get("/api/v1/roadmap")
        self.assertEqual(len(body["parts"]), 4)
        for part in body["parts"]:
            self.assert_has(part, "id", "name", "question", "status", "endpoints")

    # -- failure paths the interface shows a message for -------------------

    def test_a_missing_booklet_gives_a_message_not_a_crash(self) -> None:
        response = self.client.get("/api/v1/documents/no-such-ref/segmentation")
        self.assertIn(response.status_code, (404, 409, 422))
        self.assertIn("detail", response.json())

    def test_an_unknown_exam_is_404(self) -> None:
        self.assertEqual(self.client.get("/api/v1/exams/nope").status_code, 404)
        self.assertEqual(
            self.client.get("/api/v1/exams/nope/validate").status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
