"""Write `data/exam/sample_rubric.docx` - a demo document for rubric import.

A typed marking scheme in the shape institutions actually write them: a
metadata block, numbered questions with their marks in brackets, and the
criteria in a table with a marks column. It exists so the import feature can
be demonstrated without hunting for a real paper, and so the tests have
something to point at that is not a fixture built inside a test file.

Run it with:

    .venv\\Scripts\\python backend\\..\\scripts\\make_sample_rubric.py

It writes a real .docx - a zip of XML - with no dependency beyond the standard
library, the same way `app/services/document_text.py` reads one.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "data" / "exam" / "sample_rubric.docx"

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""


def para(text: str = "", *, bold: bool = False, size: int | None = None) -> str:
    runs = ""
    if text:
        properties = ""
        if bold or size:
            properties = (
                "<w:rPr>"
                + ("<w:b/>" if bold else "")
                + (f'<w:sz w:val="{size * 2}"/>' if size else "")
                + "</w:rPr>"
            )
        runs = f"<w:r>{properties}<w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r>"
    return f"<w:p>{runs}</w:p>"


def table(rows: list[list[str]]) -> str:
    body = ""
    for index, row in enumerate(rows):
        cells = "".join(
            f"<w:tc><w:tcPr><w:tcW w:w=\"{width}\" w:type=\"dxa\"/></w:tcPr>"
            f"{para(cell, bold=index == 0)}</w:tc>"
            for cell, width in zip(row, (900, 6800, 1200))
        )
        body += f"<w:tr>{cells}</w:tr>"
    return (
        '<w:tbl><w:tblPr><w:tblBorders>'
        '<w:top w:val="single" w:sz="4"/><w:left w:val="single" w:sz="4"/>'
        '<w:bottom w:val="single" w:sz="4"/><w:right w:val="single" w:sz="4"/>'
        '<w:insideH w:val="single" w:sz="4"/><w:insideV w:val="single" w:sz="4"/>'
        "</w:tblBorders></w:tblPr>" + body + "</w:tbl>"
    )


QUESTIONS = [
    (
        "Q1. Define a stack and list the operations it supports. "
        "State one real use of a stack in a compiler. (6 marks)",
        [
            ["1", "Defines a stack as a LIFO structure", "2"],
            ["2", "Lists push and pop", "2"],
            ["3", "Names one further operation such as peek or isEmpty", "1"],
            ["4", "Gives a compiler use such as the call stack or expression parsing", "1"],
        ],
        "A stack is a linear data structure in which the last element inserted "
        "is the first removed, so it is called last-in-first-out. Its basic "
        "operations are push, which adds an element to the top, and pop, which "
        "removes the top element. Peek returns the top element without removing "
        "it, and isEmpty reports whether the stack holds anything. A compiler "
        "uses a stack to hold function call frames and to evaluate expressions.",
    ),
    (
        "Q2. Explain linear search. State its best case and worst case time "
        "complexity, and say when it is preferable to binary search. (7 marks)",
        [
            ["1", "Describes examining elements one by one from the start", "2"],
            ["2", "States the best case as O(1)", "1"],
            ["3", "States the worst case as O(n)", "1"],
            ["4", "Says it does not require the data to be sorted", "2"],
            ["5", "Notes it is preferable on small or unsorted data", "1"],
        ],
        "Linear search examines each element of the list in turn from the first "
        "until the target is found or the list ends. In the best case the target "
        "is the first element, which is O(1). In the worst case it is absent or "
        "last, so all n elements are examined and the cost is O(n). Unlike "
        "binary search it does not require the data to be sorted, so it is the "
        "better choice on small lists or on data that is not kept in order.",
    ),
    (
        "Q3. Differentiate between an array and a linked list on any four "
        "points. (8 marks)",
        [
            ["1", "Memory allocation: contiguous against dynamic", "2"],
            ["2", "Access: random access against sequential traversal", "2"],
            ["3", "Insertion and deletion cost", "2"],
            ["4", "Memory overhead of storing a pointer per node", "2"],
        ],
        "An array occupies one contiguous block of memory decided when it is "
        "created, while a linked list allocates each node separately as it is "
        "needed. An array supports random access by index in O(1); a linked "
        "list must be traversed from the head, which is O(n). Inserting or "
        "deleting in the middle of an array requires shifting the later "
        "elements, whereas a linked list only relinks two pointers. A linked "
        "list pays for this with one pointer of extra memory per node.",
    ),
]


def build() -> bytes:
    body = (
        para("Shivaji University, Kolhapur", bold=True, size=14)
        + para("Second Year Computer Science - Class Test", bold=True, size=12)
        + para("Subject: Data Structures")
        + para("Subject Code: EVN-DS-02")
        + para("Term: Winter 2026")
        + para("Total Marks: 21")
        + para("Duration: 45 minutes")
        + para()
        + para("Marking scheme", bold=True, size=12)
        + para(
            "Award the marks shown against each point. Partial credit is allowed "
            "where a point is partly made. Spelling is not penalised."
        )
        + para()
    )

    for question, criteria, answer_key in QUESTIONS:
        body += para(question, bold=True)
        body += table([["No", "Criterion", "Marks"], *criteria])
        body += para(f"Answer key: {answer_key}")
        body += para()

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {W}><w:body>{body}</w:body></w:document>"
    )

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", RELS)
        archive.writestr("word/document.xml", document)
    return TARGET.read_bytes()


if __name__ == "__main__":
    data = build()
    print(f"Wrote {TARGET} ({len(data):,} bytes)")
    print("Import it from Questions & rubrics -> Import Word / PDF.")
