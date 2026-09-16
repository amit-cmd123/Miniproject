"""Turning a PDF answer booklet into page images.

A scanned answer sheet arrives as a PDF, but handwriting recognition works on
images - and, one level down, on individual lines. So a PDF becomes N page
images, each of which then goes through the ordinary Part 1 pipeline.

Resolution matters more than it might seem. Rendering at a fixed DPI either
starves the recogniser of stroke detail on a small page or produces a needlessly
huge bitmap on a large one, so pages are rendered to a *target pixel width*
instead. That width is matched to what `preprocessing.MAX_WIDTH` will keep,
which avoids rendering detail that is immediately thrown away.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

# Matches preprocessing.MAX_WIDTH: rendering wider is wasted work, because the
# page is downscaled to this before segmentation anyway.
TARGET_WIDTH = 2000
# Guard rails. A scanner set to 1200 DPI on A3 can produce an enormous page.
MIN_ZOOM = 0.5
MAX_ZOOM = 6.0


class PdfError(ValueError):
    """The PDF could not be read. The message is shown to the user."""


@dataclass
class RenderedPage:
    page_number: int  # 1-based, as a human would refer to it
    image: np.ndarray  # BGR, ready for the preprocessing pipeline
    width: int
    height: int
    dpi: float


def _pymupdf():
    """Import PyMuPDF under whichever name this version exposes.

    The package renamed its module from `fitz` to `pymupdf`; `fitz` still works
    but emits a deprecation warning on every import.
    """
    try:
        import pymupdf

        return pymupdf
    except ImportError:  # pragma: no cover - older PyMuPDF
        import fitz

        return fitz


def is_pdf(content_type: str | None, data: bytes) -> bool:
    """Sniff the payload rather than trusting the declared content type.

    Browsers and mobile uploads mislabel files often enough that the magic
    bytes are the more reliable signal.
    """
    if data[:5] == b"%PDF-":
        return True
    return (content_type or "").lower() in {"application/pdf", "application/x-pdf"}


def page_count(data: bytes) -> int:
    fitz = _pymupdf()

    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            return document.page_count
    except Exception as exc:
        raise PdfError(f"This file could not be opened as a PDF: {exc}") from exc


def parse_page_range(spec: str | None, total: int) -> list[int]:
    """Parse "1-3,7" into 1-based page numbers, clamped to the document.

    Returns every page when the spec is empty.
    """
    if not spec or not spec.strip():
        return list(range(1, total + 1))

    wanted: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            if "-" in chunk:
                start_text, end_text = chunk.split("-", 1)
                start, end = int(start_text), int(end_text)
                if start > end:
                    start, end = end, start
                wanted.update(range(start, end + 1))
            else:
                wanted.add(int(chunk))
        except ValueError as exc:
            raise PdfError(
                f"'{chunk}' is not a page or range. Use something like 1-3 or 2,5."
            ) from exc

    pages = sorted(p for p in wanted if 1 <= p <= total)
    if not pages:
        raise PdfError(
            f"That page selection is outside the document, which has {total} "
            f"page{'s' if total != 1 else ''}."
        )
    return pages


def render_pages(
    data: bytes,
    pages: list[int] | None = None,
    target_width: int = TARGET_WIDTH,
) -> list[RenderedPage]:
    """Rasterise the requested pages to BGR arrays."""
    import cv2

    fitz = _pymupdf()

    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfError(f"This file could not be opened as a PDF: {exc}") from exc

    if document.page_count == 0:
        document.close()
        raise PdfError("This PDF has no pages.")

    if document.needs_pass:
        document.close()
        raise PdfError(
            "This PDF is password protected. Remove the password and upload it again."
        )

    wanted = pages or list(range(1, document.page_count + 1))
    rendered: list[RenderedPage] = []

    try:
        for number in wanted:
            page = document.load_page(number - 1)
            width_pt = page.rect.width or 1.0

            # Render to a target pixel width rather than a fixed DPI, so a
            # small page gets more magnification and a large one less.
            zoom = min(max(target_width / width_pt, MIN_ZOOM), MAX_ZOOM)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)

            array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height, pixmap.width, pixmap.n
            )
            if pixmap.n == 1:
                image = cv2.cvtColor(array, cv2.COLOR_GRAY2BGR)
            elif pixmap.n == 4:
                image = cv2.cvtColor(array, cv2.COLOR_RGBA2BGR)
            else:
                image = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)

            rendered.append(
                RenderedPage(
                    page_number=number,
                    # The buffer belongs to the pixmap, which is about to be
                    # freed - copy before it goes.
                    image=image.copy(),
                    width=pixmap.width,
                    height=pixmap.height,
                    dpi=round(zoom * 72.0, 1),
                )
            )
    except PdfError:
        raise
    except Exception as exc:
        raise PdfError(f"A page could not be rendered: {exc}") from exc
    finally:
        document.close()

    return rendered


def encode_png(image: np.ndarray) -> bytes:
    """PNG bytes for a rendered page, so it can be stored like any upload."""
    import cv2

    success, buffer = cv2.imencode(".png", image)
    if not success:  # pragma: no cover - defensive
        raise PdfError("A rendered page could not be encoded.")
    return buffer.tobytes()
