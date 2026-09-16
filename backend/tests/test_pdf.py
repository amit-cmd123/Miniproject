"""Tests for PDF rasterisation and page-range handling."""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from app.services.pdf_service import (
    PdfError,
    encode_png,
    is_pdf,
    page_count,
    parse_page_range,
    render_pages,
)


def make_pdf(pages: int = 3, width: int = 595, height: int = 842) -> bytes:
    """A small PDF with rendered text on each page."""
    try:
        import pymupdf as fitz
    except ImportError:  # pragma: no cover
        import fitz

    document = fitz.open()
    for index in range(pages):
        page = document.new_page(width=width, height=height)
        for line in range(6):
            page.insert_text(
                (60, 100 + line * 40),
                f"page {index + 1} line {line + 1} the quick brown fox",
                fontsize=18,
            )
    data = document.tobytes()
    document.close()
    return data


class SniffingTests(unittest.TestCase):
    def test_magic_bytes_win_over_content_type(self) -> None:
        self.assertTrue(is_pdf("application/octet-stream", b"%PDF-1.7 ..."))

    def test_declared_type_is_accepted(self) -> None:
        self.assertTrue(is_pdf("application/pdf", b"not really"))

    def test_an_image_is_not_a_pdf(self) -> None:
        self.assertFalse(is_pdf("image/png", b"\x89PNG\r\n\x1a\n"))


class PageRangeTests(unittest.TestCase):
    def test_blank_means_everything(self) -> None:
        self.assertEqual(parse_page_range(None, 3), [1, 2, 3])
        self.assertEqual(parse_page_range("  ", 3), [1, 2, 3])

    def test_a_simple_range(self) -> None:
        self.assertEqual(parse_page_range("1-3", 10), [1, 2, 3])

    def test_individual_pages(self) -> None:
        self.assertEqual(parse_page_range("2,5", 10), [2, 5])

    def test_mixed_and_deduplicated(self) -> None:
        self.assertEqual(parse_page_range("1-3,2,7", 10), [1, 2, 3, 7])

    def test_reversed_range_is_tolerated(self) -> None:
        self.assertEqual(parse_page_range("5-3", 10), [3, 4, 5])

    def test_out_of_bounds_pages_are_clamped_away(self) -> None:
        self.assertEqual(parse_page_range("1-99", 3), [1, 2, 3])

    def test_a_selection_entirely_outside_the_document_is_an_error(self) -> None:
        with self.assertRaises(PdfError):
            parse_page_range("50-60", 3)

    def test_nonsense_is_rejected_with_advice(self) -> None:
        with self.assertRaises(PdfError) as caught:
            parse_page_range("abc", 3)
        self.assertIn("1-3", str(caught.exception))


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pdf = make_pdf(3)

    def test_page_count(self) -> None:
        self.assertEqual(page_count(self.pdf), 3)

    def test_renders_every_page_by_default(self) -> None:
        pages = render_pages(self.pdf)
        self.assertEqual(len(pages), 3)
        self.assertEqual([p.page_number for p in pages], [1, 2, 3])

    def test_renders_only_the_requested_pages(self) -> None:
        pages = render_pages(self.pdf, [2])
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].page_number, 2)

    def test_output_is_bgr_and_usable_by_opencv(self) -> None:
        page = render_pages(self.pdf, [1])[0]
        self.assertEqual(page.image.ndim, 3)
        self.assertEqual(page.image.shape[2], 3)
        self.assertEqual(page.image.dtype, np.uint8)
        # Must survive the first step of the real pipeline.
        self.assertEqual(cv2.cvtColor(page.image, cv2.COLOR_BGR2GRAY).ndim, 2)

    def test_renders_near_the_target_width(self) -> None:
        page = render_pages(self.pdf, [1], target_width=1200)[0]
        self.assertAlmostEqual(page.width, 1200, delta=40)

    def test_a_narrow_page_is_magnified_more_than_a_wide_one(self) -> None:
        narrow = render_pages(make_pdf(1, width=300), [1])[0]
        wide = render_pages(make_pdf(1, width=1200), [1])[0]
        # Both target the same pixel width, so the narrow page needs more zoom.
        self.assertGreater(narrow.dpi, wide.dpi)

    def test_the_image_survives_the_pixmap(self) -> None:
        """The buffer is owned by the pixmap, so it must be copied out."""
        pages = render_pages(self.pdf)
        for page in pages:
            self.assertGreater(int(page.image.sum()), 0)

    def test_garbage_is_rejected(self) -> None:
        with self.assertRaises(PdfError):
            render_pages(b"this is not a pdf at all")

    def test_page_count_on_garbage_is_rejected(self) -> None:
        with self.assertRaises(PdfError):
            page_count(b"nope")

    def test_encode_png_round_trips(self) -> None:
        page = render_pages(self.pdf, [1])[0]
        data = encode_png(page.image)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        decoded = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(decoded.shape, page.image.shape)


class DocumentApiTests(unittest.TestCase):
    """The PDF endpoints, end to end, on the mock recognition engine."""

    @classmethod
    def setUpClass(cls) -> None:
        import os
        import tempfile

        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["EVALNOVA_OCR_PROVIDER"] = "mock"
        os.environ["EVALNOVA_DATABASE_URL"] = f"sqlite:///{cls._tmp.name}/pdf.db"
        os.environ["EVALNOVA_STORAGE_DIR"] = cls._tmp.name

        from app.core.config import get_settings

        get_settings.cache_clear()

        from fastapi.testclient import TestClient

        from app.db.session import init_db
        from app.main import app

        init_db()
        cls.client = TestClient(app)
        cls.pdf = make_pdf(3)

    @classmethod
    def tearDownClass(cls) -> None:
        # Windows will not delete a file SQLAlchemy still holds open, so the
        # connection pool has to go first.
        from app.db.session import engine

        engine.dispose()
        try:
            cls._tmp.cleanup()
        except OSError:
            pass  # a stray lock must not fail an otherwise passing run

    def test_inspect_reports_pages_and_an_estimate(self) -> None:
        response = self.client.post(
            "/api/v1/documents/inspect",
            files={"file": ("booklet.pdf", self.pdf, "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_pages"], 3)
        self.assertGreater(body["estimated_seconds"], 0)

    def test_inspect_rejects_an_image(self) -> None:
        response = self.client.post(
            "/api/v1/documents/inspect",
            files={"file": ("x.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )
        self.assertEqual(response.status_code, 400)

    def test_transcribe_produces_one_answer_per_page(self) -> None:
        response = self.client.post(
            "/api/v1/documents/transcribe",
            files={"file": ("booklet.pdf", self.pdf, "application/pdf")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()

        self.assertEqual(body["total_pages"], 3)
        self.assertEqual(body["pages_processed"], 3)
        self.assertEqual(len(body["pages"]), 3)
        self.assertEqual([p["page_number"] for p in body["pages"]], [1, 2, 3])

        for page in body["pages"]:
            self.assertIsNone(page["error"])
            self.assertEqual(page["answer"]["page_number"], page["page_number"])
            self.assertEqual(page["answer"]["document_ref"], body["document_ref"])

    def test_a_page_range_limits_the_work(self) -> None:
        response = self.client.post(
            "/api/v1/documents/transcribe",
            files={"file": ("booklet.pdf", self.pdf, "application/pdf")},
            data={"pages": "2"},
        )
        body = response.json()
        self.assertEqual(body["pages_processed"], 1)
        self.assertEqual(body["pages"][0]["page_number"], 2)
        self.assertTrue(any("2 of 3" in w or "1 of 3" in w for w in body["warnings"]))

    def test_document_confidence_is_in_range(self) -> None:
        body = self.client.post(
            "/api/v1/documents/transcribe",
            files={"file": ("booklet.pdf", self.pdf, "application/pdf")},
        ).json()
        self.assertGreaterEqual(body["overall_confidence"], 0.0)
        self.assertLessEqual(body["overall_confidence"], 1.0)

    def test_combined_text_contains_every_page(self) -> None:
        body = self.client.post(
            "/api/v1/documents/transcribe",
            files={"file": ("booklet.pdf", self.pdf, "application/pdf")},
        ).json()
        combined = body["combined_text"]
        for page in body["pages"]:
            self.assertIn(page["ocr"]["extracted_text"].strip(), combined)

    def test_pages_are_retrievable_by_document_reference(self) -> None:
        created = self.client.post(
            "/api/v1/documents/transcribe",
            files={"file": ("booklet.pdf", self.pdf, "application/pdf")},
        ).json()
        response = self.client.get(f"/api/v1/documents/{created['document_ref']}")
        self.assertEqual(response.status_code, 200)
        pages = response.json()
        self.assertEqual(len(pages), 3)
        self.assertEqual([p["page_number"] for p in pages], [1, 2, 3])

    def test_unknown_document_is_404(self) -> None:
        self.assertEqual(self.client.get("/api/v1/documents/nope").status_code, 404)

    def test_an_image_sent_to_the_document_endpoint_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/documents/transcribe",
            files={"file": ("x.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not a PDF", response.json()["detail"])

    def test_an_impossible_page_range_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/documents/transcribe",
            files={"file": ("booklet.pdf", self.pdf, "application/pdf")},
            data={"pages": "40-50"},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
