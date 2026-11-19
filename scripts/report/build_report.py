"""Assemble the Mini Project report as a Word document.

    .venv\\Scripts\\python scripts\\report\\figures.py
    .venv\\Scripts\\python scripts\\report\\build_report.py
    powershell -ExecutionPolicy Bypass -File scripts\\report\\finalise.ps1

The page-numbering regimes follow the institute's compilation instructions:

    Part A   cover, declarations, certificate, acknowledgement   no numbers
    Part B   abstract, contents, lists                           i, ii, iii...
    Part C   chapters, references, appendices                    1, 2, 3...

### Why the document is built twice

The List of Figures and the List of Tables sit in Part B, ahead of the
chapters, but their content is only known once the chapters have been
emitted. So the document is built once to discover what was emitted, then
built again with those lists filled in. The content functions are
deterministic, so the two passes agree by construction.

The table of contents and every page number are Word fields; `finalise.ps1`
evaluates them, reports the resulting page count and exports a PDF.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

REPO = HERE.parents[1]
OUT = REPO / "docs" / "report" / "EvalNova_Mini_Project_Report.docx"

from content_back import appendices, references  # noqa: E402
from content_ch1_2 import chapter_1  # noqa: E402
from content_ch3 import chapter_3  # noqa: E402
from content_ch4_5 import chapter_4, chapter_5  # noqa: E402
from content_front import (  # noqa: E402
    abstract,
    acknowledgement,
    certificate,
    cover,
    declaration_one,
    declaration_two,
)
from docx_builder import Report  # noqa: E402
from meta import placeholders  # noqa: E402

ABBREVIATIONS = [
    ("API", "Application Programming Interface"),
    ("ASAG", "Automatic Short Answer Grading"),
    ("CER", "Character Error Rate"),
    ("CPU", "Central Processing Unit"),
    ("DPI", "Dots Per Inch"),
    ("ER", "Entity-Relationship"),
    ("GPU", "Graphics Processing Unit"),
    ("HTR", "Handwritten Text Recognition"),
    ("HTTP", "Hypertext Transfer Protocol"),
    ("IAM", "The IAM Handwriting Database"),
    ("JSON", "JavaScript Object Notation"),
    ("LLM", "Large Language Model"),
    ("OCR", "Optical Character Recognition"),
    ("ORM", "Object-Relational Mapping"),
    ("PDF", "Portable Document Format"),
    ("PSNR", "Peak Signal-to-Noise Ratio"),
    ("REST", "Representational State Transfer"),
    ("SQL", "Structured Query Language"),
    ("TrOCR", "Transformer-based Optical Character Recognition"),
    ("WER", "Word Error Rate"),
    ("r", "Pearson correlation coefficient"),
]


def abbreviations(r) -> None:
    r.front_heading("List of Abbreviations")
    # Two pairs per row, so the list occupies half the page it otherwise would.
    rows = []
    for i in range(0, len(ABBREVIATIONS), 2):
        pair = ABBREVIATIONS[i:i + 2]
        row = [pair[0][0], pair[0][1]]
        row += [pair[1][0], pair[1][1]] if len(pair) > 1 else ["", ""]
        rows.append(row)
    r.table(
        None,  # not one of the report's numbered tables
        ["Abbr.", "Expansion", "Abbr.", "Expansion"],
        rows,
        widths=[0.6, 2.35, 0.6, 2.4],
        font=9.0,
    )


def _caption_list(r, title: str, entries, note: str) -> None:
    r.front_heading(title)
    r.para(note, italic=True, space_after=8)
    r.caption_list(entries)


def build(figures=None, tables=None) -> Report:
    """Emit the whole document. The lists are filled on the second pass."""
    r = Report()

    # ---- Part A: no page numbers -------------------------------------
    cover(r)
    declaration_one(r)
    declaration_two(r)
    certificate(r)
    acknowledgement(r)

    # ---- Part B: lower-case Roman, restarting at i -------------------
    r.new_part(fmt="lowerRoman", start=1, numbered=True)
    abstract(r)

    r.front_heading("Table of Contents")
    r.toc_field()

    _caption_list(
        r, "List of Figures", figures or [],
        "Figures are numbered chapter-wise; the caption appears below each figure.",
    )
    _caption_list(
        r, "List of Tables", tables or [],
        "Tables are numbered chapter-wise; the caption appears above each table.",
    )
    abbreviations(r)

    # ---- Part C: Arabic, restarting at 1 -----------------------------
    r.new_part(fmt="decimal", start=1, numbered=True)
    r.chapter = 0
    # The abbreviation table above was emitted by this same Report, so the
    # counters are cleared before the chapters start numbering their own.
    r.figures.clear()
    r.tables.clear()
    r.figure_no = 0
    r.table_no = 0

    chapter_1(r)      # also emits Chapter 2
    chapter_3(r)
    chapter_4(r)
    chapter_5(r)
    references(r)
    appendices(r)
    return r


def main() -> int:
    missing = placeholders()

    probe = build()                           # discover what gets emitted
    r = build(probe.figures, probe.tables)    # build again, lists filled in
    r.save(OUT)

    print(f"\nWrote {OUT.relative_to(REPO)}")
    print(f"  chapters: 5   figures: {len(r.figures)}   tables: {len(r.tables)}")
    print("\nNext:  powershell -ExecutionPolicy Bypass -File "
          "scripts\\report\\finalise.ps1")
    print("       (updates the contents, the lists and every page number,")
    print("        then exports a PDF)")

    if missing:
        print(f"\n!! {len(missing)} placeholder(s) still to fill in "
              f"scripts/report/meta.py:")
        for item in missing:
            print(f"     {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
