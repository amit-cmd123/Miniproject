"""Generate synthetic handwritten answer sheets for development and testing.

Real handwriting samples are what the project will actually be measured on -
this script is not a substitute for collecting them. It exists so that the
pipeline can be exercised end to end before the dataset arrives, and so that
tests have a reproducible input with a known ground-truth transcription.

Usage:
    python scripts/generate_sample_answer.py                    # default sample
    python scripts/generate_sample_answer.py --style messy      # harder case
    python scripts/generate_sample_answer.py --list-styles
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "samples"

HANDWRITING_FONTS = [
    r"C:\Windows\Fonts\Inkfree.ttf",
    r"C:\Windows\Fonts\segoepr.ttf",
    r"C:\Windows\Fonts\comic.ttf",
    r"C:\Windows\Fonts\LHANDW.TTF",
]

ANSWER_TEXT = [
    "Polymorphism means one interface can take many forms.",
    "In object oriented programming a reference of a base class",
    "can point to objects of different derived classes.",
    "There are two types: compile time polymorphism which is",
    "achieved using method overloading, and run time",
    "polymorphism which is achieved using method overriding.",
    "For example a Shape class declares a draw() method and",
    "Circle and Square override it with their own version.",
    "The correct method is chosen based on the actual object.",
    "This makes the program easier to extend and maintain.",
]

STYLES = {
    "clean": dict(jitter=1.0, rotate=0.4, blur=0.0, noise=3, contrast=1.0),
    "normal": dict(jitter=2.0, rotate=1.2, blur=0.4, noise=7, contrast=0.95),
    "messy": dict(jitter=3.5, rotate=2.8, blur=0.9, noise=14, contrast=0.82),
    "poor": dict(jitter=5.0, rotate=4.5, blur=1.6, noise=22, contrast=0.68),
}


def _pick_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in HANDWRITING_FONTS:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def generate(style: str = "normal", seed: int = 7, lines: list[str] | None = None) -> Path:
    config = STYLES[style]
    rng = random.Random(seed)
    text_lines = lines or ANSWER_TEXT

    width, margin, line_height = 1700, 110, 92
    height = margin * 2 + line_height * len(text_lines)

    # Paper: a warm off-white with a faint ruled grid.
    image = Image.new("RGB", (width, height), (250, 249, 245))
    draw = ImageDraw.Draw(image)
    for y in range(margin, height - margin + 1, line_height):
        draw.line([(margin // 2, y), (width - margin // 2, y)], fill=(226, 231, 236), width=2)
    draw.line([(margin, 0), (margin, height)], fill=(236, 205, 205), width=2)

    font = _pick_font(52)
    ink = (26, 38, 78)

    for index, line in enumerate(text_lines):
        base_y = margin + index * line_height - 58
        x = margin + 16 + rng.uniform(-4, 4)
        # Draw character by character so each one wobbles independently -
        # uniform text is far easier to read than real handwriting.
        for char in line:
            dy = rng.uniform(-config["jitter"], config["jitter"])
            draw.text((x, base_y + dy), char, font=font, fill=ink)
            x += draw.textlength(char, font=font) + rng.uniform(-0.6, 1.1)

    if config["rotate"]:
        image = image.rotate(
            rng.uniform(-config["rotate"], config["rotate"]),
            resample=Image.BICUBIC,
            fillcolor=(250, 249, 245),
        )
    if config["blur"]:
        image = image.filter(ImageFilter.GaussianBlur(config["blur"]))

    array = np.asarray(image).astype(np.float32)
    if config["contrast"] != 1.0:
        mean = array.mean()
        array = (array - mean) * config["contrast"] + mean
    if config["noise"]:
        array += np.random.default_rng(seed).normal(0, config["noise"], array.shape)
    image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"sample_answer_{style}.png"
    image.save(path)

    truth = OUT_DIR / f"sample_answer_{style}.txt"
    truth.write_text("\n".join(text_lines), encoding="utf-8")

    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", default="normal", choices=sorted(STYLES))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--all", action="store_true", help="generate every style")
    parser.add_argument("--list-styles", action="store_true")
    args = parser.parse_args()

    if args.list_styles:
        for name, config in STYLES.items():
            print(f"{name:8} {config}")
        return

    styles = sorted(STYLES) if args.all else [args.style]
    for style in styles:
        path = generate(style=style, seed=args.seed)
        print(f"{style:8} -> {path}")


if __name__ == "__main__":
    main()
