"""Synthesise handwritten C-code answer pages with exact line-level ground truth.

Why this exists
---------------
Fine-tuning TrOCR on IAM would gain us nothing: TrOCR is already trained on IAM.
The distribution we actually need is missing from every public corpus - handwritten
*code*, with braces, semicolons, operators and identifiers, written on ruled paper
and photographed with a phone.

So we generate it. TrOCR itself was pre-trained on 17M synthetic lines; synthetic
pre-training followed by a small real fine-tune is the standard recipe when the
target domain has no dataset. These pages are not a substitute for the real
handwriting being collected - they are what lets the model learn the *symbols*
before it ever sees a real script.

What one page contains
----------------------
Ruled paper, a margin rule, handwriting in blue or black ink, and - optionally -
every degradation a real phone photo brings: rotation, uneven lighting, blur,
sensor noise, and mirror-image show-through from the back of the sheet.

Each page is written out with a JSON sidecar giving the exact text and bounding box
of every line, so it can be used three ways:

  * as recogniser training data (crop each line, pair it with its text),
  * as a segmentation test set (did we find the lines where they actually are?),
  * as an end-to-end CER/WER test set for code, which we have never had.

Usage
-----
    python scripts/generate_code_dataset.py --pages 200 --out data/synthetic
    python scripts/generate_code_dataset.py --pages 8 --styles clean,poor --seed 1
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]

# A spread of hands. Each renders the same text differently, which is the point:
# the model must learn the token, not one person's letterforms.
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\Inkfree.ttf",
    r"C:\Windows\Fonts\segoepr.ttf",
    r"C:\Windows\Fonts\segoesc.ttf",
    r"C:\Windows\Fonts\comic.ttf",
    r"C:\Windows\Fonts\comici.ttf",
    r"C:\Windows\Fonts\LHANDW.TTF",
    r"C:\Windows\Fonts\MISTRAL.TTF",
    r"C:\Windows\Fonts\BRUSHSCI.TTF",
    r"C:\Windows\Fonts\segoeprb.ttf",
    r"C:\Windows\Fonts\comicbd.ttf",
]

# Ballpoint blues and blacks, as scanned - never pure black.
INK_COLOURS = [
    (26, 38, 78),    # standard blue ballpoint
    (18, 28, 64),    # darker blue
    (40, 52, 96),    # faded blue
    (30, 30, 34),    # black ballpoint
    (44, 44, 48),    # grey-black, low pressure
    (12, 20, 52),    # fresh blue gel
]


@dataclass
class Style:
    """How badly the page is written and photographed."""

    jitter: float          # per-character vertical wobble, px
    char_gap: float        # extra spacing randomness, px
    rotate: float          # page rotation, degrees
    blur: float            # gaussian blur radius
    noise: float           # sensor noise sigma
    contrast: float        # <1 fades the ink
    show_through: float    # 0 = none, 1 = strong bleed from the back
    shadow: float          # 0 = even light, 1 = heavy gradient
    stroke_width: int = 0  # 1 = heavy pen pressure


STYLES: dict[str, Style] = {
    "clean":  Style(jitter=1.0, char_gap=0.4, rotate=0.3, blur=0.0, noise=3,
                    contrast=1.00, show_through=0.00, shadow=0.0),
    "normal": Style(jitter=2.0, char_gap=0.8, rotate=1.0, blur=0.4, noise=7,
                    contrast=0.95, show_through=0.15, shadow=0.2),
    "messy":  Style(jitter=3.2, char_gap=1.3, rotate=2.2, blur=0.8, noise=13,
                    contrast=0.86, show_through=0.30, shadow=0.45),
    "poor":   Style(jitter=4.5, char_gap=1.8, rotate=3.8, blur=1.5, noise=20,
                    contrast=0.72, show_through=0.45, shadow=0.75),
}


# ---------------------------------------------------------------------------
# The text pool - C code and the prose that surrounds it in a real answer
# ---------------------------------------------------------------------------

CODE_BLOCKS: list[list[str]] = [
    [
        "#include <stdio.h>",
        "int main()",
        "{",
        "    int n, i, flag = 0;",
        '    scanf("%d", &n);',
        "    for (i = 2; i < n; i++) {",
        "        if (n % i == 0) {",
        "            flag = 1;",
        "            break;",
        "        }",
        "    }",
        "    if (flag == 0)",
        '        printf("Prime");',
        "    else",
        '        printf("Not Prime");',
        "    return 0;",
        "}",
    ],
    [
        "int largest(int arr[], int n)",
        "{",
        "    int i, max;",
        "    max = arr[0];",
        "    for (i = 1; i < n; i++) {",
        "        if (arr[i] > max)",
        "            max = arr[i];",
        "    }",
        "    return max;",
        "}",
    ],
    [
        "int x = 10;",
        "int *p = &x;",
        'printf("%d", *p);',
        "*p = 25;",
        'printf("%d", x);',
    ],
    [
        "int i, sum = 0;",
        "for (i = 1; i <= 5; i++) {",
        "    if (i % 2 == 0)",
        "        continue;",
        "    sum = sum + i;",
        "}",
        'printf("%d", sum);',
    ],
    [
        "while (i != n) {",
        "    total += arr[i];",
        "    i++;",
        "}",
        "do {",
        "    count--;",
        "} while (count > 0);",
    ],
    [
        "void swap(int *a, int *b)",
        "{",
        "    int temp;",
        "    temp = *a;",
        "    *a = *b;",
        "    *b = temp;",
        "}",
    ],
    [
        "struct student {",
        "    char name[20];",
        "    int roll;",
        "    float marks;",
        "};",
        "struct student s1;",
        's1.roll = 42;',
    ],
    [
        "int fact(int n)",
        "{",
        "    if (n == 0 || n == 1)",
        "        return 1;",
        "    return n * fact(n - 1);",
        "}",
    ],
]

PROSE_LINES: list[str] = [
    "A pointer is a variable that stores the address of another variable.",
    "The & operator gives the memory address of a variable.",
    "The * operator gives the value stored at that address.",
    "A while loop is entry controlled, the condition is checked first.",
    "A do-while loop is exit controlled and runs at least once.",
    "The output is 9 because continue skips the even numbers.",
    "Only the odd numbers 1, 3 and 5 are added to the sum.",
    "The variable i is not declared before it is used in the loop.",
    "Assignment is used instead of comparison, it should be ==.",
    "A semicolon is missing at the end of the statement.",
    "An array stores a fixed number of elements of the same type.",
    "The index of the first element of an array is zero.",
    "A function can return only one value in C.",
    "Arguments passed by value do not change the original variable.",
    "The break statement exits the loop immediately.",
    "The modulus operator gives the remainder after division.",
    "Recursion is when a function calls itself.",
    "The main function is the entry point of every C program.",
    "A structure groups variables of different types together.",
    "Memory is allocated at compile time for a static array.",
]

# Dense symbol drill - the characters that actually break code recognition.
SYMBOL_LINES: list[str] = [
    "int count = 0;   float avg = 12.75;   char grade = 'A';",
    "sum = a + b * (c - d) / e;   rem = x % y;",
    "if (p == q) { r = 1; } else { r = 0; }",
    "flag == 1 && count != 0 || done == 0",
    "arr[0] = 25;   arr[i] = arr[i + 1];   n--;   ++j;",
    "printf(\"%d %c %f \\n\", num, ch, avg);",
    "x <= y;   a >= b;   p != q;   !found;",
    "0 1 2 3 4 5 6 7 8 9   10 25 100 512 1024",
    "{ } ( ) [ ] ; , . \" ' * & % # < > = + - /",
]


def build_answer(rng: random.Random) -> list[str]:
    """One plausible answer: a little prose, then code, the way students write."""
    lines: list[str] = []
    shape = rng.choice(["code", "code", "mixed", "mixed", "prose", "symbols"])

    if shape == "code":
        lines += rng.choice(CODE_BLOCKS)
    elif shape == "mixed":
        lines += rng.sample(PROSE_LINES, k=rng.randint(1, 2))
        lines += rng.choice(CODE_BLOCKS)
    elif shape == "prose":
        lines += rng.sample(PROSE_LINES, k=rng.randint(3, 6))
    else:
        lines += rng.sample(SYMBOL_LINES, k=rng.randint(3, 5))
    return lines


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@dataclass
class RenderedPage:
    image: Image.Image
    lines: list[dict] = field(default_factory=list)


def _load_fonts() -> list[str]:
    available = [f for f in FONT_CANDIDATES if Path(f).exists()]
    if not available:
        raise SystemExit(
            "No handwriting fonts found. This script expects Windows fonts such as "
            "Inkfree.ttf or segoepr.ttf."
        )
    return available


def wrap_to_width(
    text_lines: list[str],
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    max_width: float,
) -> list[str]:
    """Break lines that would overrun the page, the way a writer does.

    A line running off the edge would be invisible in the image while still
    present in the ground truth - which teaches the model to hallucinate text it
    cannot see. Continuation lines keep the original indentation plus two spaces,
    which is how code is actually continued by hand.
    """
    wrapped: list[str] = []
    for line in text_lines:
        if not line.strip() or draw.textlength(line, font=font) <= max_width:
            wrapped.append(line)
            continue
        indent = " " * (len(line) - len(line.lstrip()))
        words = line.split(" ")
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width or not current:
                current = candidate
            else:
                wrapped.append(current)
                current = f"{indent}  {word}"
        if current:
            wrapped.append(current)
    return wrapped


def render_page(
    text_lines: list[str],
    style: Style,
    font_path: str,
    ink: tuple[int, int, int],
    rng: random.Random,
    width: int = 1700,
    line_height: int = 86,
    margin: int = 150,
    ruled: bool = True,
) -> RenderedPage:
    """Draw one page of handwriting and report where each line landed."""
    height = margin * 2 + line_height * max(len(text_lines), 1)
    image = Image.new("RGB", (width, height), (250, 249, 245))
    draw = ImageDraw.Draw(image)

    if ruled:
        # Printed ruling: the single biggest cause of recognition failure, so the
        # synthetic pages must have it.
        rule_colour = (205, 214, 226)
        for y in range(margin, height - margin + 1, line_height):
            draw.line([(margin // 2, y), (width - margin // 2, y)], fill=rule_colour, width=2)
        # Red margin rule, exactly as a real notebook has.
        draw.line([(margin, 0), (margin, height)], fill=(228, 180, 180), width=2)

    font_size = rng.randint(46, 56)
    font = ImageFont.truetype(font_path, font_size)

    # Wrap first, then size the page to the wrapped line count - otherwise a
    # wrapped line falls off the bottom edge instead of the right one.
    usable = width - margin - 18 - (margin // 2)
    text_lines = wrap_to_width(text_lines, draw, font, usable)
    needed = margin * 2 + line_height * max(len(text_lines), 1)
    if needed > height:
        image = Image.new("RGB", (width, needed), (250, 249, 245))
        draw = ImageDraw.Draw(image)
        height = needed
        if ruled:
            rule_colour = (205, 214, 226)
            for y in range(margin, height - margin + 1, line_height):
                draw.line([(margin // 2, y), (width - margin // 2, y)],
                          fill=rule_colour, width=2)
            draw.line([(margin, 0), (margin, height)], fill=(228, 180, 180), width=2)

    records: list[dict] = []
    for index, text in enumerate(text_lines):
        baseline = margin + index * line_height - int(line_height * 0.62)
        x = margin + 18 + rng.uniform(-5, 5)
        x_start = x
        y_min, y_max = 10**9, -10**9

        # Character by character, so each one wobbles independently. Uniformly
        # rendered text is far easier to read than real handwriting, and a model
        # trained on it learns the font rather than the letter.
        for char in text:
            dy = rng.uniform(-style.jitter, style.jitter)
            draw.text((x, baseline + dy), char, font=font, fill=ink,
                      stroke_width=style.stroke_width, stroke_fill=ink)
            advance = draw.textlength(char, font=font)
            # A space in handwriting is narrower and more variable than in type.
            if char == " ":
                advance *= rng.uniform(0.65, 0.95)
            x += advance + rng.uniform(-0.5, style.char_gap)
            y_min = min(y_min, baseline + dy)
            y_max = max(y_max, baseline + dy + font_size)

        if text.strip():
            records.append({
                "index": len(records),
                "text": text,
                # Generous box: ascenders and descenders sit outside the glyph box.
                "bbox": [int(x_start - 8), int(max(y_min - 10, 0)),
                         int(x - x_start + 16), int(y_max - y_min + 20)],
            })

    return RenderedPage(image=image, lines=records)


def degrade(
    page: RenderedPage, style: Style, rng: random.Random
) -> tuple[Image.Image, np.ndarray | None]:
    """Everything a phone camera and a sheet of paper do to the ink.

    Returns the degraded image and the affine matrix applied to it, or None if the
    page was not rotated. The caller needs that matrix: the line boxes were
    recorded against the upright page, and a box that no longer sits over its own
    ink is a mislabelled training example - worse than no example at all.
    """
    image = page.image

    if style.show_through > 0:
        # Mirror-image writing bleeding from the back of the sheet. Faint, flipped,
        # and offset - exactly what the ink-isolation stage has to reject.
        back = image.transpose(Image.FLIP_LEFT_RIGHT)
        back = back.filter(ImageFilter.GaussianBlur(1.6))
        image = Image.blend(image, back, 0.10 * style.show_through)

    matrix: np.ndarray | None = None
    if style.rotate:
        angle = rng.uniform(-style.rotate, style.rotate)
        # cv2 rather than PIL, so the identical matrix can be applied to the boxes.
        array = np.asarray(image)
        h, w = array.shape[:2]
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        rotated = cv2.warpAffine(array, matrix, (w, h), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=(250, 249, 245))
        image = Image.fromarray(rotated)

    if style.blur:
        image = image.filter(ImageFilter.GaussianBlur(style.blur))

    array = np.asarray(image).astype(np.float32)

    if style.shadow > 0:
        # A soft gradient across the page: one corner lit, the opposite corner dark.
        h, w = array.shape[:2]
        gx, gy = np.meshgrid(np.linspace(0, 1, w), np.linspace(0, 1, h))
        angle = rng.uniform(0, 2 * np.pi)
        ramp = gx * np.cos(angle) + gy * np.sin(angle)
        ramp = (ramp - ramp.min()) / max(np.ptp(ramp), 1e-6)
        shading = 1.0 - style.shadow * 0.35 * ramp
        array *= shading[..., None]

    if style.contrast != 1.0:
        mean = array.mean()
        array = (array - mean) * style.contrast + mean

    if style.noise:
        array += np.random.default_rng(rng.randint(0, 2**31)).normal(
            0, style.noise, array.shape)

    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8)), matrix


def move_boxes(lines: list[dict], matrix: np.ndarray | None,
               size: tuple[int, int]) -> list[dict]:
    """Carry the line boxes through the same rotation the page received."""
    if matrix is None:
        return lines
    width, height = size
    moved: list[dict] = []
    for line in lines:
        x, y, w, h = line["bbox"]
        corners = np.array([[x, y], [x + w, y], [x, y + h], [x + w, y + h]],
                           dtype=np.float64)
        shifted = corners @ matrix[:, :2].T + matrix[:, 2]
        x0, y0 = shifted.min(axis=0)
        x1, y1 = shifted.max(axis=0)
        x0, y0 = max(int(x0), 0), max(int(y0), 0)
        x1, y1 = min(int(x1), width), min(int(y1), height)
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        moved.append({**line, "bbox": [x0, y0, x1 - x0, y1 - y0]})
    return moved


# ---------------------------------------------------------------------------
# Dataset assembly
# ---------------------------------------------------------------------------


def generate(
    pages: int,
    out_dir: Path,
    styles: list[str],
    seed: int = 0,
    ruled_fraction: float = 0.8,
) -> dict:
    rng = random.Random(seed)
    fonts = _load_fonts()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pages").mkdir(exist_ok=True)

    index: list[dict] = []
    per_style: dict[str, int] = {}
    total_lines = 0

    for page_no in range(1, pages + 1):
        style_name = styles[(page_no - 1) % len(styles)]
        style = STYLES[style_name]
        font_path = fonts[rng.randrange(len(fonts))]
        ink = INK_COLOURS[rng.randrange(len(INK_COLOURS))]

        text_lines: list[str] = []
        previous: list[str] | None = None
        target = rng.randint(8, 16)
        while len(text_lines) < target:
            answer = build_answer(rng)
            for _ in range(4):           # resample rather than repeat an answer
                if answer != previous:
                    break
                answer = build_answer(rng)
            previous = answer
            text_lines += answer
            text_lines.append("")  # blank line between answers, as instructed
        text_lines = text_lines[:18]

        page = render_page(text_lines, style, font_path, ink, rng,
                           ruled=rng.random() < ruled_fraction)
        final, matrix = degrade(page, style, rng)
        page.lines = move_boxes(page.lines, matrix, final.size)

        name = f"page_{page_no:04d}"
        final.save(out_dir / "pages" / f"{name}.png")
        record = {
            "page": name,
            "image": f"pages/{name}.png",
            "style": style_name,
            "font": Path(font_path).name,
            "ink": list(ink),
            "lines": page.lines,
        }
        (out_dir / "pages" / f"{name}.json").write_text(
            json.dumps(record, indent=1), encoding="utf-8")
        index.append(record)
        per_style[style_name] = per_style.get(style_name, 0) + 1
        total_lines += len(page.lines)

    manifest = {
        "pages": len(index),
        "lines": total_lines,
        "per_style": per_style,
        "fonts": [Path(f).name for f in fonts],
        "seed": seed,
        "note": "Synthetic handwritten C code. Ground truth is exact: the text was "
                "rendered, not transcribed.",
        "index": index,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=100)
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "synthetic"))
    parser.add_argument("--styles", default="clean,normal,messy,poor")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--ruled-fraction", type=float, default=0.8,
                        help="share of pages drawn on ruled paper")
    args = parser.parse_args()

    styles = [s.strip() for s in args.styles.split(",") if s.strip() in STYLES]
    if not styles:
        raise SystemExit(f"No valid styles. Choose from: {', '.join(STYLES)}")

    out_dir = Path(args.out)
    manifest = generate(args.pages, out_dir, styles, seed=args.seed,
                        ruled_fraction=args.ruled_fraction)
    print(f"{manifest['pages']} pages, {manifest['lines']} labelled lines -> {out_dir}")
    print(f"  styles: {manifest['per_style']}")
    print(f"  fonts:  {len(manifest['fonts'])} different hands")


if __name__ == "__main__":
    main()
