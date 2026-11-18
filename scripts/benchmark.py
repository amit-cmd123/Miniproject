"""Measure the recognition pipeline against a dataset with known ground truth.

Every change to preprocessing or to the recogniser has to be justified by a number,
not by how the output looks. This is the harness that produces the number.

It reports three things, kept separate on purpose:

  * **Segmentation** - did we find the right number of lines, in the right places?
    A page can score badly here while the recogniser is blameless.
  * **Recognition** - character and word error rate on the text we did extract.
  * **Confidence** - what the system believed about its own output, so we can see
    whether low confidence actually predicts high error.

Keeping them apart is the whole point: published work on handwritten grading found
87% of marking errors came from transcription, and you can only act on that if you
know which stage failed.

Usage
-----
    python scripts/benchmark.py --dataset data/synthetic_pilot
    python scripts/benchmark.py --dataset data/synthetic --limit 50 --tag after-finetune
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import jiwer  # noqa: E402

from app.services import preprocessing as pp  # noqa: E402

# Characters that mark a line as code rather than prose. Reported separately
# because code is the harder half and an overall average hides that.
CODE_MARKERS = set(";{}[]()<>=&*%#")
CODE_KEYWORDS = {"int", "char", "float", "void", "return", "printf", "scanf",
                 "for", "while", "if", "else", "include", "struct", "break"}

NORMALISE = jiwer.Compose([
    jiwer.ToLowerCase(),
    jiwer.RemoveMultipleSpaces(),
    jiwer.Strip(),
])


def is_code(line: str) -> bool:
    if any(c in CODE_MARKERS for c in line):
        return True
    return any(word in CODE_KEYWORDS for word in line.replace("(", " ").split())


def rates(reference: str, hypothesis: str) -> tuple[float, float]:
    ref, hyp = NORMALISE(reference), NORMALISE(hypothesis)
    if not ref.strip():
        return (0.0, 0.0) if not hyp.strip() else (1.0, 1.0)
    return float(jiwer.cer(ref, hyp)), float(jiwer.wer(ref, hyp))


@dataclass
class Bucket:
    """Running totals for one slice of the dataset."""

    pages: int = 0
    true_lines: int = 0
    found_lines: int = 0
    cer: list[float] = field(default_factory=list)
    wer: list[float] = field(default_factory=list)
    confidence: list[float] = field(default_factory=list)
    seconds: list[float] = field(default_factory=list)

    def mean(self, values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def summary(self) -> dict:
        return {
            "pages": self.pages,
            "true_lines": self.true_lines,
            "found_lines": self.found_lines,
            "line_recall": round(self.found_lines / self.true_lines, 4) if self.true_lines else 0.0,
            "cer": round(self.mean(self.cer), 4),
            "wer": round(self.mean(self.wer), 4),
            "confidence": round(self.mean(self.confidence), 4),
            "seconds_per_page": round(self.mean(self.seconds), 2),
        }


def load_entries(dataset: Path) -> list[dict]:
    """Index either a generated dataset or a folder of real scanned pages.

    A synthetic dataset carries a manifest with the exact box of every line. A
    folder of real scans has no boxes - only an image and a transcript - so the
    line entries hold text alone. Everything downstream uses the text, and the
    line *count* as the segmentation target, so both shapes work.
    """
    manifest = dataset / "manifest.json"
    if manifest.exists():
        return json.loads(manifest.read_text(encoding="utf-8"))["index"]

    entries: list[dict] = []
    for image in sorted(dataset.glob("*.png")) + sorted(dataset.glob("*.jpg")):
        transcript = image.with_suffix(".txt")
        if not transcript.exists():
            print(f"  (no transcript for {image.name}, skipped)")
            continue
        text_lines = [t.strip() for t
                      in transcript.read_text(encoding="utf-8").splitlines() if t.strip()]
        entries.append({
            "page": image.stem,
            "image": image.name,
            "style": "real",
            "lines": [{"index": i, "text": t} for i, t in enumerate(text_lines)],
        })
    if not entries:
        raise SystemExit(f"{dataset} has neither manifest.json nor image/.txt pairs.")
    return entries


def run(dataset: Path, provider_name: str, limit: int | None, tag: str) -> dict:
    from app.core.config import settings
    from app.providers.ocr.registry import get_ocr_provider, reset_provider_cache

    settings.ocr_provider = provider_name
    reset_provider_cache()
    provider = get_ocr_provider()

    started = time.perf_counter()
    provider.warmup()
    warmup_seconds = time.perf_counter() - started

    entries = load_entries(dataset)
    if limit:
        entries = entries[:limit]

    overall = Bucket()
    by_style: dict[str, Bucket] = {}
    by_kind: dict[str, Bucket] = {"code": Bucket(), "prose": Bucket()}
    worst: list[tuple[float, str, str, str]] = []

    for entry in entries:
        truth_lines = [line["text"] for line in entry["lines"]]
        reference = "\n".join(truth_lines)
        kind = "code" if sum(map(is_code, truth_lines)) * 2 >= len(truth_lines) else "prose"

        page_started = time.perf_counter()
        image = pp.load_image(dataset / entry["image"])
        clean, boxes, report = pp.preprocess(image, max_lines=settings.ocr_max_lines)
        boxes = [b for b in boxes if pp.line_ink_fraction(clean, b) >= 0.004]

        if provider.reads_full_page:
            result = provider.recognise_page(image, [pp.crop_line(clean, b) for b in boxes], boxes)
        else:
            result = provider.recognise([pp.crop_line(clean, b) for b in boxes], boxes)
        elapsed = time.perf_counter() - page_started

        cer, wer = rates(reference, result.text)
        confidences = [line.confidence for line in result.lines]
        mean_conf = sum(confidences) / len(confidences) if confidences else 0.0

        for bucket in (overall, by_style.setdefault(entry["style"], Bucket()), by_kind[kind]):
            bucket.pages += 1
            bucket.true_lines += len(truth_lines)
            bucket.found_lines += len(result.lines)
            bucket.cer.append(cer)
            bucket.wer.append(wer)
            bucket.confidence.append(mean_conf)
            bucket.seconds.append(elapsed)

        worst.append((cer, entry["page"], reference, result.text))
        print(f"  {entry['page']}  {entry['style']:<7} {kind:<5} "
              f"lines {len(result.lines):>2}/{len(truth_lines):<2}  "
              f"CER {cer:6.1%}  WER {wer:6.1%}  conf {mean_conf:5.1%}  {elapsed:5.1f}s",
              flush=True)

    worst.sort(reverse=True)
    report_data = {
        "tag": tag,
        "dataset": str(dataset),
        "provider": provider_name,
        "model": provider.info().model_name,
        "warmup_seconds": round(warmup_seconds, 1),
        "overall": overall.summary(),
        "by_style": {k: v.summary() for k, v in sorted(by_style.items())},
        "by_kind": {k: v.summary() for k, v in by_kind.items() if v.pages},
        "worst_pages": [
            {"page": name, "cer": round(cer, 4),
             "reference": ref[:400], "hypothesis": hyp[:400]}
            for cer, name, ref, hyp in worst[:3]
        ],
    }

    reports = REPO_ROOT / "data" / "benchmarks"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = reports / f"{stamp}_{tag}.json"
    path.write_text(json.dumps(report_data, indent=1), encoding="utf-8")
    report_data["_path"] = str(path)
    return report_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(REPO_ROOT / "data" / "synthetic_pilot"))
    parser.add_argument("--provider", default="trocr", choices=["trocr", "gemini", "mock"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--tag", default="baseline")
    args = parser.parse_args()

    dataset = Path(args.dataset)
    if not dataset.exists():
        raise SystemExit(f"No such dataset directory: {dataset}")

    print(f"Benchmarking {dataset.name} with {args.provider} ...")
    data = run(dataset, args.provider, args.limit, args.tag)

    o = data["overall"]
    print(f"\n{'='*66}")
    print(f"OVERALL   CER {o['cer']:.1%}   WER {o['wer']:.1%}   "
          f"line recall {o['line_recall']:.1%}   {o['seconds_per_page']}s/page")
    print(f"{'='*66}")
    print(f"{'slice':<12}{'pages':>6}{'CER':>9}{'WER':>9}{'lines':>9}{'conf':>8}{'s/page':>8}")
    for name, bucket in list(data["by_kind"].items()) + list(data["by_style"].items()):
        print(f"{name:<12}{bucket['pages']:>6}{bucket['cer']:>9.1%}{bucket['wer']:>9.1%}"
              f"{bucket['line_recall']:>9.1%}{bucket['confidence']:>8.1%}"
              f"{bucket['seconds_per_page']:>8.1f}")
    print(f"\nreport: {data['_path']}")


if __name__ == "__main__":
    main()
