"""Measure both recognition engines on the real answer pages, side by side.

This is the harness behind the accuracy numbers in the project report. It runs
the production reading path - the same preprocessing, the same segmentation,
the same providers the API uses - over every page in `data/exam/pages` that
has a ground-truth transcription beside it, and reports character and word
error rate, wall-clock time and the confidence the system claimed.

It touches no database and writes no answers, so it can be run against a
machine mid-demo without leaving anything behind.

Usage
-----
    .venv\\Scripts\\python scripts\\measure_engines.py
    .venv\\Scripts\\python scripts\\measure_engines.py --engines local
    .venv\\Scripts\\python scripts\\measure_engines.py --out results.json

Why error rate and not "accuracy"
---------------------------------
Character error rate is edit distance divided by the length of the reference,
so it is the share of characters that would have to be fixed. It can exceed
100% when the output is longer than the truth - which is exactly what a
runaway decoder produces, and exactly the failure an "accuracy" percentage
would hide by clipping at zero.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import jiwer  # noqa: E402

PAGES_DIR = REPO_ROOT / "data" / "exam" / "pages"

def normalise(text: str) -> str:
    """Fold away differences neither engine should be judged on.

    Case and run-length of whitespace are not things a reader of an answer
    script cares about, and jiwer's own transform chains cannot be reused
    across cer() and wer() - cer() needs the character-splitting transform
    its default supplies. Normalising the strings here and letting both
    metrics use their defaults keeps one definition of "the same text".
    """
    return " ".join(text.lower().split())


@dataclass
class PageResult:
    page: str
    engine: str
    reference_chars: int
    hypothesis_chars: int
    cer: float
    wer: float
    seconds: float
    confidence: float
    lines_found: int
    reference_lines: int
    error: str | None = None


@dataclass
class EngineSummary:
    engine: str
    pages: int
    mean_cer: float
    median_cer: float
    best_cer: float
    worst_cer: float
    mean_wer: float
    mean_seconds: float
    total_seconds: float
    mean_confidence: float
    results: list[PageResult] = field(default_factory=list)


def pages_with_truth() -> list[tuple[Path, Path]]:
    pairs = []
    for image in sorted(PAGES_DIR.glob("*.png")):
        truth = image.with_suffix(".txt")
        if truth.exists():
            pairs.append((image, truth))
    return pairs


def page_confidence(result, boxes) -> float:
    """Length-weighted mean line confidence, as the service computes it."""
    lines = [line for line in result.lines if line.text.strip()]
    if not lines:
        return 0.0
    weights = [max(len(line.text), 1) for line in lines]
    total = sum(weights)
    return sum(l.confidence * w for l, w in zip(lines, weights)) / total


def measure(engine: str, pairs: list[tuple[Path, Path]]) -> EngineSummary:
    from app.providers.ocr.registry import get_ocr_provider_for
    from app.services.ocr_service import _read_page

    provider = get_ocr_provider_for(engine)
    print(f"\n{'=' * 78}\n{engine.upper()}  ({provider.info().model_name})\n{'=' * 78}")
    print(f"{'page':<18}{'CER':>9}{'WER':>9}{'secs':>8}{'conf':>8}{'lines':>8}")
    print("-" * 78)

    results: list[PageResult] = []
    for image, truth in pairs:
        reference = truth.read_text(encoding="utf-8").strip()
        started = time.perf_counter()
        try:
            read = _read_page(str(image), provider)
            hypothesis = read.result.text.strip()
            elapsed = time.perf_counter() - started
            confidence = page_confidence(read.result, read.boxes)
            ref_n = normalise(reference)
            hyp_n = normalise(hypothesis) or " "
            cer = jiwer.cer(ref_n, hyp_n)
            wer = jiwer.wer(ref_n, hyp_n)
            result = PageResult(
                page=image.stem,
                engine=engine,
                reference_chars=len(reference),
                hypothesis_chars=len(hypothesis),
                cer=round(float(cer), 4),
                wer=round(float(wer), 4),
                seconds=round(elapsed, 2),
                confidence=round(confidence, 4),
                lines_found=len([l for l in read.result.lines if l.text.strip()]),
                reference_lines=len([l for l in reference.splitlines() if l.strip()]),
            )
            print(
                f"{result.page:<18}{result.cer:>8.1%}{result.wer:>9.1%}"
                f"{result.seconds:>8.1f}{result.confidence:>8.3f}"
                f"{result.lines_found:>5}/{result.reference_lines:<3}"
            )
        except Exception as exc:  # a failed page is data, not a crash
            elapsed = time.perf_counter() - started
            result = PageResult(
                page=image.stem, engine=engine, reference_chars=len(reference),
                hypothesis_chars=0, cer=float("nan"), wer=float("nan"),
                seconds=round(elapsed, 2), confidence=0.0, lines_found=0,
                reference_lines=0, error=str(exc)[:200],
            )
            print(f"{result.page:<18}{'FAILED':>9}  {str(exc)[:44]}")
        results.append(result)

    ok = [r for r in results if r.error is None]
    cers = [r.cer for r in ok]
    summary = EngineSummary(
        engine=engine,
        pages=len(ok),
        mean_cer=round(statistics.mean(cers), 4) if cers else float("nan"),
        median_cer=round(statistics.median(cers), 4) if cers else float("nan"),
        best_cer=round(min(cers), 4) if cers else float("nan"),
        worst_cer=round(max(cers), 4) if cers else float("nan"),
        mean_wer=round(statistics.mean([r.wer for r in ok]), 4) if ok else float("nan"),
        mean_seconds=round(statistics.mean([r.seconds for r in ok]), 2) if ok else 0.0,
        total_seconds=round(sum(r.seconds for r in results), 2),
        mean_confidence=round(statistics.mean([r.confidence for r in ok]), 4) if ok else 0.0,
        results=results,
    )
    print("-" * 78)
    print(
        f"{'MEAN':<18}{summary.mean_cer:>8.1%}{summary.mean_wer:>9.1%}"
        f"{summary.mean_seconds:>8.1f}{summary.mean_confidence:>8.3f}"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engines",
        default="local,gemini",
        help="Comma-separated: local, gemini. Default both.",
    )
    parser.add_argument("--out", type=Path, help="Write the full results as JSON")
    args = parser.parse_args()

    pairs = pages_with_truth()
    if not pairs:
        print(f"No pages with ground truth in {PAGES_DIR}", file=sys.stderr)
        return 1

    print(f"{len(pairs)} page(s) with ground truth in {PAGES_DIR.relative_to(REPO_ROOT)}")

    summaries: list[EngineSummary] = []
    for engine in [e.strip() for e in args.engines.split(",") if e.strip()]:
        try:
            summaries.append(measure(engine, pairs))
        except Exception as exc:
            print(f"\n{engine}: could not run - {exc}", file=sys.stderr)

    if len(summaries) > 1:
        print(f"\n{'=' * 78}\nSIDE BY SIDE\n{'=' * 78}")
        print(f"{'engine':<12}{'pages':>7}{'mean CER':>11}{'median':>9}{'mean WER':>11}{'s/page':>9}{'conf':>8}")
        print("-" * 78)
        for s in summaries:
            print(
                f"{s.engine:<12}{s.pages:>7}{s.mean_cer:>10.1%}{s.median_cer:>9.1%}"
                f"{s.mean_wer:>10.1%}{s.mean_seconds:>9.1f}{s.mean_confidence:>8.3f}"
            )

    if args.out:
        args.out.write_text(
            json.dumps([asdict(s) for s in summaries], indent=2), encoding="utf-8"
        )
        print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
