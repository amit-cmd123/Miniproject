"""Question bank and rubric endpoints - Part 2's public surface."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT
from app.db.models import Exam, Question, Rubric
from app.db.session import get_db
from app.schemas.rubrics import (
    CriterionOut,
    ExamDetailOut,
    ExamIn,
    ExamOut,
    QuestionOut,
    RubricIn,
    RubricOut,
    RubricValidationOut,
)
from app.services import rubric_service
from app.services.rubric_service import RubricError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["questions & rubrics"])

# The exam shipped with the project: a 30-mark C programming paper with a
# rubric per question. Seeding it is how a demo gets something to mark.
SEED_PATH = REPO_ROOT / "data" / "exam" / "seed_exam.json"


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _rubric_out(rubric: Rubric) -> RubricOut:
    load_bearing = rubric_service.load_bearing_positions(rubric)
    return RubricOut(
        id=rubric.id,
        question_id=rubric.question_id,
        version=rubric.version,
        is_active=rubric.is_active,
        marking_scheme=rubric.marking_scheme,
        scoring_rules=rubric.scoring_rules or {},
        criteria=[
            CriterionOut(
                id=criterion.id,
                position=criterion.position,
                description=criterion.description,
                max_marks=criterion.max_marks,
                essential_concepts=list(criterion.essential_concepts or []),
                acceptable_alternatives=list(criterion.acceptable_alternatives or []),
                common_mistakes=list(criterion.common_mistakes or []),
                allows_partial=criterion.allows_partial,
                load_bearing=criterion.position in load_bearing,
            )
            for criterion in sorted(rubric.criteria, key=lambda c: c.position)
        ],
        total_criterion_marks=rubric_service.total_criterion_marks(rubric),
        created_at=rubric.created_at,
    )


def _question_out(db: Session, question: Question, *, with_rubric: bool = True) -> QuestionOut:
    rubric = rubric_service.active_rubric(db, question.id)
    key = rubric_service.active_answer_key(db, question.id)
    return QuestionOut(
        id=question.id,
        exam_id=question.exam_id,
        number=question.number,
        text=question.text,
        topic=question.topic,
        question_type=question.question_type,
        max_marks=question.max_marks,
        answer_key=key.reference_answer if key else None,
        has_rubric=rubric is not None,
        rubric=_rubric_out(rubric) if (rubric and with_rubric) else None,
        created_at=question.created_at,
    )


def _exam_out(db: Session, exam: Exam) -> ExamOut:
    questions = rubric_service.questions_for(db, exam.id)
    return ExamOut(
        id=exam.id,
        title=exam.title,
        subject=exam.subject,
        subject_code=exam.subject_code,
        term=exam.term,
        question_count=len(questions),
        total_marks=round(sum(q.max_marks for q in questions), 4),
        created_at=exam.created_at,
    )


def _get_exam(db: Session, exam_id: str) -> Exam:
    exam = rubric_service.get_exam(db, exam_id)
    if exam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No exam with that id.")
    return exam


def _get_question(db: Session, question_id: str) -> Question:
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No question with that id.")
    return question


# ---------------------------------------------------------------------------
# Exams
# ---------------------------------------------------------------------------


@router.get("/exams", response_model=list[ExamOut])
def list_exams(db: Session = Depends(get_db)) -> list[ExamOut]:
    return [_exam_out(db, exam) for exam in rubric_service.list_exams(db)]


@router.post("/exams", response_model=ExamDetailOut, status_code=status.HTTP_201_CREATED)
def create_exam(payload: ExamIn, db: Session = Depends(get_db)) -> ExamDetailOut:
    """Define a paper, its answer keys and its rubrics in one request."""
    exam = rubric_service.create_exam(db, payload)
    return ExamDetailOut(
        **_exam_out(db, exam).model_dump(),
        questions=[
            _question_out(db, question)
            for question in rubric_service.questions_for(db, exam.id)
        ],
    )


@router.post("/exams/seed", response_model=ExamDetailOut)
def seed_exam(
    replace: bool = Query(
        default=False,
        description="Delete and rewrite the exam if it already exists. Answers "
        "and evaluations are not touched.",
    ),
    db: Session = Depends(get_db),
) -> ExamDetailOut:
    """Load the bundled 30-mark C programming paper from disk.

    Idempotent: seeding twice returns the exam already loaded rather than
    creating a second copy, so it is safe to call on every startup.
    """
    try:
        exam = rubric_service.seed_from_file(db, SEED_PATH, replace=replace)
    except RubricError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return ExamDetailOut(
        **_exam_out(db, exam).model_dump(),
        questions=[
            _question_out(db, question)
            for question in rubric_service.questions_for(db, exam.id)
        ],
    )


@router.get("/exams/{exam_id}", response_model=ExamDetailOut)
def get_exam(exam_id: str, db: Session = Depends(get_db)) -> ExamDetailOut:
    exam = _get_exam(db, exam_id)
    return ExamDetailOut(
        **_exam_out(db, exam).model_dump(),
        questions=[
            _question_out(db, question)
            for question in rubric_service.questions_for(db, exam.id)
        ],
    )


@router.get("/exams/{exam_id}/validate", response_model=RubricValidationOut)
def validate_exam(exam_id: str, db: Session = Depends(get_db)) -> RubricValidationOut:
    """Is every rubric in this paper fit to mark with?

    Run before a marking session. A rubric whose criteria do not sum to the
    question's marks produces scores that look entirely reasonable and are
    wrong for every student, so this check is a precondition of marking rather
    than a diagnostic.
    """
    return rubric_service.validate_exam(db, _get_exam(db, exam_id))


# ---------------------------------------------------------------------------
# Questions and rubrics
# ---------------------------------------------------------------------------


@router.get("/questions", response_model=list[QuestionOut])
def list_questions(
    exam_id: str | None = Query(default=None),
    include_rubric: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[QuestionOut]:
    if exam_id:
        questions = rubric_service.questions_for(db, _get_exam(db, exam_id).id)
    else:
        questions = []
        for exam in rubric_service.list_exams(db):
            questions.extend(rubric_service.questions_for(db, exam.id))
    return [_question_out(db, q, with_rubric=include_rubric) for q in questions]


@router.get("/questions/{question_id}", response_model=QuestionOut)
def get_question(question_id: str, db: Session = Depends(get_db)) -> QuestionOut:
    return _question_out(db, _get_question(db, question_id))


@router.get("/questions/{question_id}/rubric", response_model=RubricOut)
def get_rubric(question_id: str, db: Session = Depends(get_db)) -> RubricOut:
    question = _get_question(db, question_id)
    rubric = rubric_service.active_rubric(db, question.id)
    if rubric is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This question has no active rubric, so it cannot be marked yet.",
        )
    return _rubric_out(rubric)


@router.put("/questions/{question_id}/rubric", response_model=RubricOut)
def replace_rubric(
    question_id: str, payload: RubricIn, db: Session = Depends(get_db)
) -> RubricOut:
    """Write a new rubric version. The previous one is kept, deactivated.

    Existing evaluations keep citing the version they were marked with, which
    is what lets a past score still be explained after the rubric changes.
    """
    question = _get_question(db, question_id)

    total = round(sum(c.max_marks for c in payload.criteria), 4)
    if abs(total - question.max_marks) > rubric_service.MARK_TOLERANCE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"The criteria sum to {total:g} but the question is worth "
            f"{question.max_marks:g}. Adjust the criteria so they match, or "
            f"change the question's marks.",
        )

    positions = [c.position for c in payload.criteria]
    if len(set(positions)) != len(positions):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Two criteria share the same position."
        )

    return _rubric_out(rubric_service.replace_rubric(db, question, payload))
