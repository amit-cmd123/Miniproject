"""Reading text out of a typed rubric document.

A question paper with its marking scheme usually exists as a Word file or a
PDF long before anyone thinks about JSON. This module turns one into plain
text; `rubric_import.py` then turns that text into a paper.

### Tables are the whole problem

Marking schemes are written as tables far more often than as prose - one row
per criterion, a marks column on the right. Extracting a `.docx` by pulling
every `<w:t>` run in file order destroys exactly that structure: the criterion
and its mark end up on separate lines with nothing linking them, and the
parser downstream cannot tell which mark belongs to which row.

So tables are read as tables and emitted as pipe-delimited rows:

    | Defines the term correctly | 2 |

which keeps the association the document was using to express it, and happens
to be the one text shape both the local parser and a language model read
without being taught anything.

### Scans are refused, not guessed at

A PDF of a *photographed* marking scheme has no text layer. Rather than
returning three stray characters and letting the parser invent a paper from
them, a page that yields almost nothing is reported as what it is.
"""

from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Below this many characters across the whole document there is nothing worth
# parsing, and the most likely explanation is a scan rather than a typed file.
MIN_USEFUL_CHARS = 40


class DocumentTextError(ValueError):
    """The document could not be read. The message is shown to the user."""


@dataclass
class ExtractedDocument:
    text: str
    kind: str  # "docx" | "pdf" | "text"
    page_count: int = 1
    table_count: int = 0
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------


def _paragraph_text(node: ElementTree.Element) -> str:
    """One paragraph, with tabs and line breaks kept as separators.

    `w:tab` matters: a criterion written as "Defines the term<TAB>2" is how a
    marking scheme that avoided tables still associates a line with its mark,
    and dropping the tab would glue them into one unparseable word.
    """
    parts: list[str] = []
    for child in node.iter():
        tag = child.tag
        if tag == W + "t":
            parts.append(child.text or "")
        elif tag == W + "tab":
            parts.append("\t")
        elif tag in (W + "br", W + "cr"):
            parts.append("\n")
    return "".join(parts).strip()


def _cell_text(cell: ElementTree.Element) -> str:
    lines = [_paragraph_text(p) for p in cell.findall(W + "p")]
    return " ".join(line for line in lines if line).strip()


def _table_rows(table: ElementTree.Element) -> list[str]:
    rows: list[str] = []
    for row in table.findall(W + "tr"):
        cells = [_cell_text(cell) for cell in row.findall(W + "tc")]
        if any(cells):
            rows.append("| " + " | ".join(cells) + " |")
    return rows


def extract_docx(data: bytes) -> ExtractedDocument:
    """Read a .docx without a third-party dependency.

    A .docx is a zip holding XML, so the standard library is enough. Doing it
    here rather than through python-docx keeps the demo machine's setup to
    `pip install -r requirements.txt` and nothing else, and the structure we
    need - paragraphs in order, tables as rows - is a dozen lines of it.
    """
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocumentTextError(
            "That file is not a readable .docx. If it is an older .doc file, "
            "open it in Word and save it as .docx or PDF first."
        ) from exc

    try:
        xml = archive.read("word/document.xml")
    except KeyError as exc:
        raise DocumentTextError(
            "That .docx has no document body - it may be corrupt, or saved in "
            "a format Word cannot open either."
        ) from exc

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise DocumentTextError(
            "The Word document could not be parsed: " + str(exc)
        ) from exc

    body = root.find(W + "body")
    if body is None:
        raise DocumentTextError("The Word document has no body.")

    lines: list[str] = []
    tables = 0

    # Walking the body's direct children keeps document order: a table that
    # appears between two paragraphs stays between them, which is what makes
    # "Q3 ... <table of criteria> ... Q4" parseable later.
    for node in body:
        if node.tag == W + "p":
            lines.append(_paragraph_text(node))
        elif node.tag == W + "tbl":
            tables += 1
            lines.append("")
            lines.extend(_table_rows(node))
            lines.append("")

    return ExtractedDocument(
        text=_tidy("\n".join(lines)),
        kind="docx",
        table_count=tables,
    )


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def extract_pdf(data: bytes) -> ExtractedDocument:
    from app.services.pdf_service import _pymupdf

    fitz = _pymupdf()
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise DocumentTextError("That PDF could not be opened: " + str(exc)) from exc

    warnings: list[str] = []
    pages: list[str] = []
    empty = 0
    try:
        count = document.page_count
        for page in document:
            text = page.get_text("text") or ""
            if len(text.strip()) < 10:
                empty += 1
            pages.append(text)
    finally:
        document.close()

    if empty:
        warnings.append(
            f"{empty} of {count} page(s) hold no selectable text. A scanned or "
            "photographed marking scheme cannot be read this way - export the "
            "original from Word, or paste the text in by hand."
        )

    return ExtractedDocument(
        text=_tidy("\n".join(pages)),
        kind="pdf",
        page_count=count,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _tidy(text: str) -> str:
    """Normalise whitespace without destroying line structure.

    Line breaks carry meaning here - one criterion per line - so they survive;
    runs of blank lines, non-breaking spaces and smart punctuation do not.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ")
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract(
    data: bytes, filename: str, content_type: str | None = None
) -> ExtractedDocument:
    """Text from an uploaded rubric document, by extension then by signature."""
    name = (filename or "").lower()
    kind = (content_type or "").lower()

    if name.endswith(".docx") or "wordprocessingml" in kind:
        result = extract_docx(data)
    elif name.endswith(".pdf") or kind == "application/pdf":
        result = extract_pdf(data)
    elif name.endswith((".txt", ".md", ".text")) or kind.startswith("text/"):
        result = ExtractedDocument(
            text=_tidy(data.decode("utf-8", "replace")), kind="text"
        )
    elif name.endswith(".doc"):
        raise DocumentTextError(
            "The old .doc format cannot be read directly. Open it in Word and "
            "save as .docx or PDF, then upload that."
        )
    elif data[:4] == b"PK\x03\x04":
        result = extract_docx(data)
    elif data[:5] == b"%PDF-":
        result = extract_pdf(data)
    else:
        raise DocumentTextError(
            "Unsupported file type. Upload a Word document (.docx), a PDF with "
            "selectable text, or a plain .txt file."
        )

    if len(result.text) < MIN_USEFUL_CHARS:
        detail = " ".join(result.warnings) or "The file appears to be empty."
        raise DocumentTextError("No readable text was found in that file. " + detail)

    return result
