"""Build status, served rather than written down.

This router used to hold stubs for Parts 2-4 that returned 501 naming the
workstream that owned them. They have all been implemented, so the stubs are
gone and what remains is the status document itself - the interface reads it
to label sections, and it is the one place that says what is real.

It deliberately distinguishes *built* from *validated*. Part 3 produces a
confidence number for every score; whether that number predicts examiner
disagreement is an empirical question that needs reviewed answers to settle,
and claiming otherwise would be the single most misleading thing this project
could do. `GET /analytics/summary` is where that question gets answered.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/roadmap", summary="What is built, and what is proven")
def roadmap() -> dict:
    """Machine-readable build status, used by the interface to label sections."""
    return {
        "parts": [
            {
                "id": 1,
                "name": "Handwriting & OCR",
                "question": "What did the student write?",
                "status": "available",
                "endpoints": [
                    "POST /answers",
                    "POST /answers/transcribe",
                    "POST /answers/{id}/ocr",
                    "POST /documents/inspect",
                    "POST /documents/transcribe",
                    "PATCH /answers/{id}/ocr/verify",
                    "POST /answers/{id}/ocr/accuracy",
                ],
            },
            {
                "id": 2,
                "name": "Questions & Rubrics",
                "question": "What should a correct answer contain?",
                "status": "available",
                "endpoints": [
                    "POST /exams",
                    "POST /exams/seed",
                    "GET /exams/{id}",
                    "GET /exams/{id}/validate",
                    "GET /questions",
                    "GET /questions/{id}/rubric",
                    "PUT /questions/{id}/rubric",
                ],
            },
            {
                "id": 3,
                "name": "Evaluation & Confidence",
                "question": "How many marks, and how sure are we?",
                "status": "available",
                "endpoints": [
                    "POST /evaluations",
                    "GET /evaluations/{id}",
                    "GET /documents/{ref}/segmentation",
                    "POST /documents/evaluate",
                    "GET /config/confidence-weights",
                ],
            },
            {
                "id": 4,
                "name": "Examiner Review & Validation",
                "question": "Can a human verify and correct it?",
                "status": "available",
                "endpoints": [
                    "POST /reviews",
                    "GET /evaluations/{id}/reviews",
                    "GET /analytics/summary",
                ],
            },
        ],
        "measured": {
            "transcription": (
                "Character error rate is measured against transcripts of real "
                "scripts by scripts/benchmark.py, and per answer through "
                "POST /answers/{id}/ocr/accuracy."
            ),
            "marking": (
                "Machine-examiner agreement is measured from review rows by "
                "GET /analytics/summary. It needs reviewed answers to mean "
                "anything; the endpoint reports its own sample size."
            ),
        },
        "not_yet_validated": [
            "Confidence calibration. The four signals are combined with "
            "uncalibrated weights chosen by hand. Whether a 90% confidence "
            "really means a 10% chance of examiner disagreement is unmeasured "
            "until enough answers have been reviewed.",
            "Auto-accept. The top band is labelled an auto-accept *candidate* "
            "and still routes to a human, because the false-auto-accept rate "
            "has not been measured.",
        ],
    }
