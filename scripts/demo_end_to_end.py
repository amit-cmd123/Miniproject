"""Run the whole pipeline on one real answer booklet, and print what happened.

This is the script to run before a demo, and the one to run when something is
broken, because it exercises every part in the order they depend on each other:

    PDF -> transcription -> per-question split -> rubric marking
        -> composite confidence -> review routing -> validation metrics

It talks to the application through its own API, in-process, so it proves the
HTTP contracts work and not merely that the services do. Nothing is mocked:
with EVALNOVA_OCR_PROVIDER=gemini it sends real pages to Google and marks real
text against the real rubric.

Usage
-----
    .venv\\Scripts\\python scripts\\demo_end_to_end.py
    .venv\\Scripts\\python scripts\\demo_end_to_end.py data\\exam\\scans\\writer_2.pdf
    .venv\\Scripts\\python scripts\\demo_end_to_end.py --pages 1-2 --samples 1

`--samples 1` halves the cost and time by taking one reading per answer
instead of two, at the price of the agreement signal, which is then reported
as unmeasured rather than assumed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

RULE = "=" * 78


def heading(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pdf",
        nargs="?",
        default=str(REPO_ROOT / "data" / "exam" / "scans" / "writer_1.pdf"),
        help="a scanned answer booklet",
    )
    parser.add_argument("--pages", default=None, help="e.g. 1-2. Blank reads all.")
    parser.add_argument(
        "--samples",
        type=int,
        default=None,
        help="independent readings per answer (default: the configured value)",
    )
    parser.add_argument(
        "--booklet-ref", default=None, help="anonymous booklet label, e.g. BK-014"
    )
    args = parser.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        raise SystemExit(f"No such booklet: {pdf}")

    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.db.session import init_db
    from app.main import app

    init_db()
    client = TestClient(app)

    heading("CONFIGURATION")
    ocr = client.get("/api/v1/ocr/provider").json()
    marker = client.get("/api/v1/evaluations/provider").json()
    print(f"  transcription : {ocr['name']} / {ocr['model_name']} ({ocr['device']})")
    print(f"  marking       : {marker['name']} / {marker['model_name']}")
    print(f"  readings      : {args.samples or settings.evaluation_samples} per answer")
    if marker["is_mock"]:
        print(
            "\n  NOTE: the keyword baseline is marking, not a language model.\n"
            "  Set EVALNOVA_EVALUATION_PROVIDER=gemini in .env for real marking."
        )

    # ---- Part 2: the standard to mark against --------------------------
    heading("PART 2 - RUBRICS")
    exam = client.post("/api/v1/exams/seed").json()
    report = client.get(f"/api/v1/exams/{exam['id']}/validate").json()
    print(f"  {exam['title']}")
    print(
        f"  {report['questions_checked']} questions, "
        f"{report['criteria_checked']} criteria, {report['total_marks']} marks"
    )
    print(f"  rubrics valid : {report['is_valid']}")
    for problem in report["problems"]:
        print(f"    [{problem['severity']}] {problem['question']}: {problem['message']}")
    if not report["is_valid"]:
        print("\n  Marking is blocked until the rubric errors above are fixed.")
        return 1

    # ---- Part 1: read the handwriting ----------------------------------
    heading(f"PART 1 - TRANSCRIPTION of {pdf.name}")
    started = time.perf_counter()
    with pdf.open("rb") as handle:
        form = {"file": (pdf.name, handle, "application/pdf")}
        data = {"booklet_ref": args.booklet_ref} if args.booklet_ref else {}
        if args.pages:
            data["pages"] = args.pages
        response = client.post("/api/v1/documents/transcribe", files=form, data=data)

    if response.status_code != 201:
        print(f"  FAILED ({response.status_code}): {response.text[:500]}")
        return 1

    document = response.json()
    print(
        f"  {document['pages_processed']} of {document['total_pages']} pages read "
        f"in {document['duration_ms'] / 1000:.1f}s"
    )
    print(
        f"  {document['total_lines']} lines, {document['total_words']} words, "
        f"confidence {document['overall_confidence']:.1%} "
        f"({document['band_label']})"
    )
    for page in document["pages"]:
        if page["ocr"]:
            print(
                f"    page {page['page_number']}: "
                f"{page['ocr']['line_count']:>3} lines  "
                f"conf {page['ocr']['confidence']:.1%}"
            )
        else:
            print(f"    page {page['page_number']}: FAILED - {page['error']}")
    for warning in document["warnings"]:
        print(f"    ! {warning}")

    document_ref = document["document_ref"]

    # ---- Part 3a: which text answers which question --------------------
    heading("PART 3a - SPLITTING THE BOOKLET BY QUESTION")
    split = client.get(f"/api/v1/documents/{document_ref}/segmentation").json()
    for segment in split["segments"]:
        if segment["found"]:
            preview = segment["text"].replace("\n", " / ")[:68]
            print(
                f"  {segment['question_number']:>3}  "
                f"pages {str(segment['page_numbers']):<10} "
                f"by {segment['located_by']:<7} "
                f"conf {segment['transcription_confidence']:.0%}  {preview}"
            )
        else:
            print(f"  {segment['question_number']:>3}  not found in this booklet")
    for warning in split["warnings"]:
        print(f"    ! {warning}")

    # ---- Part 3b: mark it ----------------------------------------------
    heading("PART 3b - MARKING AGAINST THE RUBRIC")
    payload = {"document_ref": document_ref, "exam_id": exam["id"]}
    if args.samples:
        payload["samples"] = args.samples
    if args.booklet_ref:
        payload["booklet_ref"] = args.booklet_ref

    response = client.post("/api/v1/documents/evaluate", json=payload)
    if response.status_code != 201:
        print(f"  FAILED ({response.status_code}): {response.text[:800]}")
        return 1
    result = response.json()

    for evaluation in result["evaluations"]:
        print(
            f"\n  {evaluation['question_number']}  "
            f"{evaluation['score']:g}/{evaluation['max_score']:g}  "
            f"confidence {evaluation['confidence']:.1%}  "
            f"[{evaluation['band_label']}]"
        )
        for criterion in evaluation["criteria"]:
            flag = "" if criterion["evidence_found"] else "  <- quote not in the page"
            print(
                f"      {criterion['position']}. "
                f"{criterion['awarded_marks']:g}/{criterion['max_marks']:g}  "
                f"{criterion['verdict']:<20} {criterion['description'][:46]}{flag}"
            )
        signals = evaluation["confidence_signals"].get("signals", {})
        if signals:
            print(
                "      signals: "
                + "  ".join(f"{k} {v:.0%}" for k, v in sorted(signals.items()))
            )
        for warning in evaluation["warnings"]:
            print(f"      ! {warning}")

    heading("RESULT")
    print(
        f"  TOTAL {result['total_score']:g} / {result['total_max']:g}  "
        f"({result['percentage']:.1f}%)"
    )
    print(
        f"  marked {result['questions_marked']} of {result['questions_total']} "
        f"questions in {result['duration_ms'] / 1000:.1f}s"
    )
    print(
        f"  overall marking confidence {result['overall_confidence']:.1%} "
        f"({result['band_label']})"
    )
    if result["needs_review"]:
        print(f"  needs examiner review: {', '.join(result['needs_review'])}")
    for warning in result["warnings"]:
        print(f"    ! {warning}")

    # ---- Part 4: the routing decision and the metrics ------------------
    heading("PART 4 - REVIEW ROUTING")
    queue = client.get("/api/v1/evaluations?unreviewed=true").json()
    print(f"  {len(queue)} marked answer(s) awaiting an examiner, least confident first:")
    for evaluation in sorted(queue, key=lambda e: e["confidence"])[:10]:
        print(
            f"    {evaluation['question_number'] or '-':>3}  "
            f"{evaluation['score']:g}/{evaluation['max_score']:g}  "
            f"conf {evaluation['confidence']:.1%}  {evaluation['band_label']}"
        )

    metrics = client.get("/api/v1/analytics/summary").json()
    print(
        f"\n  uploaded {metrics['answers_uploaded']} · "
        f"transcribed {metrics['answers_transcribed']} · "
        f"marked {metrics['evaluations']} · reviewed {metrics['reviewed_evaluations']}"
    )
    if metrics["note"]:
        print(f"  note: {metrics['note']}")

    print(
        f"\nWhole pipeline: {time.perf_counter() - started:.1f}s "
        f"for {document['pages_processed']} page(s).\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
