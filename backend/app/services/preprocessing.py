"""Image preprocessing and handwriting line segmentation.

Handwriting recognition models read *one line at a time*. Feeding them a whole
scanned page produces nonsense, so the real work of this module is turning a
photographed answer sheet into an ordered list of clean line images.

The pipeline:

    load -> resize -> grayscale -> light denoise -> quality assessment
         -> flatten illumination -> isolate ink (drop red/orange print and
            examiner marks, drop faint show-through from the back of the sheet)
         -> remove printed ruling and margin lines -> classify the page
         -> deskew -> projection profile -> line boxes -> per-line crops

Real answer booklets are ruled, printed in colour, and written on both sides.
Every one of those features looks like "ink" to a naive threshold, and a
recogniser handed a ruled line will confidently invent a sentence for it. So
the recogniser is given a *cleaned* page: the student's strokes on white, and
nothing else.

Every stage records what it did in a `PreprocessingReport`, because Part 1 is
required to explain *why* a transcription failed, not merely that it did.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from app.schemas.ocr import PreprocessingReport

# A page photographed on a phone is often huge; anything past this width adds
# processing time without adding legible detail.
MAX_WIDTH = 2000
# Below this, upscaling helps the recogniser more than it hurts.
MIN_WIDTH = 1000

BLUR_THRESHOLD = 90.0           # Laplacian variance below this reads as soft focus
LOW_CONTRAST_THRESHOLD = 90.0   # ink-to-paper intensity separation
MIN_LINE_HEIGHT = 12           # px, after normalisation
MAX_SKEW_DEG = 8.0

# A ruling line is a straight run of ink at least this fraction of the page.
RULE_MIN_FRACTION = 1 / 12
# A page whose coloured print outweighs its handwriting several times over is
# a cover or form page, not an answer.
FORM_WARM_FRACTION = 0.02
FORM_WARM_TO_INK = 1.5

PAGE_HANDWRITING = "handwriting"
PAGE_PRINTED_FORM = "printed_form"


class ImageLoadError(ValueError):
    """The file could not be decoded as an image."""


def load_image(path: str | Path) -> np.ndarray:
    """Read an image from disk as BGR.

    Uses numpy + imdecode rather than cv2.imread so that non-ASCII paths work
    on Windows, where imread silently returns None.
    """
    path = Path(path)
    if not path.exists():
        raise ImageLoadError(f"No such image: {path}")
    try:
        buffer = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    except Exception as exc:  # pragma: no cover - defensive
        raise ImageLoadError(f"Could not decode image: {exc}") from exc
    if image is None or image.size == 0:
        raise ImageLoadError(
            "The file is not a readable image. Upload a JPEG, PNG, WEBP, BMP or TIFF."
        )
    return image


def _normalise_size(image: np.ndarray, report: PreprocessingReport) -> np.ndarray:
    height, width = image.shape[:2]
    if width > MAX_WIDTH:
        scale = MAX_WIDTH / width
        image = cv2.resize(
            image, (MAX_WIDTH, int(height * scale)), interpolation=cv2.INTER_AREA
        )
        report.steps.append(f"downscaled to {MAX_WIDTH}px wide")
    elif width < MIN_WIDTH:
        scale = MIN_WIDTH / width
        image = cv2.resize(
            image, (MIN_WIDTH, int(height * scale)), interpolation=cv2.INTER_CUBIC
        )
        report.steps.append(f"upscaled to {MIN_WIDTH}px wide")
    return image


def assess_quality(gray: np.ndarray) -> tuple[float, bool]:
    """Return (blur_score, is_low_contrast).

    Blur score is the variance of the Laplacian - a standard sharpness proxy.
    Low values mean soft focus, which is the most common cause of a bad
    transcription from a phone photo.

    Contrast is measured as the separation between ink and paper, not the
    standard deviation of the whole image. On a page of handwriting the vast
    majority of pixels are background, so a global std-dev stays low even on a
    perfectly crisp scan and would flag every page as faint. Otsu's method
    splits the two populations, and we compare their means.
    """
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    threshold, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink_pixels = gray[gray <= threshold]
    paper_pixels = gray[gray > threshold]
    if ink_pixels.size == 0 or paper_pixels.size == 0:
        return blur_score, True

    separation = float(paper_pixels.mean() - ink_pixels.mean())
    return blur_score, separation < LOW_CONTRAST_THRESHOLD


# ---------------------------------------------------------------------------
# Ink isolation
# ---------------------------------------------------------------------------


def estimate_paper(gray: np.ndarray) -> np.ndarray:
    """The brightness the paper would have at every pixel if nothing were written.

    Ink is removed with a dilation (a local maximum), then a wide median smooths
    what is left. Done at quarter resolution: the paper's shading varies slowly,
    so detail there is wasted work.
    """
    height, width = gray.shape[:2]
    small = cv2.resize(
        gray, (max(width // 4, 1), max(height // 4, 1)), interpolation=cv2.INTER_AREA
    )
    small = cv2.dilate(small, np.ones((5, 5), np.uint8))
    small = cv2.medianBlur(small, 21 if min(small.shape[:2]) > 21 else 3)
    return cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)


def flatten_illumination(gray: np.ndarray, paper: np.ndarray) -> np.ndarray:
    """Divide out the paper so a shadowed corner reads like a lit one.

    The result has paper at ~255 everywhere and ink darker in proportion to how
    much light it actually absorbs, which makes one threshold valid across the
    whole page.
    """
    ratio = gray.astype(np.float32) / np.maximum(paper, 1).astype(np.float32)
    return np.clip(ratio * 255.0, 0, 255).astype(np.uint8)


def warm_colour_mask(bgr: np.ndarray, paper: np.ndarray) -> np.ndarray:
    """Red and orange marks on paper: printed forms and the examiner's pen.

    Neither is the student's answer. Restricted to bright paper so that a
    wooden desk showing at the edge of a phone photo is not mistaken for print.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    warm = ((hue <= 25) | (hue >= 160)) & (saturation >= 70) & (value >= 60)
    return warm & (paper > 140)


def ink_threshold(flat: np.ndarray) -> float:
    """How dark a pixel must be, relative to paper, to count as ink.

    Set halfway between the darkest strokes on the page and the paper. A fixed
    value either misses faint pencil-grey ink on a washed-out photo or admits
    the mirror-image writing that shows through from the back of the sheet;
    anchoring to the page's own darkest ink handles both.
    """
    darkest = float(np.percentile(flat, 0.3))
    return float(np.clip((darkest + 255.0) / 2.0, 120.0, 215.0))


def _remove_specks(mask: np.ndarray, min_area: int = 12) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return mask
    keep = np.zeros(count, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[labels].astype(np.uint8) * 255


def _looks_like_rule(mask: np.ndarray, segment: tuple[int, int, int, int]) -> bool:
    """Is this straight run of ink a printed rule, or a row of writing?

    Neat writing lines its letters up on a baseline, and the Hough transform
    happily reports that as a line. The difference is what lies beside it: a
    rule is dense along its own path with bare paper on either side, while a
    baseline has letter bodies right next to it.
    """
    x1, y1, x2, y2 = segment
    on_path = np.zeros_like(mask)
    cv2.line(on_path, (x1, y1), (x2, y2), 255, 3)
    # "Beside" starts ~10px out, so the twin of a double margin rule counts as
    # part of the rule, and ends ~22px out, where letter bodies would sit.
    near = np.zeros_like(mask)
    cv2.line(near, (x1, y1), (x2, y2), 255, 45)
    beside = cv2.bitwise_and(near, cv2.bitwise_not(cv2.dilate(on_path, np.ones((19, 19), np.uint8))))

    along = float((mask[on_path > 0] > 0).mean())
    around = float((mask[beside > 0] > 0).mean()) if beside.any() else 0.0
    return along >= 0.45 and around <= along * 0.25


def remove_ruling(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Strip printed ruling and margin lines from an ink mask.

    Returns (mask without rules, the rules that were removed).

    Two passes. First, any perfectly straight run of ink longer than a twelfth
    of the page is a rule - handwriting has no such strokes. Second, rules are
    often broken where the page curves or the ink is faint, leaving short
    dashes behind; any thin dash lying *on* a row (or column) already known to
    hold a rule goes too. Dots and letters are kept: only dash-shaped pieces
    are removed, and only on rule rows.
    """
    height, width = mask.shape[:2]
    horizontal = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(int(width * RULE_MIN_FRACTION), 20), 1)),
    )
    vertical = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(int(height * RULE_MIN_FRACTION), 20))),
    )
    rules = cv2.dilate(cv2.bitwise_or(horizontal, vertical), np.ones((3, 3), np.uint8))
    cleaned = cv2.bitwise_and(mask, cv2.bitwise_not(rules))

    # A photographed page is never perfectly flat, so one rule wanders across
    # a few rows; smear before measuring how much of each row is rule.
    rows_band = cv2.dilate(horizontal, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 9)))
    cols_band = cv2.dilate(vertical, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1)))
    rule_rows = (rows_band > 0).sum(axis=1) > width * 0.10
    rule_cols = (cols_band > 0).sum(axis=0) > height * 0.10

    count, labels, stats, centroids = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
    widths = stats[:, cv2.CC_STAT_WIDTH]
    heights = stats[:, cv2.CC_STAT_HEIGHT]
    # A double margin line fuses into a component a little wider than one
    # rule, hence the more generous limit down the page than across it.
    dash_h = (heights <= 10) & (widths >= 2 * heights)
    dash_v = (widths <= 16) & (heights >= 2 * widths)
    dash_h[0] = dash_v[0] = False

    # A rule too faint to survive as one piece still leaves a dashed straight
    # line. A probabilistic Hough transform bridges the short gaps between
    # dashes, but not the much larger gap between one written line and the
    # next - so letter stems that merely happen to line up at the left margin
    # are not mistaken for a ruled margin.
    broken = np.zeros_like(mask)
    for is_vertical, length in ((False, width), (True, height)):
        min_length = int(length * 0.2)
        segments = cv2.HoughLinesP(
            cleaned, 1, np.pi / 360, threshold=max(int(min_length * 0.4), 30),
            minLineLength=min_length, maxLineGap=24,
        )
        # OpenCV versions disagree on the result's shape; flatten to (N, 4).
        for x1, y1, x2, y2 in ([] if segments is None else segments.reshape(-1, 4)):
            dx, dy = abs(int(x2) - int(x1)), abs(int(y2) - int(y1))
            straight = dx >= 25 * dy if not is_vertical else dy >= 25 * dx
            if straight and _looks_like_rule(cleaned, (int(x1), int(y1), int(x2), int(y2))):
                cv2.line(broken, (int(x1), int(y1)), (int(x2), int(y2)), 255, 5)

    rule_rows = np.convolve(rule_rows, np.ones(9), mode="same") > 0
    rule_cols = np.convolve(rule_cols, np.ones(13), mode="same") > 0
    if not rule_rows.any() and not rule_cols.any() and not broken.any():
        return cleaned, rules

    drop = np.zeros(count, dtype=bool)
    for index in np.where(dash_h | dash_v)[0]:
        cx, cy = centroids[index]
        if dash_h[index] and rule_rows[min(int(cy), height - 1)]:
            drop[index] = True
        elif dash_v[index] and rule_cols[min(int(cx), width - 1)]:
            drop[index] = True
        elif broken.any():
            x, y = stats[index, cv2.CC_STAT_LEFT], stats[index, cv2.CC_STAT_TOP]
            piece = labels[y : y + heights[index], x : x + widths[index]] == index
            on_line = broken[y : y + heights[index], x : x + widths[index]][piece] > 0
            drop[index] = on_line.mean() >= 0.8
    if drop.any():
        fragments = drop[labels]
        cleaned[fragments] = 0
        rules[fragments] = 255

    return cleaned, rules


def binarize(gray: np.ndarray) -> np.ndarray:
    """Ink as white on black, robust to uneven lighting across a page.

    Kept for callers that have only a grayscale image; `preprocess` uses the
    colour-aware path in `isolate_ink` instead.
    """
    paper = estimate_paper(gray)
    flat = flatten_illumination(gray, paper)
    mask = (flat < ink_threshold(flat)).astype(np.uint8) * 255
    speck_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, speck_kernel, iterations=1)


def isolate_ink(
    bgr: np.ndarray, gray: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    """Find the student's strokes and nothing else.

    Returns (flattened grayscale, ink mask, measurements).
    """
    paper = estimate_paper(gray)
    flat = flatten_illumination(gray, paper)
    warm = warm_colour_mask(bgr, paper)

    threshold = ink_threshold(flat)
    mask = ((flat < threshold) & ~warm).astype(np.uint8) * 255
    # Specks are removed by size, not with a morphological opening: an opening
    # also erases every stroke thinner than its kernel, and a fine pen on a
    # modest-resolution photo is exactly that thin.
    mask = _remove_specks(mask)
    mask, rules = remove_ruling(mask)
    mask = _remove_specks(mask)

    return flat, mask, {
        "ink_threshold": round(threshold, 1),
        "warm_fraction": float(warm.mean()),
        "rule_fraction": float((rules > 0).mean()),
        "ink_fraction": float((mask > 0).mean()),
    }


def render_clean_page(flat: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """The student's strokes on white - what the recogniser is shown.

    The mask is widened by a pixel so anti-aliased stroke edges survive, and
    the ink is stretched so that a faint pen reads as firmly as a dark one.
    """
    keep = cv2.dilate(mask, np.ones((3, 3), np.uint8)) > 0
    clean = np.full_like(flat, 255)
    if not keep.any():
        return clean
    darkest = float(np.percentile(flat[mask > 0], 5)) if mask.any() else 0.0
    scale = min(225.0 / max(255.0 - darkest, 1.0), 3.0)
    stretched = 255.0 - (255.0 - flat.astype(np.float32)) * scale
    clean[keep] = np.clip(stretched[keep], 0, 255).astype(np.uint8)
    return clean


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def _skew_from_mask(mask: np.ndarray) -> float:
    """Rotation that makes text rows sharpest in the horizontal projection.

    Text lines are horizontal bands of ink; when the page is straight, the
    row-sum profile has tall peaks and empty troughs, so its variance is at a
    maximum. A coarse search followed by a fine one, on a small copy.
    """
    if mask is None or not mask.any():
        return 0.0
    height, width = mask.shape[:2]
    scale = 500.0 / max(width, 1)
    small = cv2.resize(
        mask.astype(np.float32),
        (max(int(width * scale), 1), max(int(height * scale), 1)),
        interpolation=cv2.INTER_AREA,
    )
    if small.sum() < 50:
        return 0.0
    centre = (small.shape[1] / 2, small.shape[0] / 2)

    def sharpness(angle: float) -> float:
        matrix = cv2.getRotationMatrix2D(centre, angle, 1.0)
        rotated = cv2.warpAffine(small, matrix, (small.shape[1], small.shape[0]))
        return float(rotated.sum(axis=1).var())

    coarse = np.arange(-MAX_SKEW_DEG, MAX_SKEW_DEG + 0.01, 0.5)
    best = max(coarse, key=sharpness)
    fine = np.arange(best - 0.5, best + 0.51, 0.1)
    best = max(fine, key=sharpness)
    return float(round(best, 2))


def estimate_skew(gray: np.ndarray) -> float:
    """Estimate the rotation, in degrees, that straightens the page.

    Bounded to +/- MAX_SKEW_DEG so a failure of the estimator can never turn a
    page sideways.
    """
    inverted = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    return _skew_from_mask(inverted)


def rotate(image: np.ndarray, angle: float, fill: int | None = None) -> np.ndarray:
    if abs(angle) < 0.1:
        return image
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    if fill is None:
        return cv2.warpAffine(
            image, matrix, (width, height),
            flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
        )
    return cv2.warpAffine(
        image, matrix, (width, height),
        flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=fill,
    )


def _main_ink_span(band: np.ndarray, gap: int) -> tuple[int, int] | None:
    """Horizontal extent of a line, ignoring stray marks far from the writing.

    Columns of ink are grouped into clusters separated by wide empty gaps; a
    cluster holding almost none of the line's ink (a leftover scrap of ruling,
    a speck at the page edge) is dropped. Without this one dot at the margin
    stretches the crop across the page, and the recogniser - which squeezes
    every line into a fixed-size square - sees the real words shrunk to a blur.
    """
    column_ink = (band > 0).sum(axis=0)
    columns = np.where(column_ink > 0)[0]
    if columns.size == 0:
        return None
    breaks = np.where(np.diff(columns) > gap)[0]
    starts = np.concatenate(([columns[0]], columns[breaks + 1]))
    ends = np.concatenate((columns[breaks], [columns[-1]]))
    total = float(column_ink.sum())
    kept = [
        (int(s), int(e))
        for s, e in zip(starts, ends)
        if column_ink[s : e + 1].sum() >= total * 0.04
        and not (column_ink[s : e + 1].sum() < total * 0.08 and e - s < 50)
    ]
    if not kept:
        return None
    return kept[0][0], kept[-1][1]


def segment_lines(binary: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Find handwriting lines using a horizontal projection profile.

    Words are first smeared sideways so that the gaps between them close and
    each text line becomes one continuous horizontal band. Summing ink per row
    then produces peaks for lines and troughs for the gaps between them.

    Returns boxes as (x, y, w, h), ordered top to bottom.
    """
    height, width = binary.shape[:2]

    # Smear width scales with the page so it works at any resolution.
    smear = max(15, width // 45)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (smear, 3))
    smeared = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

    projection = (smeared > 0).sum(axis=1).astype(np.float32)
    if projection.max() <= 0:
        return []

    # Light vertical smoothing so that a single ragged row does not chop a
    # line in half.
    projection = cv2.GaussianBlur(projection.reshape(-1, 1), (1, 5), 0).ravel()

    # Otsu finds the natural split between "row containing text" and "row in a
    # gap". A fixed fraction of the maximum fails on blurred or low-contrast
    # pages, where ink bleeds vertically and the gaps never fall to zero - the
    # whole page then merges into one band. With the page cleaned of rules the
    # gaps are genuinely empty, so the floor can sit low enough to keep a line
    # holding only a question number.
    scaled = np.clip(projection / projection.max() * 255.0, 0, 255).astype(np.uint8)
    otsu_level, _ = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = min(
        max(float(otsu_level) / 255.0 * float(projection.max()), width * 0.004),
        max(width * 0.004, float(projection.max()) * 0.03),
    )
    is_text = projection > threshold

    boxes: list[tuple[int, int]] = []
    start: int | None = None
    for row in range(height):
        if is_text[row] and start is None:
            start = row
        elif not is_text[row] and start is not None:
            boxes.append((start, row))
            start = None
    if start is not None:
        boxes.append((start, height))

    results: list[tuple[int, int, int, int]] = []
    for top, bottom in boxes:
        if bottom - top < MIN_LINE_HEIGHT:
            continue
        band = binary[top:bottom, :]
        span = _main_ink_span(band, gap=max(60, width // 12))
        if span is None:
            continue
        left, right = span
        band = band[:, left : right + 1]
        rows = np.where((band > 0).any(axis=1))[0]
        if rows.size == 0:
            continue
        if right - left < 20:
            continue
        # Tighten to the ink actually present; the smear widens bands.
        ink_top, ink_bottom = top + int(rows[0]), top + int(rows[-1]) + 1
        # A little padding: descenders and ascenders sit outside the ink band.
        pad_y = max(4, (ink_bottom - ink_top) // 6)
        pad_x = 10
        y0 = max(0, ink_top - pad_y)
        y1 = min(height, ink_bottom + pad_y)
        x0 = max(0, left - pad_x)
        x1 = min(width, right + pad_x)
        results.append((x0, y0, x1 - x0, y1 - y0))

    # Padding can make neighbours touch; split the difference so crops never
    # overlap and no stroke is read twice.
    for i in range(len(results) - 1):
        x, y, w, h = results[i]
        nx, ny, nw, nh = results[i + 1]
        if y + h > ny:
            middle = (y + h + ny) // 2
            results[i] = (x, y, w, max(middle - y, 1))
            results[i + 1] = (nx, middle, nw, max(ny + nh - middle, 1))

    return results


def split_tall_lines(
    mask: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    median_height: float,
) -> list[tuple[int, int, int, int]]:
    """Cut apart two lines that a tall stroke has fused into one band.

    An exponent, a descender or a fraction bar can bridge the gap between two
    written lines, and the projection profile then reports one band twice the
    usual height. The recogniser reads only one line per crop, so the second
    line would silently vanish. A band much taller than the page's typical
    line is split at its emptiest row near the middle, recursively.
    """
    if not boxes or median_height <= 0:
        return boxes
    height, width = mask.shape[:2]
    result: list[tuple[int, int, int, int]] = []
    pending = list(boxes)
    while pending:
        x, y, w, h = pending.pop(0)
        if h <= median_height * 1.8 or h < 2 * MIN_LINE_HEIGHT:
            result.append((x, y, w, h))
            continue
        profile = (mask[y : y + h, x : x + w] > 0).sum(axis=1).astype(np.float32)
        profile = np.convolve(profile, np.ones(5) / 5, mode="same")
        lo, hi = int(h * 0.25), int(h * 0.75)
        if hi <= lo:
            result.append((x, y, w, h))
            continue
        cut = lo + int(np.argmin(profile[lo:hi]))
        parts = []
        for top, bottom in ((y, y + cut), (y + cut, y + h)):
            band = mask[top:bottom, x : x + w]
            rows = np.where((band > 0).any(axis=1))[0]
            span = _main_ink_span(band, gap=max(60, width // 12))
            if rows.size == 0 or span is None:
                continue
            t, b = top + int(rows[0]), top + int(rows[-1]) + 1
            if b - t < MIN_LINE_HEIGHT // 2:
                continue
            pad_y = max(4, (b - t) // 8)
            t, b = max(top, t - pad_y), min(bottom, b + pad_y)
            left, right = x + span[0], x + span[1]
            x0, x1 = max(0, left - 10), min(width, right + 10)
            parts.append((x0, t, x1 - x0, b - t))
        if len(parts) < 2:
            result.append((x, y, w, h))
        else:
            pending[0:0] = parts
    result.sort(key=lambda box: box[1])
    return result


def merge_thin_lines(
    boxes: list[tuple[int, int, int, int]], median_height: float
) -> list[tuple[int, int, int, int]]:
    """Fold stray fragments into the nearest real line.

    A dotted 'i', an exponent written above the line, or a stray mark can
    produce its own tiny band. Anything under a third of the typical line
    height is merged into whichever neighbour is vertically closer, rather than
    sent to the recogniser as a line of its own - an exponent belongs to the
    line *below* it, a descender fragment to the one above.
    """
    if not boxes:
        return boxes

    def union(a, b):
        x0, y0 = min(a[0], b[0]), min(a[1], b[1])
        x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
        return (x0, y0, x1 - x0, y1 - y0)

    remaining = list(boxes)
    merged: list[tuple[int, int, int, int]] = []
    i = 0
    while i < len(remaining):
        box = remaining[i]
        if box[3] >= median_height * 0.34:
            merged.append(box)
            i += 1
            continue
        gap_up = box[1] - (merged[-1][1] + merged[-1][3]) if merged else math.inf
        nxt = remaining[i + 1] if i + 1 < len(remaining) else None
        gap_down = nxt[1] - (box[1] + box[3]) if nxt is not None else math.inf
        if merged and gap_up <= gap_down:
            merged[-1] = union(merged[-1], box)
        elif nxt is not None:
            remaining[i + 1] = union(box, nxt)
        else:
            merged.append(box)
        i += 1
    return merged


def preprocess(
    image: np.ndarray, max_lines: int = 40
) -> tuple[np.ndarray, list[tuple[int, int, int, int]], PreprocessingReport]:
    """Run the full pipeline.

    Returns the cleaned page (the student's ink on white, which is what the
    line crops are cut from), the ordered line boxes, and a report of
    everything that happened along the way.
    """
    report = PreprocessingReport()
    report.original_size = (int(image.shape[1]), int(image.shape[0]))

    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    image = _normalise_size(image, report)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    report.steps.append("converted to grayscale")

    # A 3x3 median removes sensor speckle at a fraction of the cost of
    # non-local-means, which took seconds on a full page.
    gray = cv2.medianBlur(gray, 3)
    report.steps.append("denoised")

    # Quality is assessed *after* denoising, deliberately. Sensor noise raises
    # Laplacian variance, so a grainy photograph of soft handwriting would
    # otherwise score as razor sharp - the opposite of the truth.
    blur_score, is_low_contrast = assess_quality(gray)
    report.blur_score = round(blur_score, 2)
    report.is_low_contrast = is_low_contrast

    flat, mask, measures = isolate_ink(image, gray)
    report.steps.append("illumination flattened")
    report.steps.append(
        f"ink isolated (threshold {measures['ink_threshold']:.0f}; coloured print, "
        "examiner marks and show-through dropped)"
    )
    if measures["rule_fraction"] > 0.002:
        report.steps.append("printed ruling lines removed")
    report.ruling_removed = measures["rule_fraction"] > 0.002

    if (
        measures["warm_fraction"] > FORM_WARM_FRACTION
        and measures["warm_fraction"] > FORM_WARM_TO_INK * measures["ink_fraction"]
    ):
        report.page_kind = PAGE_PRINTED_FORM
        report.steps.append("classified as a printed cover/form page")

    angle = _skew_from_mask(mask)
    if abs(angle) >= 0.1:
        flat = rotate(flat, angle)
        mask = rotate(mask, angle, fill=0)
        report.steps.append(f"deskewed by {angle:.2f} deg")
    report.deskew_angle_deg = round(angle, 2)

    clean = render_clean_page(flat, mask)
    report.processed_size = (int(clean.shape[1]), int(clean.shape[0]))

    boxes = segment_lines(mask)
    if boxes:
        median_height = float(np.median([h for _, _, _, h in boxes]))
        boxes = merge_thin_lines(boxes, median_height)
        boxes = split_tall_lines(mask, boxes, median_height)
    report.steps.append("segmented lines by projection profile")

    report.estimated_ink_coverage = round(float((mask > 0).mean()), 4)
    report.detected_lines = len(boxes)

    if len(boxes) > max_lines:
        boxes = boxes[:max_lines]
        report.steps.append(f"truncated to first {max_lines} lines")

    return clean, boxes, report


def line_ink_fraction(page: np.ndarray, box: tuple[int, int, int, int]) -> float:
    """Share of a line box that is ink - near zero means nothing to read."""
    x, y, w, h = box
    crop = page[y : y + h, x : x + w]
    if crop.size == 0:
        return 0.0
    return float((crop < 200).mean())


def crop_line(gray: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """Cut one line out of the page and present it the way TrOCR expects:
    dark text on a light background, as a 3-channel image."""
    x, y, w, h = box
    crop = gray[y : y + h, x : x + w]
    if crop.size == 0:
        crop = np.full((32, 32), 255, dtype=np.uint8)
    # Slight upscaling of short lines measurably helps recognition.
    if crop.shape[0] < 48:
        scale = 48 / max(crop.shape[0], 1)
        crop = cv2.resize(
            crop,
            (max(int(crop.shape[1] * scale), 1), 48),
            interpolation=cv2.INTER_CUBIC,
        )
    return cv2.cvtColor(crop, cv2.COLOR_GRAY2RGB)


def render_debug_overlay(
    gray: np.ndarray, boxes: list[tuple[int, int, int, int]]
) -> np.ndarray:
    """Draw the detected line boxes onto the page.

    Shown in the UI so an examiner can see at a glance whether segmentation -
    rather than recognition - is what went wrong.
    """
    canvas = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for index, (x, y, w, h) in enumerate(boxes, start=1):
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (92, 107, 15), 2)
        label_y = max(y - 6, 14)
        cv2.putText(
            canvas,
            str(index),
            (x, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (92, 107, 15),
            2,
            cv2.LINE_AA,
        )
    return canvas


def sharpness_penalty(blur_score: float) -> float:
    """Map a blur score onto a 0-1 multiplier used in confidence.

    A soft photo makes every line less trustworthy, and that should be visible
    in the confidence rather than hidden inside the model's own estimate.
    """
    if blur_score >= BLUR_THRESHOLD:
        return 1.0
    return float(max(0.55, 0.55 + 0.45 * (blur_score / BLUR_THRESHOLD)))


def gaussian_confidence_floor(value: float) -> float:
    """Clamp any confidence into [0, 1] and guard against NaN."""
    if value is None or math.isnan(value) or math.isinf(value):
        return 0.0
    return float(min(1.0, max(0.0, value)))
