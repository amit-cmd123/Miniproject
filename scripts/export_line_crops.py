"""Turn labelled pages into the line-image / text pairs a recogniser trains on.

TrOCR learns from one line at a time: an image of a single written line, and the
text it contains. This script produces exactly that, from two sources:

  * **synthetic pages** - the generator knows where every line is, so crops come
    from the recorded boxes and the text is exact;
  * **real scanned scripts** - no boxes are known, so the crops come from our own
    segmentation and are paired with the transcript the writer copied.

The two are deliberately kept as separate splits. Synthetic data teaches the
symbols; real data teaches the handwriting. Mixing them in the manifest but
tracking the source lets the training notebook weight them differently, and lets
us report how much of any gain came from real scripts.

Usage
-----
    python scripts/export_line_crops.py --dataset data/synthetic --out data/train
    python scripts/export_line_crops.py --dataset data/synthetic --out data/train --val-fraction 0.1
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services import preprocessing as pp  # noqa: E402

# TrOCR squeezes every crop to a fixed square, so an extremely wide or thin line
# arrives as a smear. Those are dropped rather than taught.
MIN_CROP_HEIGHT = 16
# Set from the command line in main(); see --max-height / --jpeg.
MAX_HEIGHT = 0
JPEG = False
MAX_ASPECT = 60.0


def shrink(crop: np.ndarray) -> np.ndarray:
    """Scale a crop down to MAX_HEIGHT, keeping its aspect ratio."""
    if not MAX_HEIGHT or crop.shape[0] <= MAX_HEIGHT:
        return crop
    scale = MAX_HEIGHT / crop.shape[0]
    return cv2.resize(crop, (max(int(crop.shape[1] * scale), 8), MAX_HEIGHT),
                      interpolation=cv2.INTER_AREA)


def save_crop(crop: np.ndarray, target: Path) -> Path:
    """Write a crop, in whichever format was asked for."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if JPEG:
        target = target.with_suffix(".jpg")
        cv2.imwrite(str(target), shrink(crop), [cv2.IMWRITE_JPEG_QUALITY, 92])
    else:
        cv2.imwrite(str(target), shrink(crop))
    return target


def tighten(crop: np.ndarray) -> np.ndarray:
    """Trim a crop to its own line of ink.

    Rotating a wide box and taking its axis-aligned bound inflates it vertically,
    so a crop can carry a sliver of the line above or below. Trained on, those
    slivers teach the model to read text that is not part of the line. This keeps
    the band of ink containing the vertical centre and drops anything separated
    from it by a clear gap.
    """
    if crop.size == 0:
        return crop
    # Ink is dark; threshold generously so faint pen survives.
    ink_rows = (crop < 190).sum(axis=1)
    if not ink_rows.any():
        return crop
    busy = ink_rows > max(ink_rows.max() * 0.08, 1)
    centre = len(busy) // 2
    if not busy[centre]:
        # Centre sits in a gap: fall back to the densest row.
        centre = int(np.argmax(ink_rows))
    top = centre
    while top > 0 and busy[top - 1]:
        top -= 1
    bottom = centre
    while bottom < len(busy) - 1 and busy[bottom + 1]:
        bottom += 1
    pad = 3
    top, bottom = max(0, top - pad), min(crop.shape[0], bottom + pad + 1)
    trimmed = crop[top:bottom]
    # Never trim away most of the line - that means the heuristic misfired.
    if trimmed.shape[0] < crop.shape[0] * 0.35:
        return crop
    return trimmed


def crop_from_box(page: np.ndarray, box: tuple[int, int, int, int],
                  pad: int = 4) -> np.ndarray | None:
    x, y, w, h = box
    height, width = page.shape[:2]
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(width, x + w + pad), min(height, y + h + pad)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = tighten(page[y0:y1, x0:x1])
    if crop.shape[0] < MIN_CROP_HEIGHT:
        return None
    if crop.shape[1] / max(crop.shape[0], 1) > MAX_ASPECT:
        return None
    return crop


def export_synthetic(dataset: Path, out: Path, rng: random.Random,
                     val_fraction: float) -> list[dict]:
    """Crops cut from the generator's own recorded boxes - exact ground truth."""
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    records: list[dict] = []

    for entry in manifest["index"]:
        image = pp.load_image(dataset / entry["image"])
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        for line in entry["lines"]:
            text = line["text"].strip()
            if not text:
                continue
            crop = crop_from_box(gray, tuple(line["bbox"]))
            if crop is None:
                continue
            split = "val" if rng.random() < val_fraction else "train"
            name = f"{entry['page']}_l{line['index']:02d}.png"
            written = save_crop(crop, out / split / "images" / name)
            records.append({
                "image": f"{split}/images/{written.name}",
                "text": text,
                "split": split,
                "source": "synthetic",
                "style": entry["style"],
                "font": entry["font"],
            })
    return records


def export_real(scans: Path, out: Path, rng: random.Random,
                val_fraction: float) -> list[dict]:
    """Crops from real scripts, segmented by our own pipeline.

    Pairing is by position: the nth line our segmentation finds is matched with
    the nth line of the transcript. That holds only when segmentation is correct,
    so a page whose line count disagrees with its transcript is skipped rather
    than silently mislabelled - a wrong pair is worse than a missing one.
    """
    records: list[dict] = []
    skipped: list[str] = []

    for pdf_or_image in sorted(scans.glob("*")):
        if pdf_or_image.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        transcript = pdf_or_image.with_suffix(".txt")
        if not transcript.exists():
            skipped.append(f"{pdf_or_image.name}: no .txt transcript")
            continue

        truth = [t.strip() for t in transcript.read_text(encoding="utf-8").splitlines()
                 if t.strip()]
        image = pp.load_image(pdf_or_image)
        clean, boxes, _ = pp.preprocess(image)
        boxes = [b for b in boxes if pp.line_ink_fraction(clean, b) >= 0.004]

        if len(boxes) != len(truth):
            skipped.append(
                f"{pdf_or_image.name}: found {len(boxes)} lines, transcript has "
                f"{len(truth)} - skipped to avoid mislabelling")
            continue

        for index, (box, text) in enumerate(zip(boxes, truth)):
            crop = crop_from_box(clean, box)
            if crop is None:
                continue
            split = "val" if rng.random() < val_fraction else "train"
            name = f"{pdf_or_image.stem}_l{index:02d}.png"
            written = save_crop(crop, out / split / "images" / name)
            records.append({
                "image": f"{split}/images/{written.name}",
                "text": text,
                "split": split,
                "source": "real",
                "writer": pdf_or_image.stem,
            })

    for note in skipped:
        print(f"  skipped {note}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(REPO_ROOT / "data" / "synthetic"),
                        help="synthetic dataset directory with a manifest.json")
    parser.add_argument("--scans", default=None,
                        help="directory of real page images, each with a matching .txt")
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "train"))
    parser.add_argument("--val-fraction", type=float, default=0.08)
    parser.add_argument("--max-height", type=int, default=0,
                        help="downscale crops taller than this (0 = keep full size). "
                             "TrOCR resizes every crop to 384x384 anyway, so storing "
                             "tall crops costs upload size and buys nothing")
    parser.add_argument("--jpeg", action="store_true",
                        help="save crops as JPEG instead of PNG - roughly 5x smaller")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    global MAX_HEIGHT, JPEG
    MAX_HEIGHT, JPEG = args.max_height, args.jpeg

    rng = random.Random(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    dataset = Path(args.dataset)
    if (dataset / "manifest.json").exists():
        print(f"Exporting synthetic crops from {dataset} ...")
        records += export_synthetic(dataset, out, rng, args.val_fraction)
    else:
        print(f"No synthetic manifest at {dataset}, skipping")

    if args.scans:
        scans = Path(args.scans)
        if scans.exists():
            print(f"Exporting real crops from {scans} ...")
            records += export_real(scans, out, rng, args.val_fraction)
        else:
            print(f"No scans directory at {scans}, skipping")

    if not records:
        raise SystemExit("Nothing exported. Generate a dataset first.")

    for split in ("train", "val"):
        rows = [r for r in records if r["split"] == split]
        path = out / f"{split}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    train = [r for r in records if r["split"] == "train"]
    val = [r for r in records if r["split"] == "val"]
    real = [r for r in records if r["source"] == "real"]
    chars = sorted({c for r in records for c in r["text"]})

    summary = {
        "total_lines": len(records),
        "train": len(train),
        "val": len(val),
        "synthetic": len(records) - len(real),
        "real": len(real),
        "distinct_characters": len(chars),
        "characters": "".join(chars),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")

    print(f"\n{len(records)} line crops -> {out}")
    print(f"  train {len(train)} | val {len(val)}")
    print(f"  synthetic {summary['synthetic']} | real {summary['real']}")
    print(f"  {summary['distinct_characters']} distinct characters")


if __name__ == "__main__":
    main()
