"""Planned endpoints for Parts 2, 3 and 4.

These are deliberately registered and deliberately unimplemented. They return
501 with a message naming the workstream that owns them, which means:

  * the contract is visible in the API documentation from day one,
  * the frontend can wire real calls now and get an honest failure,
  * and no member has to guess at another member's route names.

Each becomes a real router as its phase lands.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["planned"])

PLANNED = {
    "questions": ("Part 2", "Question bank and answer keys"),
    "rubrics": ("Part 2", "Marking schemes and criterion definitions"),
    "evaluations": ("Part 3", "Rubric-driven marking with composite confidence"),
    "reviews": ("Part 4", "Examiner accept/modify and final score"),
    "analytics": ("Part 4", "Agreement, calibration and workflow metrics"),
}


def _not_yet(area: str):
    part, description = PLANNED[area]
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "area": area,
            "workstream": part,
            "description": description,
            "message": f"{description} is {part} of the plan and is not built yet.",
        },
    )


@router.get("/questions", summary="[Part 2 - planned] List questions")
def list_questions():
    _not_yet("questions")


@router.get("/questions/{question_id}/rubric", summary="[Part 2 - planned] Get rubric")
def get_rubric(question_id: str):
    _not_yet("rubrics")


@router.post("/evaluations", summary="[Part 3 - planned] Evaluate an answer")
def create_evaluation():
    _not_yet("evaluations")


@router.post("/reviews", summary="[Part 4 - planned] Accept or modify a score")
def create_review():
    _not_yet("reviews")


@router.get("/analytics/summary", summary="[Part 4 - planned] Validation metrics")
def analytics_summary():
    _not_yet("analytics")


@router.get("/roadmap", summary="What is built and what is next")
def roadmap():
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
                    "PATCH /answers/{id}/ocr/verify",
                    "POST /answers/{id}/ocr/accuracy",
                ],
            },
            {
                "id": 2,
                "name": "Questions & Rubrics",
                "question": "What should a correct answer contain?",
                "status": "planned",
                "endpoints": ["GET /questions", "GET /questions/{id}/rubric"],
            },
            {
                "id": 3,
                "name": "Evaluation & Confidence",
                "question": "How many marks, and how sure are we?",
                "status": "planned",
                "endpoints": ["POST /evaluations"],
            },
            {
                "id": 4,
                "name": "Examiner App & Validation",
                "question": "Can a human verify and correct it?",
                "status": "planned",
                "endpoints": ["POST /reviews", "GET /analytics/summary"],
            },
        ]
    }
