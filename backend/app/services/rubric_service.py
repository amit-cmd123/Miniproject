"""Question bank and rubric management - Part 2's service layer.

Owns three jobs:

* **Loading** an exam, its answer keys and its rubrics from one JSON document,
  so a paper can be version-controlled as a file and seeded reproducibly.
* **Versioning** rubrics. Editing a rubric never mutates the old one; it writes
  a new version and deactivates the previous. Evaluations record the rubric
  version they used, so a score stays explainable after the rubric changes.
* **Validating** that a rubric is fit to mark with, before any marks depend on
  it.

Why validation is a service and not a comment: a rubric whose criteria sum to
4.5 out of 5 caps every student at 90% and produces entirely plausible-looking
scores. That failure is invisible in the output and visible here.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnswerKey, Exam, Question, Rubric, RubricCriterion
from app.schemas.rubrics import (
    ExamIn,
    QuestionIn,
    RubricIn,
    RubricProblem,
    RubricValidationOut,
)
from app.services import audit

logger = logging.getLogger(__name__)

# A rubric's criteria must sum to the question's maximum. Floating-point
# addition of values like 1.5 + 1.5 + 1.0 + 1.0 is not exact, so compare
# within a tolerance smaller than the finest mark anyone awards.
MARK_TOLERANCE = 0.001

DEFAULT_SCORING_RULES: dict = {
    "spelling_penalised": False,
    "indentation_penalised": False,
    "partial_credit": True,
    "round_to": 0.5,
}


class RubricError(ValueError):
    """The rubric or question definition is unusable. Message is user-facing."""


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def list_exams(db: Session) -> list[Exam]:
    return list(db.scalars(select(Exam).order_by(Exam.created_at.desc())))


def get_exam(db: Session, exam_id: str) -> Exam | None:
    return db.get(Exam, exam_id)


def get_exam_by_code(db: Session, subject_code: str) -> Exam | None:
    return db.scalars(
        select(Exam)
        .where(Exam.subject_code == subject_code)
        .order_by(Exam.created_at.desc())
    ).first()


def questions_for(db: Session, exam_id: str) -> list[Question]:
    """An exam's questions, in paper order rather than insertion order."""
    rows = list(db.scalars(select(Question).where(Question.exam_id == exam_id)))
    return sorted(rows, key=lambda q: _question_sort_key(q.number))


def _question_sort_key(number: str | None) -> tuple[int, str]:
    """Sort Q2 before Q10, and anything unnumbered last."""
    if not number:
        return (10_000, "")
    digits = "".join(c for c in number if c.isdigit())
    return (int(digits) if digits else 9_999, number)


def active_rubric(db: Session, question_id: str) -> Rubric | None:
    return db.scalars(
        select(Rubric)
        .where(Rubric.question_id == question_id, Rubric.is_active.is_(True))
        .order_by(Rubric.version.desc())
    ).first()


def active_answer_key(db: Session, question_id: str) -> AnswerKey | None:
    return db.scalars(
        select(AnswerKey)
        .where(AnswerKey.question_id == question_id, AnswerKey.is_active.is_(True))
        .order_by(AnswerKey.version.desc())
    ).first()


def total_criterion_marks(rubric: Rubric) -> float:
    return round(sum(c.max_marks for c in rubric.criteria), 4)


def scoring_rules_for(rubric: Rubric | None) -> dict:
    """The rubric's rules, with any unset key taking the project default."""
    rules = dict(DEFAULT_SCORING_RULES)
    if rubric and rubric.scoring_rules:
        rules.update(rubric.scoring_rules)
    return rules


def load_bearing_positions(rubric: Rubric | None) -> set[int]:
    """Criterion positions the rest of the answer hangs on.

    Stored in the rubric's JSON rules rather than as a column on
    `rubric_criteria`, so adding the concept needed no migration.
    """
    rules = scoring_rules_for(rubric)
    return {int(p) for p in rules.get("load_bearing_positions") or []}


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def create_exam(db: Session, payload: ExamIn) -> Exam:
    exam = Exam(
        title=payload.title,
        subject=payload.subject,
        subject_code=payload.subject_code,
        term=payload.term,
    )
    db.add(exam)
    db.flush()

    for question in payload.questions:
        _add_question(db, exam, question)

    db.commit()
    db.refresh(exam)
    audit.record(
        db,
        action="exam.created",
        object_type="exam",
        object_id=exam.id,
        details={"title": exam.title, "questions": len(payload.questions)},
    )
    return exam


def _add_question(db: Session, exam: Exam, payload: QuestionIn) -> Question:
    question = Question(
        exam_id=exam.id,
        number=payload.number,
        text=payload.text,
        topic=payload.topic,
        question_type=payload.question_type,
        max_marks=payload.max_marks,
    )
    db.add(question)
    db.flush()

    if payload.answer_key:
        db.add(
            AnswerKey(
                question_id=question.id,
                reference_answer=payload.answer_key,
                version=1,
                is_active=True,
            )
        )
    if payload.rubric:
        _write_rubric(db, question, payload.rubric, version=1)
    return question


def _write_rubric(
    db: Session, question: Question, payload: RubricIn, version: int
) -> Rubric:
    rules = dict(DEFAULT_SCORING_RULES)
    rules.update(payload.scoring_rules or {})

    load_bearing = sorted(c.position for c in payload.criteria if c.load_bearing)
    if load_bearing:
        rules["load_bearing_positions"] = load_bearing

    rubric = Rubric(
        question_id=question.id,
        version=version,
        is_active=True,
        marking_scheme=payload.marking_scheme,
        scoring_rules=rules,
    )
    db.add(rubric)
    db.flush()

    for criterion in payload.criteria:
        db.add(
            RubricCriterion(
                rubric_id=rubric.id,
                position=criterion.position,
                description=criterion.description,
                max_marks=criterion.max_marks,
                essential_concepts=list(criterion.essential_concepts),
                acceptable_alternatives=list(criterion.acceptable_alternatives),
                common_mistakes=list(criterion.common_mistakes),
                allows_partial=criterion.allows_partial,
            )
        )
    db.flush()
    return rubric


def replace_rubric(db: Session, question: Question, payload: RubricIn) -> Rubric:
    """Write a new rubric version and retire the previous one.

    The old rubric is kept, deactivated. Any evaluation that cited it still
    resolves, which is what makes a past score auditable.
    """
    current = active_rubric(db, question.id)
    next_version = (current.version + 1) if current else 1
    if current:
        current.is_active = False

    rubric = _write_rubric(db, question, payload, version=next_version)
    db.commit()
    db.refresh(rubric)

    audit.record(
        db,
        action="rubric.replaced",
        object_type="question",
        object_id=question.id,
        details={"version": next_version, "criteria": len(payload.criteria)},
    )
    return rubric


# ---------------------------------------------------------------------------
# Seeding from a file
# ---------------------------------------------------------------------------


def exam_from_seed(document: dict) -> ExamIn:
    """Turn a `seed_exam.json` document into the API's own input shape.

    Going through `ExamIn` rather than writing rows directly means a seed file
    is validated by exactly the same rules as an exam posted to the API.
    """
    meta = document.get("exam") or {}
    shared_rules = document.get("scoring_rules") or {}

    questions: list[QuestionIn] = []
    for entry in document.get("questions") or []:
        criteria = entry.get("criteria") or []
        rubric = (
            RubricIn(
                marking_scheme=entry.get("marking_scheme"),
                criteria=criteria,
                scoring_rules=shared_rules,
            )
            if criteria
            else None
        )
        questions.append(
            QuestionIn(
                number=entry.get("number"),
                text=entry["text"],
                topic=entry.get("topic"),
                question_type=entry.get("question_type", "theory"),
                max_marks=float(entry["max_marks"]),
                answer_key=entry.get("answer_key"),
                rubric=rubric,
            )
        )

    return ExamIn(
        title=meta.get("title") or "Untitled exam",
        subject=meta.get("subject") or "Unspecified",
        subject_code=meta.get("code"),
        term=meta.get("term"),
        questions=questions,
    )


def seed_from_file(db: Session, path: Path, *, replace: bool = False) -> Exam:
    """Load an exam definition from disk.

    Idempotent by subject code: seeding twice returns the existing exam rather
    than creating a duplicate, unless `replace` is asked for.
    """
    if not path.exists():
        raise RubricError(f"No exam definition at {path}.")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RubricError(f"{path.name} is not valid JSON: {exc}") from exc

    payload = exam_from_seed(document)

    if payload.subject_code:
        existing = get_exam_by_code(db, payload.subject_code)
        if existing and not replace:
            logger.info("Exam %s already seeded; leaving it alone", payload.subject_code)
            return existing
        if existing and replace:
            _delete_exam(db, existing)

    exam = create_exam(db, payload)

    declared = (document.get("exam") or {}).get("total_marks")
    actual = sum(q.max_marks for q in payload.questions)
    if declared is not None and abs(float(declared) - actual) > MARK_TOLERANCE:
        logger.warning(
            "%s declares %s total marks but its questions sum to %s",
            path.name,
            declared,
            actual,
        )
    return exam


def _delete_exam(db: Session, exam: Exam) -> None:
    """Remove an exam and everything defined under it.

    Only reachable through an explicit `replace`. Answers are never touched -
    they belong to Part 1 and may be cited by existing evaluations.
    """
    for question in list(db.scalars(select(Question).where(Question.exam_id == exam.id))):
        for rubric in list(
            db.scalars(select(Rubric).where(Rubric.question_id == question.id))
        ):
            for criterion in list(
                db.scalars(
                    select(RubricCriterion).where(RubricCriterion.rubric_id == rubric.id)
                )
            ):
                db.delete(criterion)
            db.delete(rubric)
        for key in list(
            db.scalars(select(AnswerKey).where(AnswerKey.question_id == question.id))
        ):
            db.delete(key)
        db.delete(question)
    db.delete(exam)
    db.flush()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_exam(db: Session, exam: Exam) -> RubricValidationOut:
    """Check every rubric in an exam before marks depend on it."""
    problems: list[RubricProblem] = []
    questions = questions_for(db, exam.id)
    criteria_count = 0

    if not questions:
        problems.append(
            RubricProblem(
                question="-",
                severity="error",
                message="This exam has no questions, so nothing can be marked.",
            )
        )

    for question in questions:
        label = question.number or question.id[:8]
        rubric = active_rubric(db, question.id)

        if rubric is None:
            problems.append(
                RubricProblem(
                    question=label,
                    severity="error",
                    message="No active rubric. Marking cannot run without one.",
                )
            )
            continue

        criteria_count += len(rubric.criteria)

        if not rubric.criteria:
            problems.append(
                RubricProblem(
                    question=label,
                    severity="error",
                    message="The rubric has no criteria.",
                )
            )
            continue

        total = total_criterion_marks(rubric)
        if abs(total - question.max_marks) > MARK_TOLERANCE:
            direction = "below" if total < question.max_marks else "above"
            problems.append(
                RubricProblem(
                    question=label,
                    severity="error",
                    message=(
                        f"Criteria sum to {total:g}, which is {direction} the "
                        f"question's {question.max_marks:g} marks. Every student "
                        f"would be capped or over-awarded."
                    ),
                )
            )

        positions = [c.position for c in rubric.criteria]
        if len(set(positions)) != len(positions):
            problems.append(
                RubricProblem(
                    question=label,
                    severity="error",
                    message="Two criteria share the same position.",
                )
            )

        if active_answer_key(db, question.id) is None:
            problems.append(
                RubricProblem(
                    question=label,
                    severity="warning",
                    message=(
                        "No answer key. Marking still works from the criteria "
                        "alone, but agreement with a human marker is usually "
                        "lower without one."
                    ),
                )
            )

        for criterion in rubric.criteria:
            if not criterion.essential_concepts:
                problems.append(
                    RubricProblem(
                        question=label,
                        severity="warning",
                        message=(
                            f"Criterion {criterion.position} lists no essential "
                            f"concepts, so it is judged from its description alone."
                        ),
                    )
                )
            # A criterion worth half the question makes the whole score hinge
            # on one judgement. Worth knowing before reading the confidence.
            if question.max_marks and criterion.max_marks / question.max_marks >= 0.5:
                problems.append(
                    RubricProblem(
                        question=label,
                        severity="warning",
                        message=(
                            f"Criterion {criterion.position} carries "
                            f"{criterion.max_marks:g} of {question.max_marks:g} "
                            f"marks. One judgement decides half the question."
                        ),
                    )
                )

    return RubricValidationOut(
        exam_id=exam.id,
        is_valid=not any(p.severity == "error" for p in problems),
        questions_checked=len(questions),
        criteria_checked=criteria_count,
        total_marks=round(sum(q.max_marks for q in questions), 4),
        problems=problems,
    )
