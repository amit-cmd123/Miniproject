"""Front matter: cover, declarations, certificate, acknowledgement, abstract.

The wording of the declarations and the certificate is reproduced from the
institute's own template (`Mini Project Report Front Page and Declaration.docx`)
so that the generated report is the document the department expects rather
than an approximation of it.

Names, enrolment numbers and the supervisor are read from `meta.py`, which is
the single place to edit them.
"""

from __future__ import annotations

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from meta import META

NAVY = RGBColor(0x00, 0x16, 0x4F)
GREY = RGBColor(0x40, 0x56, 0x7F)


def _centre(r, text, size, bold=False, italic=False, after=6, colour=None, font=None):
    p = r.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.name = font or "Times New Roman"
    if colour is not None:
        run.font.color.rgb = colour
    return p


def cover(r) -> None:
    from pathlib import Path

    # The project wordmark already carries the tagline, so the cover does not
    # repeat it as a line of text.
    mark = (Path(__file__).resolve().parents[2] / "docs" / "report" / "assets"
            / "evalnova_wordmark.png")

    _centre(r, "", 12, after=6)
    if mark.exists():
        holder = r.doc.add_paragraph()
        holder.alignment = WD_ALIGN_PARAGRAPH.CENTER
        holder.paragraph_format.space_after = Pt(16)
        holder.add_run().add_picture(str(mark), width=Inches(3.3))
    else:
        _centre(r, "EvalNova", 26, bold=True, after=2, colour=NAVY)
        _centre(r, META["subtitle"], 12, italic=True, after=16, colour=GREY)

    _centre(r, META["title"], 16, bold=True, after=20, colour=NAVY)

    _centre(r, "Project report submitted to", 12, after=2)
    _centre(r, "Indian Institute of Information Technology, Nagpur,", 12, after=2)
    _centre(r, f"in partial fulfillment of the requirements for the {META['course']}",
            12, after=2)
    _centre(r, "at", 12, after=2)
    _centre(r, "DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING", 12,
            bold=True, after=10)
    _centre(r, "by", 12, after=8)

    table = r.doc.add_table(rows=0, cols=2)
    table.alignment = 1
    members = META["members"]
    for i in range(0, len(members), 2):
        cells = table.add_row().cells
        for cell, member in zip(cells, members[i:i + 2]):
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(3)
            run = p.add_run(member["name"])
            run.bold = True
            run.font.size = Pt(12)
            run.font.name = "Times New Roman"
            p2 = cell.add_paragraph()
            p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p2.paragraph_format.space_after = Pt(8)
            run2 = p2.add_run(member["enrolment"])
            run2.font.size = Pt(10.5)
            run2.font.name = "Times New Roman"
            run2.font.color.rgb = GREY
    from docx_builder import _no_border
    _no_border(table)

    _centre(r, "", 12, after=10)
    _centre(r, "Under the Supervision of", 12, after=4)
    _centre(r, META["supervisor"], 13, bold=True, after=4, colour=NAVY)
    _centre(r, f"Session Period: {META['session']}", 11.5, after=18, colour=GREY)

    _centre(r, "भारतीय सूचना प्रौद्योगिकी संस्थान, नागपुर", 12.5, bold=True, after=2)
    _centre(r, "INDIAN INSTITUTE OF INFORMATION TECHNOLOGY, NAGPUR", 12.5,
            bold=True, after=2, colour=NAVY)
    _centre(r, "(An Institution of National Importance by Act of Parliament) "
               "Survey No.140,141/1 behind Br. Sheshrao Wankhede Shetkari Sahkari "
               "Soot Girni, Nagpur, 441108", 9, after=10, colour=GREY)
    _centre(r, META["academic_year"], 12, bold=True, after=14)
    _centre(r, f"© Indian Institute of Information Technology, Nagpur (IIITN) "
               f"{META['copyright_year']}", 10, italic=True, colour=GREY)


def _signature_table(r, rows_label: str = "Signature") -> None:
    from docx_builder import _shade

    table = r.doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    table.alignment = 1
    headers = ("Sr. No.", "Name (Enrolment No.)", rows_label)
    for cell, text in zip(table.rows[0].cells, headers):
        cell.text = ""
        p = cell.paragraphs[0]
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(11)
        run.font.name = "Times New Roman"
        _shade(cell, "EAF1FB")

    for i, member in enumerate(META["members"], start=1):
        cells = table.add_row().cells
        for cell, text in zip(cells, (str(i),
                                      f"{member['name']}  ({member['enrolment']})",
                                      "")):
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(text)
            run.font.size = Pt(11)
            run.font.name = "Times New Roman"

    for row in table.rows:
        row.cells[0].width = Inches(0.8)
        row.cells[1].width = Inches(3.4)
        row.cells[2].width = Inches(1.7)


def declaration_one(r) -> None:
    r.doc.add_page_break()
    _centre(r, "Department of Computer Science and Engineering", 12.5, bold=True, after=2)
    _centre(r, "Indian Institute of Information Technology, Nagpur", 12.5,
            bold=True, after=22, colour=NAVY)
    _centre(r, "Declaration", 16, bold=True, after=18, colour=NAVY)

    names = ", ".join(m["name"] for m in META["members"])
    r.para(
        f"We, {names}, hereby declare that this project work titled "
        f"“{META['title']}” is carried out by us in the Department of "
        f"Computer Science and Engineering of Indian Institute of Information "
        f"Technology, Nagpur. The work is original and has not been submitted "
        f"earlier whole or in part for the award of any other certification "
        f"programme at this or any other Institution / University.",
        space_after=18,
    )
    _signature_table(r)
    r.para("")
    r.para(f"Date:  {META['submission_date']}", space_after=0)
    r.para(f"Place: Nagpur", space_after=0)


def declaration_two(r) -> None:
    r.doc.add_page_break()
    _centre(r, "Declaration", 16, bold=True, after=16, colour=NAVY)

    names = ", ".join(
        f"{m['name']} (Enrolment No. {m['enrolment']})" for m in META["members"]
    )
    r.para(
        f"We, {names}, understand that plagiarism is defined as any one or the "
        f"combination of the following:",
        space_after=8,
    )
    r.bullets([
        "Uncredited verbatim copying of individual sentences, paragraphs or "
        "illustrations (such as graphs, diagrams, etc.) from any source, "
        "published or unpublished, including the internet.",
        "Uncredited improper paraphrasing of pages or paragraphs (changing a few "
        "words or phrases, or rearranging the original sentence order).",
        "Credited verbatim copying of a major portion of a paper (or thesis "
        "chapter) without clear delineation of who did or wrote what. "
        "(Source: IEEE, the institute, Dec. 2004)",
    ])
    r.para(
        "We have made sure that all the ideas, expressions, graphs, diagrams, etc. "
        "that are not a result of our own work, are properly credited. Long "
        "phrases or sentences that had to be used verbatim from published "
        "literature have been clearly identified using quotation marks.",
        space_after=8,
    )
    r.para(
        "We affirm that no portion of our work can be considered as plagiarism and "
        "we take full responsibility if such complaint occurs. We understand fully "
        "well that the guide of the thesis may not be in a position to check for "
        "the possibility of such incidences of plagiarism in this body of work.",
        space_after=18,
    )
    _signature_table(r)
    r.para("")
    r.para(f"Date:  {META['submission_date']}", space_after=0)


def certificate(r) -> None:
    r.doc.add_page_break()
    _centre(r, "Department of Computer Science and Engineering", 12.5, bold=True, after=2)
    _centre(r, "Indian Institute of Information Technology, Nagpur", 12.5,
            bold=True, after=24, colour=NAVY)
    _centre(r, "Certificate", 16, bold=True, after=20, colour=NAVY)

    names = ", ".join(m["name"] for m in META["members"])
    r.para(
        f"This is to certify that the project titled “{META['title']}”, "
        f"submitted by {names}, in partial fulfillment of the requirements for the "
        f"{META['course']} in the Computer Science and Engineering department, "
        f"IIIT Nagpur. The work is comprehensive, complete and fit for final "
        f"evaluation.",
        space_after=48,
    )
    r.para(f"Date:  {META['submission_date']}", space_after=48)

    table = r.doc.add_table(rows=1, cols=2)
    table.alignment = 1
    left, right = table.rows[0].cells
    for cell, lines in (
        (left, [META["supervisor"], META["supervisor_designation"],
                "Department of CSE, IIIT Nagpur"]),
        (right, [META["hod"], "HoD – CSE", "IIIT Nagpur"]),
    ):
        cell.text = ""
        for i, line in enumerate(lines):
            p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(line)
            run.font.size = Pt(11.5)
            run.bold = i == 0
            run.font.name = "Times New Roman"
    from docx_builder import _no_border
    _no_border(table)


def acknowledgement(r) -> None:
    r.doc.add_page_break()
    _centre(r, "Acknowledgement", 16, bold=True, after=20, colour=NAVY)
    r.para(
        f"We express our deepest gratitude to our supervisor, {META['supervisor']}, "
        f"whose guidance and expertise have been instrumental in the successful "
        f"execution of this project. The unwavering support, insightful feedback "
        f"and encouragement we received have been invaluable throughout our work.",
    )
    r.para(
        "We are highly thankful to our Director, Prof. Dr. Prem Lal Patel, "
        "Dr. Tausif Diwan – Associate Dean (Academic), and Dr. Milind Penurkar "
        "– Head of Department (CSE). We extend our heartfelt thanks to our "
        "institution for fostering an environment of innovation and research, and "
        "for equipping us with the tools necessary to address complex problems."
    )
    r.para(
        "We thank the volunteers who hand-wrote the answer scripts used as this "
        "project's evaluation set, and who allowed their handwriting to be "
        "transcribed and measured against. Without a set of genuinely difficult, "
        "genuinely real pages, every accuracy figure in this report would have "
        "been measured on material chosen to flatter the system."
    )
    r.para(
        "Finally, we acknowledge the contributions of the academic and open-source "
        "communities, whose literature and technological frameworks provided a "
        "solid foundation for this project — in particular the authors of the "
        "TrOCR model and the maintainers of FastAPI, SQLAlchemy, OpenCV, PyTorch "
        "and React. This work would not have been possible without that collective "
        "effort."
    )


def abstract(r) -> None:
    r.front_heading("Abstract")
    r.para(
        "Manual evaluation of handwritten descriptive answers is slow, "
        "inconsistent between examiners and difficult to audit. Recent "
        "large language models can produce a plausible mark for such an answer, "
        "but a bare number from a model is not a decision an institution can "
        "defend: it carries no evidence, no account of what was actually read "
        "from the page, and no statement of how reliable it is.",
        space_after=8,
    )
    r.para(
        "This project presents **EvalNova**, a confidence-aware, rubric-driven "
        "system for evaluating handwritten examination answers. The system reads a "
        "scanned or photographed answer script, marks it criterion by criterion "
        "against the department's own marking scheme, reports a confidence that is "
        "measured rather than asserted, and routes uncertain results to a human "
        "examiner whose decision is recorded without overwriting the machine's. "
        "Every mark traces back through a chain of evidence to the handwriting "
        "that earned it.",
        space_after=8,
    )
    r.para(
        "Four design commitments distinguish the work. First, recognition is "
        "preceded by a classical computer-vision pipeline — illumination "
        "flattening, ink isolation, ruled-line removal, deskew and line "
        "segmentation — because a recogniser handed a ruled line confidently "
        "invents text for it. Second, marks arithmetic is performed in ordinary "
        "Python from the model's per-criterion verdicts, so a model can never "
        "award four marks from criteria totalling three. Third, confidence is "
        "composed from four measured signals as a weighted geometric mean, so one "
        "collapsing signal drags the result down instead of being averaged away. "
        "Fourth, recognition and marking engines sit behind a provider interface, "
        "and the engine may be chosen per request.",
        space_after=8,
    )
    r.para(
        "The system was evaluated on eight genuine handwritten answer pages "
        "produced by three writers, with hand-prepared reference transcriptions. "
        "The results, reported in full in Chapter 4, establish a twenty-fold "
        "difference in character error rate between the local line recogniser and "
        "the cloud vision-language model on this material, and show that the "
        "system's reported confidence separates its readable pages from its "
        "unreadable ones. The complete implementation comprises 47 API endpoints "
        "over 15 database tables, with 244 automated tests.",
        space_after=8,
    )
    r.para(
        "**Keywords:** handwritten text recognition, automated short answer "
        "grading, rubric-based evaluation, confidence estimation, selective "
        "prediction, human-in-the-loop assessment.",
    )
