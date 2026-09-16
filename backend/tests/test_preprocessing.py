"""Tests for image preprocessing and line segmentation."""

from __future__ import annotations

import unittest
from pathlib import Path

import cv2
import numpy as np

from app.services.preprocessing import (
    ImageLoadError,
    assess_quality,
    crop_line,
    estimate_skew,
    load_image,
    merge_thin_lines,
    preprocess,
    segment_lines,
    sharpness_penalty,
)

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"


def page_with_lines(count: int = 5, width: int = 1200, spacing: int = 90) -> np.ndarray:
    """A synthetic page: dark text bars on light paper."""
    height = spacing * (count + 1)
    image = np.full((height, width, 3), 245, dtype=np.uint8)
    for i in range(count):
        y = spacing * (i + 1)
        cv2.putText(
            image,
            "the quick brown fox jumps over the lazy dog",
            (60, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.1,
            (30, 30, 30),
            2,
            cv2.LINE_AA,
        )
    return image


class SegmentationTests(unittest.TestCase):
    def test_finds_every_line(self) -> None:
        for count in (1, 3, 7):
            with self.subTest(lines=count):
                _, boxes, report = preprocess(page_with_lines(count))
                self.assertEqual(len(boxes), count)
                self.assertEqual(report.detected_lines, count)

    def test_boxes_are_ordered_top_to_bottom(self) -> None:
        _, boxes, _ = preprocess(page_with_lines(5))
        tops = [y for _, y, _, _ in boxes]
        self.assertEqual(tops, sorted(tops))

    def test_boxes_do_not_overlap(self) -> None:
        _, boxes, _ = preprocess(page_with_lines(5))
        for (_, y1, _, h1), (_, y2, _, _) in zip(boxes, boxes[1:]):
            self.assertLessEqual(y1 + h1, y2 + 1)

    def test_blank_page_yields_no_lines(self) -> None:
        blank = np.full((600, 1200, 3), 250, dtype=np.uint8)
        _, boxes, report = preprocess(blank)
        self.assertEqual(boxes, [])
        self.assertEqual(report.detected_lines, 0)

    def test_all_black_image_does_not_crash(self) -> None:
        _, boxes, _ = preprocess(np.zeros((400, 800, 3), dtype=np.uint8))
        self.assertIsInstance(boxes, list)

    def test_respects_the_line_cap(self) -> None:
        _, boxes, _ = preprocess(page_with_lines(8), max_lines=3)
        self.assertEqual(len(boxes), 3)

    def test_empty_binary_returns_no_boxes(self) -> None:
        self.assertEqual(segment_lines(np.zeros((200, 400), dtype=np.uint8)), [])


class InkPreservationTests(unittest.TestCase):
    """Cleaning must remove paper features without eating the writing."""

    @staticmethod
    def ink_kept(page: np.ndarray) -> float:
        gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
        clean, _, _ = preprocess(page)
        return float((clean < 160).sum()) / max(float((gray < 160).sum()), 1.0)

    def test_fine_pen_strokes_survive(self) -> None:
        # The crisp sample sheet has strokes ~2px wide - exactly what a
        # morphological opening erases. OpenCV's own fonts are too thick to
        # show that failure, so the real sample is used when present.
        sample = SAMPLES / "sample_answer_clean.png"
        if not sample.exists():
            self.skipTest("run scripts/generate_sample_answer.py --all first")
        self.assertGreater(self.ink_kept(load_image(sample)), 0.95)

    def test_neat_baselines_are_not_mistaken_for_ruling(self) -> None:
        # Ten lines of thin text on perfectly straight baselines: a straight-
        # line detector sees each baseline as a rule unless it checks what
        # lies beside the line.
        page = np.full((1100, 1700, 3), 248, dtype=np.uint8)
        for i in range(10):
            cv2.putText(page, "polymorphism means many forms", (110, 90 + i * 95),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (78, 38, 26), 1, cv2.LINE_AA)
        self.assertGreater(self.ink_kept(page), 0.97)


class MergeThinLinesTests(unittest.TestCase):
    def test_fragment_merges_into_the_line_above(self) -> None:
        boxes = [(0, 0, 100, 30), (0, 32, 20, 6)]
        merged = merge_thin_lines(boxes, median_height=30)
        self.assertEqual(len(merged), 1)
        # The merged box must still cover both originals.
        x, y, w, h = merged[0]
        self.assertEqual((x, y), (0, 0))
        self.assertGreaterEqual(y + h, 38)

    def test_normal_lines_are_left_alone(self) -> None:
        boxes = [(0, 0, 100, 30), (0, 40, 100, 30)]
        self.assertEqual(merge_thin_lines(boxes, 30), boxes)

    def test_empty_input(self) -> None:
        self.assertEqual(merge_thin_lines([], 30), [])


class QualityTests(unittest.TestCase):
    def test_blur_lowers_the_sharpness_score(self) -> None:
        page = cv2.cvtColor(page_with_lines(4), cv2.COLOR_BGR2GRAY)
        sharp, _ = assess_quality(page)
        soft, _ = assess_quality(cv2.GaussianBlur(page, (9, 9), 4))
        self.assertLess(soft, sharp)

    def test_faint_ink_is_flagged_as_low_contrast(self) -> None:
        page = cv2.cvtColor(page_with_lines(4), cv2.COLOR_BGR2GRAY)
        _, crisp_flag = assess_quality(page)
        # Compress the intensity range towards mid-grey.
        faint = (page.astype(np.float32) * 0.12 + 200).clip(0, 255).astype(np.uint8)
        _, faint_flag = assess_quality(faint)
        self.assertFalse(crisp_flag)
        self.assertTrue(faint_flag)

    def test_sharpness_penalty_is_bounded(self) -> None:
        self.assertEqual(sharpness_penalty(1000.0), 1.0)
        self.assertGreaterEqual(sharpness_penalty(0.0), 0.55)
        self.assertLessEqual(sharpness_penalty(0.0), 1.0)


class SkewTests(unittest.TestCase):
    def test_rotated_page_reports_an_angle(self) -> None:
        page = page_with_lines(6)
        gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
        centre = (gray.shape[1] / 2, gray.shape[0] / 2)
        rotated = cv2.warpAffine(
            gray,
            cv2.getRotationMatrix2D(centre, 4.0, 1.0),
            (gray.shape[1], gray.shape[0]),
            borderMode=cv2.BORDER_REPLICATE,
        )
        self.assertGreater(abs(estimate_skew(rotated)), 1.0)

    def test_straight_page_reports_near_zero(self) -> None:
        gray = cv2.cvtColor(page_with_lines(6), cv2.COLOR_BGR2GRAY)
        self.assertLess(abs(estimate_skew(gray)), 1.5)

    def test_absurd_angles_are_rejected(self) -> None:
        noise = np.random.default_rng(0).integers(0, 255, (300, 300), dtype=np.uint8)
        self.assertLessEqual(abs(estimate_skew(noise)), 15.0)


class CropTests(unittest.TestCase):
    def test_crop_is_three_channel_and_tall_enough(self) -> None:
        gray = cv2.cvtColor(page_with_lines(3), cv2.COLOR_BGR2GRAY)
        crop = crop_line(gray, (10, 10, 200, 20))
        self.assertEqual(crop.shape[2], 3)
        self.assertGreaterEqual(crop.shape[0], 48)

    def test_zero_area_crop_does_not_crash(self) -> None:
        gray = cv2.cvtColor(page_with_lines(1), cv2.COLOR_BGR2GRAY)
        self.assertEqual(crop_line(gray, (0, 0, 0, 0)).shape[2], 3)


class LoadTests(unittest.TestCase):
    def test_missing_file_raises(self) -> None:
        with self.assertRaises(ImageLoadError):
            load_image("no-such-file-anywhere.png")


if __name__ == "__main__":
    unittest.main()
