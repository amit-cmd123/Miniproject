"""Editing the paper: adding, changing and deleting questions and rubrics.

These routes write institution-owned truth, so the tests are mostly about
what the application *refuses*. A rubric that does not sum to its question,
a duplicate question number, a deletion that would orphan a score already
awarded - each of those produces plausible-looking output and a wrong mark,
which is exactly the class of failure this project exists to prevent.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.db.models import Answer, OCRResult
from app.db.session import SessionLocal, init_db
from app.main import app
from app.schemas.enums import AnswerStatus


def criteria(*marks: float) -> list[dict]:
    """A minimal valid criterion list adding up to whatever is asked for."""
    return [
        {
            "position": index + 1,
            "description": f"Criterion number {index + 1} of this rubric",
            "max_marks": value,
            "essential_concepts": ["something"],
            "acceptable_alternatives": [],
            "common_mistakes": [],
            "allows_partial": True,
            "load_bearing": False,
        }
        for index, value in enumerate(marks)
    ]


class RubricEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.db = SessionLocal()
        self.exam = self.client.post(
            "/api/v1/exams",
            json={
                "title": "Editing fixture paper",
                "subject": "Computer Science",
                "subject_code": f"EDIT-{id(self):x}"[:20],
                "questions": [],
            },
        ).json()

    def tearDown(self) -> None:
        self.db.close()

    def exam_id(self) -> str:
        return self.exam["id"]

    def add(self, **overrides) -> dict:
        payload = {
            "number": "Q1",
            "text": "Explain what a pointer is in C.",
            "topic": "Pointers",
            "question_type": "theory",
            "max_marks": 5.0,
            "answer_key": "A pointer stores the address of another variable.",
            "rubric": {"criteria": criteria(2.0, 2.0, 1.0), "scoring_rules": {}},
        }
        payload.update(overrides)
        return self.client.post(
            f"/api/v1/exams/{self.exam_id()}/questions", json=payload
        )

    # -- adding ------------------------------------------------------------

    def test_a_question_can_be_added_with_its_rubric(self) -> None:
        response = self.add()
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()

        self.assertEqual(body["number"], "Q1")
        self.assertEqual(body["max_marks"], 5.0)
        self.assertTrue(body["has_rubric"])
        self.assertEqual(len(body["rubric"]["criteria"]), 3)
        self.assertEqual(body["rubric"]["version"], 1)
        self.assertEqual(body["rubric"]["total_criterion_marks"], 5.0)
        self.assertIn("address", body["answer_key"])

    def test_a_rubric_that_does_not_sum_is_refused(self) -> None:
        """The failure this guards against caps every student silently."""
        response = self.add(
            max_marks=5.0, rubric={"criteria": criteria(2.0, 2.0), "scoring_rules": {}}
        )
        self.assertEqual(response.status_code, 400, response.text)
        detail = response.json()["detail"]
        self.assertIn("4", detail)
        self.assertIn("5", detail)

    def test_two_criteria_at_the_same_position_are_refused(self) -> None:
        bad = criteria(2.5, 2.5)
        bad[1]["position"] = 1
        response = self.add(rubric={"criteria": bad, "scoring_rules": {}})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("position", response.json()["detail"].lower())

    def test_a_duplicate_question_number_is_refused(self) -> None:
        """Booklet splitting matches on the number, so they must be unique."""
        self.assertEqual(self.add().status_code, 201)
        clash = self.add(text="A different question entirely, same number.")
        self.assertEqual(clash.status_code, 409, clash.text)
        self.assertIn("Q1", clash.json()["detail"])

    def test_a_question_can_be_added_without_a_rubric(self) -> None:
        """Half-finished papers are normal; they just cannot be marked yet."""
        response = self.add(rubric=None, answer_key=None)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertFalse(response.json()["has_rubric"])

        validation = self.client.get(
            f"/api/v1/exams/{self.exam_id()}/validate"
        ).json()
        self.assertFalse(validation["is_valid"])
        self.assertTrue(validation["problems"])

    # -- editing -----------------------------------------------------------

    def test_wording_can_be_changed_without_touching_the_rubric(self) -> None:
        question = self.add().json()
        before = question["rubric"]["version"]

        response = self.client.patch(
            f"/api/v1/questions/{question['id']}",
            json={"text": "Describe pointers, with an example.", "topic": "Memory"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["text"], "Describe pointers, with an example.")
        self.assertEqual(body["topic"], "Memory")
        self.assertEqual(
            body["rubric"]["version"], before, "editing wording must not re-version"
        )

    def test_omitted_fields_are_left_alone(self) -> None:
        question = self.add().json()
        response = self.client.patch(
            f"/api/v1/questions/{question['id']}", json={"topic": "Only this"}
        )
        body = response.json()
        self.assertEqual(body["text"], question["text"])
        self.assertEqual(body["max_marks"], question["max_marks"])
        self.assertEqual(body["topic"], "Only this")

    def test_raising_the_marks_is_allowed_but_reported_as_invalid(self) -> None:
        """It must not silently rescale: what each criterion is now worth is
        an examiner's judgement, so the mismatch is surfaced instead."""
        question = self.add().json()
        response = self.client.patch(
            f"/api/v1/questions/{question['id']}", json={"max_marks": 8.0}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["max_marks"], 8.0)
        self.assertEqual(
            response.json()["rubric"]["total_criterion_marks"],
            5.0,
            "the criteria must be left exactly as they were",
        )

        validation = self.client.get(f"/api/v1/exams/{self.exam_id()}/validate").json()
        self.assertFalse(validation["is_valid"], "the mismatch must be reported")

    def test_renaming_onto_another_questions_number_is_refused(self) -> None:
        first = self.add().json()
        self.add(number="Q2", text="A second question on this paper.")
        response = self.client.patch(
            f"/api/v1/questions/{first['id']}", json={"number": "Q2"}
        )
        self.assertEqual(response.status_code, 409, response.text)

    # -- rubric versioning -------------------------------------------------

    def test_replacing_a_rubric_writes_a_new_version(self) -> None:
        question = self.add().json()
        response = self.client.put(
            f"/api/v1/questions/{question['id']}/rubric",
            json={"criteria": criteria(3.0, 2.0), "scoring_rules": {}},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["version"], 2)
        self.assertEqual(len(response.json()["criteria"]), 2)

    def test_the_history_keeps_every_version_and_marks_one_active(self) -> None:
        question = self.add().json()
        self.client.put(
            f"/api/v1/questions/{question['id']}/rubric",
            json={"criteria": criteria(3.0, 2.0), "scoring_rules": {}},
        )
        self.client.put(
            f"/api/v1/questions/{question['id']}/rubric",
            json={"criteria": criteria(5.0), "scoring_rules": {}},
        )

        versions = self.client.get(
            f"/api/v1/questions/{question['id']}/rubric/versions"
        ).json()
        self.assertEqual([v["version"] for v in versions], [3, 2, 1])
        self.assertEqual([v["is_active"] for v in versions].count(True), 1)
        self.assertTrue(versions[0]["is_active"], "newest is the active one")
        self.assertEqual(versions[0]["criteria_count"], 1)

    def test_a_replacement_rubric_must_also_sum(self) -> None:
        question = self.add().json()
        response = self.client.put(
            f"/api/v1/questions/{question['id']}/rubric",
            json={"criteria": criteria(1.0, 1.0), "scoring_rules": {}},
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_load_bearing_survives_the_round_trip(self) -> None:
        question = self.add().json()
        marked = criteria(3.0, 2.0)
        marked[0]["load_bearing"] = True
        response = self.client.put(
            f"/api/v1/questions/{question['id']}/rubric",
            json={"criteria": marked, "scoring_rules": {}},
        )
        self.assertEqual(response.status_code, 200, response.text)
        first = response.json()["criteria"][0]
        self.assertTrue(first["load_bearing"])

    # -- answer keys -------------------------------------------------------

    def test_an_answer_key_is_versioned_too(self) -> None:
        question = self.add().json()
        first = self.client.put(
            f"/api/v1/questions/{question['id']}/answer-key",
            json={"reference_answer": "A revised reference answer."},
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["version"], 2)

        second = self.client.put(
            f"/api/v1/questions/{question['id']}/answer-key",
            json={"reference_answer": "Revised once more."},
        )
        self.assertEqual(second.json()["version"], 3)

        current = self.client.get(
            f"/api/v1/questions/{question['id']}/answer-key"
        ).json()
        self.assertEqual(current["reference_answer"], "Revised once more.")
        self.assertTrue(current["is_active"])

    def test_an_empty_answer_key_is_refused(self) -> None:
        question = self.add().json()
        response = self.client.put(
            f"/api/v1/questions/{question['id']}/answer-key",
            json={"reference_answer": ""},
        )
        self.assertEqual(response.status_code, 422, response.text)

    # -- deleting ----------------------------------------------------------

    def test_an_unmarked_question_can_be_deleted(self) -> None:
        question = self.add().json()
        response = self.client.delete(f"/api/v1/questions/{question['id']}")
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(
            self.client.get(f"/api/v1/questions/{question['id']}").status_code, 404
        )

    def test_a_question_that_has_been_marked_cannot_be_deleted(self) -> None:
        """Deleting it would leave an awarded score citing a rubric that no
        longer exists - a mark nobody can explain to the student."""
        question = self.add().json()

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
                extracted_text="A pointer stores the address of another variable.",
                confidence=0.95,
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

        response = self.client.delete(f"/api/v1/questions/{question['id']}")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("marked", response.json()["detail"].lower())

    # -- export and import -------------------------------------------------

    def test_a_paper_round_trips_through_export_and_import(self) -> None:
        """A rubric that lives only in one laptop's database is not an
        institution-owned marking scheme, so it has to be exportable."""
        self.add()
        self.add(number="Q2", text="A second question.", max_marks=4.0,
                 rubric={"criteria": criteria(2.0, 2.0), "scoring_rules": {}})

        exported = self.client.get(f"/api/v1/exams/{self.exam_id()}/export")
        self.assertEqual(exported.status_code, 200, exported.text)
        document = exported.json()

        self.assertEqual(len(document["questions"]), 2)
        self.assertEqual(document["questions"][0]["number"], "Q1")
        # The seed format carries criteria directly on the question and the
        # paper's metadata under "exam"; the export has to match it exactly or
        # it cannot be fed back in.
        self.assertIn("criteria", document["questions"][0])
        self.assertIn("answer_key", document["questions"][0])
        self.assertEqual(document["exam"]["title"], "Editing fixture paper")
        self.assertEqual(len(document["questions"][0]["criteria"]), 3)

        document["exam"]["code"] = "ROUNDTRIP-1"
        document["exam"]["title"] = "Re-imported paper"
        imported = self.client.post("/api/v1/exams/import", json=document)
        self.assertEqual(imported.status_code, 201, imported.text)
        body = imported.json()

        self.assertEqual(body["question_count"], 2)
        self.assertEqual(body["total_marks"], 9.0)

        validation = self.client.get(f"/api/v1/exams/{body['id']}/validate").json()
        self.assertTrue(
            validation["is_valid"], f"re-imported paper is invalid: {validation}"
        )

    def test_importing_nonsense_is_a_message_not_a_crash(self) -> None:
        response = self.client.post(
            "/api/v1/exams/import", json={"not": "an exam at all"}
        )
        self.assertIn(response.status_code, (400, 422))
        self.assertIn("detail", response.json())

    # -- not found ---------------------------------------------------------

    def test_editing_an_unknown_question_is_404(self) -> None:
        self.assertEqual(
            self.client.patch("/api/v1/questions/nope", json={"topic": "x"}).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete("/api/v1/questions/nope").status_code, 404
        )
        self.assertEqual(
            self.client.get("/api/v1/questions/nope/rubric/versions").status_code, 404
        )

    def test_adding_to_an_unknown_exam_is_404(self) -> None:
        response = self.client.post(
            "/api/v1/exams/nope/questions",
            json={"text": "Anything at all here.", "max_marks": 2.0},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
