"""Document scaffolding for the project report.

Everything here is formatting mechanics, kept away from the report's prose so
that the content module reads as a document rather than as XML plumbing. The
rules implemented are the ones in *Guidelines for Preparation of Mini Project
Report (CSD 300/301/302, ECD 301/302)*, IIIT Nagpur:

* Margins: top 1", bottom 1.25", left 1.5", right 0.8"
* Chapters start on a fresh page, number and title centred, 18 pt bold,
  mixed case, with vertical space between number, title and first paragraph
* Sections numbered with decimal points (2.3.4 = Chapter 2, Section 3,
  Subsection 4)
* Tables numbered chapter-wise with the caption **above**; figures numbered
  chapter-wise with the caption **below**
* Three page-numbering regimes: Part A unnumbered, Part B lower-case Roman
  restarting at i, Part C Arabic restarting at 1

python-docx has no API for per-section page-number formats or for field
codes, so those are written as raw OOXML. They are isolated in this module
for that reason.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

SERIF = "Times New Roman"
BODY_PT = 10.5
NAVY = RGBColor(0x00, 0x16, 0x4F)
GREY = RGBColor(0x40, 0x56, 0x7F)


# ---------------------------------------------------------------------------
# Raw OOXML helpers
# ---------------------------------------------------------------------------


def _field(paragraph, instruction: str) -> None:
    """Insert a Word field such as PAGE or TOC.

    Word computes these when the document is opened and the fields are
    updated; python-docx cannot evaluate them, which is why a generated
    table of contents must be refreshed once in Word.
    """
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = "…"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for node in (begin, instr, separate, placeholder, end):
        run._r.append(node)


def _page_numbering(section, fmt: str | None, start: int | None = None) -> None:
    """Set the page-number format for one section (w:pgNumType)."""
    pg = section._sectPr.find(qn("w:pgNumType"))
    if pg is None:
        pg = OxmlElement("w:pgNumType")
        section._sectPr.append(pg)
    if fmt:
        pg.set(qn("w:fmt"), fmt)
    if start is not None:
        pg.set(qn("w:start"), str(start))


def _no_border(table) -> None:
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "nil")
        borders.append(element)
    table._tbl.tblPr.append(borders)


def _shade(cell, hex_colour: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hex_colour)
    cell._tc.get_or_add_tcPr().append(shd)


def _repeat_header(row) -> None:
    """Mark a table row as a header that repeats across page breaks."""
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def _plain(text: str) -> str:
    """Strip inline markup from a caption.

    Captions are set in one style and also copied into the List of Figures
    and List of Tables, so they are rendered as plain runs rather than
    through the rich-text splitter. Any markup left in them would therefore
    print literally.
    """
    import re

    text = re.sub(r"\*\*(.+?)\*\*", lambda m: m.group(1), text)
    text = re.sub(r"`(.+?)`", lambda m: m.group(1), text)
    return text.replace("*", "").replace("`", "")


def _bookmark(paragraph, name: str, bookmark_id: int) -> None:
    """Wrap a paragraph's content in a Word bookmark.

    The lists of figures and tables are built from these rather than from a
    TOC field: a TOC keyed on a paragraph style proved unreliable here, while
    a bookmark plus a PAGEREF field is exactly the mechanism Word's own
    cross-references use, and it resolves to a real page number.
    """
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def _dotted_tab(paragraph, position_inches: float) -> None:
    """A right tab stop with a dot leader, for a contents-style line."""
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "right")
    tab.set(qn("w:leader"), "dot")
    tab.set(qn("w:pos"), str(int(position_inches * 1440)))
    tabs.append(tab)
    paragraph._p.get_or_add_pPr().append(tabs)


# ---------------------------------------------------------------------------
# The document wrapper
# ---------------------------------------------------------------------------


class Report:
    def __init__(self) -> None:
        self.doc = Document()
        self.chapter = 0
        self.section_no = 0
        self.subsection_no = 0
        self.table_no = 0
        self.figure_no = 0
        self.figures: list[tuple[str, str, str]] = []  # (label, caption, bookmark)
        self.tables: list[tuple[str, str, str]] = []
        self._bookmark_id = 1000
        self._setup_styles()
        self._caption_styles()
        self._setup_page(self.doc.sections[0])
        # The first chapter follows a section break that already began a
        # page, so it must not add a second one and leave a page holding
        # nothing but its own number.
        self._first_chapter = True

    # -- setup -----------------------------------------------------------

    def _setup_styles(self) -> None:
        normal = self.doc.styles["Normal"]
        normal.font.name = SERIF
        normal.font.size = Pt(BODY_PT)
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), SERIF)
        paragraph = normal.paragraph_format
        paragraph.line_spacing = 1.05
        paragraph.space_after = Pt(4)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    def _caption_styles(self) -> None:
        """Two styles whose only job is to be collectable.

        Word builds a List of Figures from a TOC field that names a paragraph
        style. Giving figure captions and table captions one style each is
        what lets the two lists be built separately, with real page numbers,
        from captions this module writes itself.
        """
        for name in ("FigureCaption", "TableCaption"):
            style = self.doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            style.base_style = self.doc.styles["Normal"]
            style.quick_style = False
            style.font.name = SERIF
            style.font.size = Pt(9.5)
            style.font.bold = True
            style.font.color.rgb = NAVY
            style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            style.paragraph_format.line_spacing = 1.0
            style.paragraph_format.space_after = Pt(8)

    def _setup_page(self, section) -> None:
        section.page_width = Inches(8.27)   # A4
        section.page_height = Inches(11.69)
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.25)
        section.left_margin = Inches(1.5)
        section.right_margin = Inches(0.8)
        section.footer_distance = Inches(0.6)

    # -- document parts --------------------------------------------------

    def new_part(self, fmt: str | None, start: int | None, numbered: bool) -> None:
        """Begin a new section with its own page-number regime."""
        section = self.doc.add_section(WD_SECTION.NEW_PAGE)
        self._setup_page(section)
        section.footer.is_linked_to_previous = False
        _page_numbering(section, fmt, start)

        footer = section.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in list(footer.runs):
            run.text = ""
        if numbered:
            _field(footer, "PAGE")
            for run in footer.runs:
                run.font.name = SERIF
                run.font.size = Pt(11)

    def page_break(self) -> None:
        self.doc.add_page_break()

    # -- headings --------------------------------------------------------

    def chapter_heading(self, title: str) -> None:
        self.chapter += 1
        self.section_no = 0
        self.subsection_no = 0
        # Numbered chapter-wise, so these restart too.
        self.table_no = 0
        self.figure_no = 0
        if self._first_chapter:
            self._first_chapter = False
        else:
            self.doc.add_page_break()

        # The guidelines ask for an additional top margin of about 75 mm on a
        # chapter's opening page. Empty paragraphs are how that is expressed
        # without giving the chapter its own section.
        for _ in range(1):
            spacer = self.doc.add_paragraph()
            spacer.paragraph_format.space_after = Pt(0)

        number = self.doc.add_paragraph()
        number.alignment = WD_ALIGN_PARAGRAPH.CENTER
        number.paragraph_format.space_after = Pt(20)
        run = number.add_run(f"Chapter {self.chapter}")
        run.font.size = Pt(18)
        run.bold = True
        run.font.color.rgb = NAVY

        heading = self.doc.add_paragraph(style="Heading 1")
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        heading.paragraph_format.space_after = Pt(20)
        run = heading.add_run(title)
        run.font.name = SERIF
        run.font.size = Pt(18)
        run.bold = True
        run.font.color.rgb = NAVY

    def section(self, title: str) -> str:
        self.section_no += 1
        self.subsection_no = 0
        label = f"{self.chapter}.{self.section_no}"
        paragraph = self.doc.add_paragraph(style="Heading 2")
        paragraph.paragraph_format.space_before = Pt(12)
        paragraph.paragraph_format.space_after = Pt(6)
        run = paragraph.add_run(f"{label}  {title}")
        run.font.name = SERIF
        run.font.size = Pt(14)
        run.bold = True
        run.font.color.rgb = NAVY
        return label

    def subsection(self, title: str) -> str:
        self.subsection_no += 1
        label = f"{self.chapter}.{self.section_no}.{self.subsection_no}"
        paragraph = self.doc.add_paragraph(style="Heading 3")
        paragraph.paragraph_format.space_before = Pt(9)
        paragraph.paragraph_format.space_after = Pt(3)
        run = paragraph.add_run(f"{label}  {title}")
        run.font.name = SERIF
        run.font.size = Pt(12.5)
        run.bold = True
        run.font.color.rgb = NAVY
        return label

    def front_heading(self, title: str, page_break: bool = True) -> None:
        """A centred heading for the front matter, which carries no number."""
        if page_break:
            self.doc.add_page_break()
        paragraph = self.doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(18)
        run = paragraph.add_run(title)
        run.font.size = Pt(16)
        run.bold = True
        run.font.color.rgb = NAVY

    # -- body ------------------------------------------------------------

    def para(self, text: str, *, italic: bool = False, size: float | None = None,
             align: str = "justify", space_after: int = 6, bold: bool = False):
        paragraph = self.doc.add_paragraph()
        paragraph.alignment = {
            "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "left": WD_ALIGN_PARAGRAPH.LEFT,
            "right": WD_ALIGN_PARAGRAPH.RIGHT,
        }[align]
        paragraph.paragraph_format.space_after = Pt(space_after)
        self._rich(paragraph, text, italic=italic, bold=bold, size=size)
        return paragraph

    def _rich(self, paragraph, text: str, *, italic=False, bold=False, size=None):
        """Render **bold**, *italic* and `monospace` spans in a paragraph."""
        import re

        # **bold** must be tried before *italic*, or the opening ** of a bold
        # span is consumed as an italic marker and the rest renders as markup.
        for part in re.split(r"(\*\*.+?\*\*|\*[^*]+?\*|`.+?`)", text):
            if not part:
                continue
            run = paragraph.add_run()
            if part.startswith("**") and part.endswith("**"):
                run.text = part[2:-2]
                run.bold = True
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                run.text = part[1:-1]
                run.italic = True
            elif part.startswith("`") and part.endswith("`"):
                run.text = part[1:-1]
                run.font.name = "Consolas"
                run.font.size = Pt((size or BODY_PT) - 1.5)
            else:
                run.text = part
                run.bold = bold
            if run.font.name != "Consolas":
                run.font.name = SERIF
                run.font.size = Pt(size or BODY_PT)
            if italic:
                run.italic = True

    def bullets(self, items: list[str], numbered: bool = False) -> None:
        for item in items:
            paragraph = self.doc.add_paragraph(
                style="List Number" if numbered else "List Bullet"
            )
            paragraph.paragraph_format.left_indent = Inches(0.35)
            paragraph.paragraph_format.space_after = Pt(2)
            paragraph.paragraph_format.line_spacing = 1.03
            self._rich(paragraph, item)

    def code(self, text: str) -> None:
        paragraph = self.doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Inches(0.35)
        paragraph.paragraph_format.space_before = Pt(6)
        paragraph.paragraph_format.space_after = Pt(8)
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        run = paragraph.add_run(text)
        run.font.name = "Consolas"
        run.font.size = Pt(9.5)
        run.font.color.rgb = GREY

    # -- tables and figures ----------------------------------------------

    def table(self, caption: str | None, headers: list[str],
              rows: list[list[str]], widths: list[float] | None = None,
              font: float = 10.0) -> None:
        """A table with its caption above, as the guidelines require.

        A caption of None makes it an unnumbered table, for front matter
        that is not one of the report's own numbered tables.
        """
        if caption is not None:
            self.table_no += 1
            label = f"Table {self.chapter}.{self.table_no}"
            mark = f"tbl_{self.chapter}_{self.table_no}"
            self.tables.append((label, caption, mark))

            title = self.doc.add_paragraph(style="TableCaption")
            title.paragraph_format.space_before = Pt(8)
            title.paragraph_format.space_after = Pt(3)
            title.add_run(f"{label}: {_plain(caption)}")
            self._bookmark_id += 1
            _bookmark(title, mark, self._bookmark_id)

        table = self.doc.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        header_cells = table.rows[0].cells
        for cell, text in zip(header_cells, headers):
            cell.text = ""
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(1)
            paragraph.paragraph_format.space_before = Pt(1)
            paragraph.paragraph_format.line_spacing = 1.0
            run = paragraph.add_run(text)
            run.bold = True
            run.font.size = Pt(font)
            run.font.name = SERIF
            run.font.color.rgb = NAVY
            _shade(cell, "EAF1FB")
        _repeat_header(table.rows[0])

        for values in rows:
            cells = table.add_row().cells
            for cell, text in zip(cells, values):
                cell.text = ""
                paragraph = cell.paragraphs[0]
                paragraph.paragraph_format.space_after = Pt(1)
                paragraph.paragraph_format.space_before = Pt(1)
                paragraph.paragraph_format.line_spacing = 1.0
                self._rich(paragraph, str(text), size=font)

        if widths:
            for row in table.rows:
                for cell, width in zip(row.cells, widths):
                    cell.width = Inches(width)

        spacer = self.doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(0)
        spacer.paragraph_format.line_spacing = 1.0

    def figure(self, path: Path, caption: str, width: float = 4.2) -> None:
        self.figure_no += 1
        label = f"Figure {self.chapter}.{self.figure_no}"
        mark = f"fig_{self.chapter}_{self.figure_no}"
        self.figures.append((label, caption, mark))

        if not path.exists():
            self.para(f"[{label}: {caption} — figure not generated]", italic=True)
            return

        holder = self.doc.add_paragraph()
        holder.alignment = WD_ALIGN_PARAGRAPH.CENTER
        holder.paragraph_format.space_before = Pt(7)
        holder.paragraph_format.space_after = Pt(3)
        holder.add_run().add_picture(str(path), width=Inches(width))

        title = self.doc.add_paragraph(style="FigureCaption")
        run = title.add_run(f"{label}: {_plain(caption)}")
        self._bookmark_id += 1
        _bookmark(title, mark, self._bookmark_id)

    def caption_list(self, entries: list[tuple[str, str, str]]) -> None:
        """A List of Figures or List of Tables with real page numbers."""
        for label, caption, mark in entries:
            paragraph = self.doc.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(3)
            paragraph.paragraph_format.line_spacing = 1.0
            paragraph.paragraph_format.left_indent = Inches(0.0)
            _dotted_tab(paragraph, 5.97)
            run = paragraph.add_run(f"{label}:  ")
            run.bold = True
            run.font.size = Pt(10)
            run.font.name = SERIF
            clean = _plain(caption)
            text = clean if len(clean) <= 78 else clean[:75].rstrip() + "…"
            run2 = paragraph.add_run(text)
            run2.font.size = Pt(10)
            run2.font.name = SERIF
            paragraph.add_run("	")
            _field(paragraph, f"PAGEREF {mark} \h")
            for r in paragraph.runs:
                if not r.font.size:
                    r.font.size = Pt(10)
                    r.font.name = SERIF

    def toc_field(self) -> None:
        paragraph = self.doc.add_paragraph()
        _field(paragraph, r'TOC \o "1-3" \h \z \u')
        note = self.doc.add_paragraph()
        note.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = note.add_run(
            "(In Word: select all with Ctrl+A, then press F9 to build this "
            "table of contents and the page numbers throughout.)"
        )
        run.italic = True
        run.font.size = Pt(9)
        run.font.color.rgb = GREY

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(str(path))
