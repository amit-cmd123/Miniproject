"""The few facts about the submission that the code cannot discover.

Everything else in the report is derived from the repository, the measurement
JSON or the running application. This file is the one place to correct names,
enrolment numbers, the supervisor and the dates before printing.

Entries written as <angle brackets> are placeholders and must be replaced.
`build_report.py` prints a warning listing any that are still present.
"""

from __future__ import annotations

META = {
    "title": "EvalNova: A Confidence-Aware, Rubric-Driven System for "
             "Evaluating Handwritten Examination Answers",
    "subtitle": "Digitize. Evaluate. Elevate.",
    "course": "Mini Project – I",
    "session": "July to December 2026",
    "academic_year": "2026-27",
    "copyright_year": "2026",
    "submission_date": "<DD / MM / 2026>",

    # Order decides the order on the cover page and in both declarations.
    "members": [
        {"name": "Veer Bhattad", "enrolment": "<Enrolment No.>",
         "part": "Part 1 — Handwriting & OCR"},
        {"name": "Amit Kumar Pramanik", "enrolment": "<Enrolment No.>",
         "part": "Part 2 — Questions & Rubrics"},
        {"name": "<Name of participant 3>", "enrolment": "<Enrolment No.>",
         "part": "Part 3 — Evaluation & Confidence"},
        {"name": "<Name of participant 4>", "enrolment": "<Enrolment No.>",
         "part": "Part 4 — Examiner App & Validation"},
    ],

    "supervisor": "<Dr./Ms./Mr. Supervisor Name>",
    "supervisor_designation": "<Designation>",
    "hod": "Dr. Milind Penurkar",

    "repository": "https://github.com/amit-cmd123/Miniproject",

    # The machine every timing figure in Chapter 4 was measured on.
    "hardware": "Intel Core i9-13900H laptop, 16 GB RAM, CPU only (no GPU)",
    "os": "Windows 11",
    "python": "3.10",
}


def placeholders() -> list[str]:
    """Every value still carrying an angle-bracket placeholder."""
    found: list[str] = []

    def walk(prefix: str, value) -> None:
        if isinstance(value, dict):
            for key, inner in value.items():
                walk(f"{prefix}.{key}" if prefix else key, inner)
        elif isinstance(value, list):
            for index, inner in enumerate(value):
                walk(f"{prefix}[{index}]", inner)
        elif isinstance(value, str) and value.startswith("<") and value.endswith(">"):
            found.append(f"{prefix} = {value}")

    walk("", META)
    return found
