"""Importing a typed marking scheme, and choosing which engine runs.

Two features share this file because they share a motivation: an examiner
should be able to bring their own paper in the format they already have it in,
and should be able to say which engine reads it, without editing a config file
or restarting anything.

The fixtures build real `.docx` and `.pdf` bytes rather than mocking the
extractors. A Word file is a zip of XML and a PDF can be written by the
library already in the requirements, so there is no reason to test against a
pretend one - and the bugs worth catching here (a table row whose mark lands
on the wrong criterion, a heading swallowed into a question) only exist in the
real formats.
"""

from __future__ import annotations

import unittest
import zipfile
from io import BytesIO

from fastapi.testclient import TestClient

from app.db.session import init_db
from app.main import app
from app.services import document_text
from app.services.document_text import DocumentTextError
from app.services.rubric_import import RubricImportError, parse_locally

# The TestClient does not run the application's startup hook, so the
# tables have to be created before any endpoint that touches them.
init_db()
client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DOCX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _para(text: str) -> str:
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def _table(rows: list[list[str]]) -> str:
    cells = "".join(
        "<w:tr>"
        + "".join(f"<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>" for cell in row)
        + "</w:tr>"
        for row in rows
    )
    return f"<w:tbl>{cells}</w:tbl>"


def make_docx(body: str) -> bytes:
    """A minimal but genuine .docx: a zip holding word/document.xml."""
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {_W}><w:body>{body}</w:body></w:document>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("_rels/.rels", _DOCX_RELS)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def make_pdf(lines: list[str]) -> bytes:
    from app.services.pdf_service import _pymupdf

    fitz = _pymupdf()
    document = fitz.open()
    page = document.new_page()
    y = 72.0
    for line in lines:
        page.insert_text((60, y), line, fontsize=11)
        y += 18
    data = document.tobytes()
    document.close()
    return data


PAPER_BODY = (
    _para("Mini Project Class Test")
    + _para("Subject: Programming in C")
    + _para("Subject Code: TEST-IMP-01")
    + _para("Q1. State the difference between a while loop and a do-while loop. (5 marks)")
    + _table(
        [
            ["Criterion", "Marks"],
            ["States that while checks the condition before the body", "2"],
            ["States that do-while checks the condition after the body", "2"],
            ["Gives a situation where do-while is better", "1"],
        ]
    )
    + _para("Q2. Write a program to find the largest of three numbers. (5 marks)")
    + _para("- Declares the variables correctly (1)")
    + _para("- Reads input with scanf (2)")
    + _para("- Prints the largest value (2)")
)


# ---------------------------------------------------------------------------
# Extracting text
# ---------------------------------------------------------------------------


class DocumentTextTests(unittest.TestCase):
    def test_a_word_table_survives_as_rows(self) -> None:
        """The criterion and its mark must stay on one line.

        Pulling every <w:t> in file order would put "2" on its own line, and
        no parser downstream could tell which criterion it belonged to.
        """
        extracted = document_text.extract(make_docx(PAPER_BODY), "paper.docx")

        self.assertEqual(extracted.kind, "docx")
        self.assertEqual(extracted.table_count, 1)
        self.assertIn(
            "| States that while checks the condition before the body | 2 |",
            extracted.text,
        )

    def test_a_word_table_stays_where_it_was(self) -> None:
        """Document order decides which question a table belongs to."""
        text = document_text.extract(make_docx(PAPER_BODY), "p.docx").text
        self.assertLess(text.index("Q1."), text.index("| States that while"))
        self.assertLess(text.index("| Gives a situation"), text.index("Q2."))

    def test_a_pdf_with_text_is_read(self) -> None:
        data = make_pdf(["Subject: Physics", "Q1. State Newton's second law. (4 marks)"])
        extracted = document_text.extract(data, "paper.pdf")
        self.assertEqual(extracted.kind, "pdf")
        self.assertIn("Newton", extracted.text)

    def test_a_scanned_pdf_is_refused_rather_than_guessed_at(self) -> None:
        """A page with no text layer must say so, not return three characters."""
        from app.services.pdf_service import _pymupdf

        fitz = _pymupdf()
        document = fitz.open()
        document.new_page()
        blank = document.tobytes()
        document.close()

        with self.assertRaises(DocumentTextError) as caught:
            document_text.extract(blank, "scan.pdf")
        self.assertIn("no readable text", str(caught.exception).lower())

    def test_the_old_doc_format_is_named_in_the_error(self) -> None:
        with self.assertRaises(DocumentTextError) as caught:
            document_text.extract(b"\xd0\xcf\x11\xe0junk", "old.doc")
        self.assertIn(".docx", str(caught.exception))

    def test_an_unsupported_file_is_refused(self) -> None:
        with self.assertRaises(DocumentTextError):
            document_text.extract(b"\x89PNG\r\n\x1a\n" + b"0" * 200, "sheet.png")

    def test_smart_punctuation_is_normalised(self) -> None:
        body = _para("Q1. Explain the “break” statement – fully. (3 marks)")
        text = document_text.extract(make_docx(body), "p.docx").text
        self.assertNotIn("“", text)
        self.assertNotIn("–", text)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class LocalParserTests(unittest.TestCase):
    def parse(self, text: str):
        return parse_locally(text)

    def test_bulleted_criteria_with_dot_leaders(self) -> None:
        parsed = self.parse(
            "Subject: Programming in C\n"
            "Q1. Explain a while loop. (5 marks)\n"
            " - Checks the condition first ... 2\n"
            " - Syntax is correct ... 2\n"
            " - Gives an example ... 1\n"
        )
        question = parsed.seed["questions"][0]
        self.assertEqual(question["max_marks"], 5)
        self.assertEqual([c["max_marks"] for c in question["criteria"]], [2, 2, 1])
        self.assertEqual(
            question["criteria"][0]["description"], "Checks the condition first"
        )

    def test_a_marks_column_binds_to_its_own_row(self) -> None:
        parsed = self.parse(
            "Q1. Define a stack. (6 marks)\n"
            "| Sr No | Criterion | Marks |\n"
            "| 1 | Defines stack as LIFO | 2 |\n"
            "| 2 | Lists push and pop | 3 |\n"
            "| 3 | Mentions peek | 1 |\n"
        )
        criteria = parsed.seed["questions"][0]["criteria"]
        self.assertEqual(
            [(c["description"], c["max_marks"]) for c in criteria],
            [
                ("Defines stack as LIFO", 2),
                ("Lists push and pop", 3),
                ("Mentions peek", 1),
            ],
        )

    def test_a_table_header_is_not_imported_as_a_criterion(self) -> None:
        parsed = self.parse(
            "Q1. Define a stack. (4 marks)\n"
            "| Criterion | Marks |\n"
            "| Defines stack as LIFO | 4 |\n"
        )
        criteria = parsed.seed["questions"][0]["criteria"]
        self.assertEqual(len(criteria), 1)

    def test_a_table_header_is_not_glued_onto_the_question(self) -> None:
        """The bug this guards: 'Define a stack | Sr No | Criterion | Marks |'."""
        parsed = self.parse(
            "Q1. Define a stack. (4 marks)\n"
            "| Sr No | Criterion | Marks |\n"
            "| 1 | Defines stack as LIFO | 4 |\n"
        )
        self.assertEqual(parsed.seed["questions"][0]["text"], "Define a stack")

    def test_tab_separated_criteria(self) -> None:
        parsed = self.parse(
            "Q1 What is a deadlock? (4 marks)\n"
            "Defines deadlock as circular wait\t2\n"
            "Names the four conditions\t2\n"
        )
        criteria = parsed.seed["questions"][0]["criteria"]
        self.assertEqual([c["max_marks"] for c in criteria], [2, 2])

    def test_lettered_criteria_keep_their_trailing_marks(self) -> None:
        parsed = self.parse(
            "Q1. Explain break. (7 marks)\n"
            "a) Defines break as exiting the loop - 3\n"
            "b) Gives an example - 2\n"
            "c) Notes it exits one level only - 2\n"
        )
        criteria = parsed.seed["questions"][0]["criteria"]
        self.assertEqual([c["max_marks"] for c in criteria], [3, 2, 2])
        self.assertEqual(
            criteria[0]["description"], "Defines break as exiting the loop"
        )

    def test_exam_metadata_is_picked_up(self) -> None:
        parsed = self.parse(
            "Mini Project Class Test\n"
            "Subject: Programming in C\n"
            "Subject Code: TEST-01\n"
            "Term: Winter 2026\n"
            "Q1. Explain a loop. (2 marks)\n"
            "- Any correct explanation (2)\n"
        )
        exam = parsed.seed["exam"]
        self.assertEqual(exam["title"], "Mini Project Class Test")
        self.assertEqual(exam["subject"], "Programming in C")
        self.assertEqual(exam["code"], "TEST-01")
        self.assertEqual(exam["term"], "Winter 2026")

    def test_a_metadata_line_is_never_used_as_the_title(self) -> None:
        parsed = self.parse(
            "Subject: Physics\nQ1. State Newton's law. (2 marks)\n- States F = ma (2)\n"
        )
        self.assertNotIn("Subject:", parsed.seed["exam"]["title"])

    def test_an_answer_key_is_captured(self) -> None:
        parsed = self.parse(
            "Q1. Explain a while loop. (2 marks)\n"
            "- Condition checked first (2)\n"
            "Answer key: A while loop is entry controlled.\n"
        )
        self.assertIn(
            "entry controlled", parsed.seed["questions"][0]["answer_key"]
        )

    def test_a_sum_mismatch_is_reported_not_silently_rebalanced(self) -> None:
        """The imported rubric must say what the document said.

        Rescaling a marking scheme to make it add up is an examiner's
        decision. Doing it here would change what the paper is worth without
        anyone being told.
        """
        parsed = self.parse(
            "Q1. State Newton's second law. (5 marks)\n"
            "- States F = ma ... 2\n"
            "- Defines each symbol ... 1\n"
        )
        question = parsed.seed["questions"][0]
        self.assertEqual(question["max_marks"], 5)
        self.assertEqual(sum(c["max_marks"] for c in question["criteria"]), 3)
        self.assertTrue(any("sum to 3" in w for w in parsed.warnings))

    def test_an_even_split_adds_up_exactly(self) -> None:
        """7 marks over 3 criteria must still total 7, not 6.99."""
        parsed = self.parse(
            "Q1. Explain break. (7 marks)\n- Defines it\n- Example\n- One level only\n"
        )
        question = parsed.seed["questions"][0]
        self.assertAlmostEqual(
            sum(c["max_marks"] for c in question["criteria"]), 7.0, places=3
        )

    def test_a_document_with_no_questions_is_refused(self) -> None:
        with self.assertRaises(RubricImportError) as caught:
            self.parse("Minutes of the staff meeting.\nAttendance was noted.\n")
        self.assertIn("No questions", str(caught.exception))

    def test_a_numbered_line_without_marks_does_not_open_a_question(self) -> None:
        """Otherwise every numbered criterion becomes a one-line question."""
        parsed = self.parse(
            "Q1. Explain pointers. (4 marks)\n"
            "1. Defines a pointer as an address (2)\n"
            "2. Gives a declaration example (2)\n"
        )
        self.assertEqual(len(parsed.seed["questions"]), 1)
        self.assertEqual(len(parsed.seed["questions"][0]["criteria"]), 2)

    def test_the_seed_is_what_exam_from_seed_accepts(self) -> None:
        from app.services.rubric_service import exam_from_seed

        parsed = self.parse(
            "Subject: Programming in C\n"
            "Q1. Explain a while loop. (4 marks)\n"
            "- Condition checked first (2)\n"
            "- Syntax correct (2)\n"
        )
        exam_in = exam_from_seed(parsed.seed)
        self.assertEqual(len(exam_in.questions), 1)
        self.assertEqual(exam_in.questions[0].max_marks, 4)
        self.assertIsNotNone(exam_in.questions[0].rubric)


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


class ParseDocumentEndpointTests(unittest.TestCase):
    def post(self, data: bytes, filename: str, content_type: str, **params):
        return client.post(
            "/api/v1/exams/parse-document",
            files={"file": (filename, data, content_type)},
            params=params,
        )

    def test_a_word_paper_is_parsed_without_being_saved(self) -> None:
        before = len(client.get("/api/v1/exams").json())

        response = self.post(
            make_docx(PAPER_BODY),
            "paper.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()

        self.assertEqual(body["strategy"], "local")
        self.assertEqual(body["question_count"], 2)
        self.assertEqual(body["total_marks"], 10)
        self.assertEqual(body["source"]["kind"], "docx")
        self.assertEqual(body["source"]["table_count"], 1)

        # Nothing was written: a proposal is not an import.
        self.assertEqual(len(client.get("/api/v1/exams").json()), before)

    def test_a_parsed_paper_can_then_be_imported(self) -> None:
        parsed = self.post(
            make_docx(PAPER_BODY), "paper.docx", "application/octet-stream"
        ).json()

        created = client.post("/api/v1/exams/import", json=parsed["seed"])
        self.assertEqual(created.status_code, 201, created.text)

        exam = created.json()
        self.assertEqual(exam["subject"], "Programming in C")
        self.assertEqual(len(exam["questions"]), 2)

        # And the rubric it carried is a usable one.
        validation = client.get(f"/api/v1/exams/{exam['id']}/validate").json()
        self.assertTrue(validation["is_valid"], validation)

        client.delete(f"/api/v1/exams/{exam['id']}")

    def test_a_pdf_paper_is_parsed(self) -> None:
        data = make_pdf(
            [
                "Subject: Operating Systems",
                "Q1. What is a deadlock? (4 marks)",
                "- Defines deadlock as circular wait (2)",
                "- Names the four conditions (2)",
            ]
        )
        response = self.post(data, "paper.pdf", "application/pdf")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["source"]["kind"], "pdf")
        self.assertEqual(body["question_count"], 1)

    def test_an_empty_upload_is_refused(self) -> None:
        response = self.post(b"", "empty.docx", "application/octet-stream")
        self.assertEqual(response.status_code, 400)

    def test_a_document_with_no_questions_returns_422(self) -> None:
        body = _para("Minutes of the staff meeting held on Tuesday afternoon.")
        response = self.post(make_docx(body), "notes.docx", "application/octet-stream")
        self.assertEqual(response.status_code, 422)
        self.assertIn("No questions", response.json()["detail"])

    def test_an_unreadable_file_returns_400_with_a_reason(self) -> None:
        response = self.post(b"\x00\x01\x02" * 100, "mystery.bin", "application/octet-stream")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported", response.json()["detail"])


# ---------------------------------------------------------------------------
# The engine switch
# ---------------------------------------------------------------------------


class EngineSelectionTests(unittest.TestCase):
    def test_the_engines_endpoint_lists_both(self) -> None:
        body = client.get("/api/v1/engines").json()
        ids = [engine["id"] for engine in body["engines"]]
        self.assertEqual(ids, ["gemini", "local"])

    def test_the_local_engine_is_always_available(self) -> None:
        body = client.get("/api/v1/engines").json()
        local = next(e for e in body["engines"] if e["id"] == "local")
        self.assertTrue(local["available"])

    def test_gemini_without_a_key_is_offered_but_marked_unavailable(self) -> None:
        """The switch must be visibly off, not fail when flipped.

        The test suite pins the key to empty, so this is the no-key case.
        """
        body = client.get("/api/v1/engines").json()
        gemini = next(e for e in body["engines"] if e["id"] == "gemini")
        self.assertFalse(gemini["available"])
        self.assertIn("API key", gemini["unavailable_reason"])

    def test_asking_for_gemini_without_a_key_fails_loudly(self) -> None:
        """It must not quietly transcribe with the local model instead.

        The provider's name is written onto the stored transcription, so a
        substitution here would make the record say Gemini read a page that
        Gemini never saw.
        """
        from app.providers.ocr.registry import EngineUnavailable, get_ocr_provider_for

        with self.assertRaises(EngineUnavailable):
            get_ocr_provider_for("gemini")

    def test_the_marker_refuses_the_same_way(self) -> None:
        from app.providers.evaluation.registry import (
            EngineUnavailable,
            get_evaluation_provider_for,
        )

        with self.assertRaises(EngineUnavailable):
            get_evaluation_provider_for("gemini")

    def test_local_names_resolve_to_the_same_engine(self) -> None:
        from app.providers.ocr.registry import get_ocr_provider_for

        self.assertIs(
            get_ocr_provider_for("local"), get_ocr_provider_for("trocr")
        )

    def test_an_unknown_engine_is_refused(self) -> None:
        from app.providers.ocr.registry import EngineUnavailable, get_ocr_provider_for

        with self.assertRaises(EngineUnavailable):
            get_ocr_provider_for("gpt-9")

    def test_an_unknown_engine_on_an_endpoint_returns_503(self) -> None:
        response = client.get("/api/v1/ocr/provider", params={"engine": "nonsense"})
        self.assertEqual(response.status_code, 503)

    def test_auto_follows_configuration(self) -> None:
        from app.providers.ocr.registry import get_ocr_provider, get_ocr_provider_for

        self.assertIs(get_ocr_provider_for(None), get_ocr_provider())
        self.assertIs(get_ocr_provider_for("auto"), get_ocr_provider())


class BundledSampleTests(unittest.TestCase):
    """The demo document committed to the repository must keep parsing.

    `data/exam/sample_rubric.docx` is what the import feature is demonstrated
    with. It is a real Word file with three bordered tables, so it exercises
    the extractor on the shape a marking scheme is actually written in - and
    if a parser change breaks it, the demo breaks, which is worth a test of
    its own rather than finding out in front of an audience.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from app.core.config import REPO_ROOT

        cls.path = REPO_ROOT / "data" / "exam" / "sample_rubric.docx"

    def test_the_sample_parses_into_a_markable_paper(self) -> None:
        if not self.path.exists():
            self.skipTest("run scripts/make_sample_rubric.py to create it")

        parsed = parse_locally(
            document_text.extract(self.path.read_bytes(), self.path.name).text
        )
        seed = parsed.seed

        self.assertEqual(seed["exam"]["subject"], "Data Structures")
        self.assertEqual(seed["exam"]["code"], "EVN-DS-02")
        self.assertEqual(len(seed["questions"]), 3)
        self.assertEqual(seed["exam"]["total_marks"], 21)

        # Every rubric must sum, or the paper imports as unmarkable.
        for question in seed["questions"]:
            criteria = question["criteria"]
            self.assertAlmostEqual(
                sum(c["max_marks"] for c in criteria),
                question["max_marks"],
                places=3,
                msg=f"{question['number']} does not sum",
            )
            self.assertTrue(question["answer_key"])

        self.assertEqual(parsed.warnings, [])


if __name__ == "__main__":
    unittest.main()
