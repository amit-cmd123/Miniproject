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


def add_question(db: Session, exam: Exam, payload: QuestionIn) -> Question:
    """Append one question, with its answer key and rubric, to an exam."""
    question = _add_question(db, exam, payload)
    db.commit()
    db.refresh(question)

    audit.record(
        db,
        action="question.added",
        object_type="exam",
        object_id=exam.id,
        details={
            "question": question.number,
            "max_marks": question.max_marks,
            "criteria": len(payload.rubric.criteria) if payload.rubric else 0,
        },
    )
    return question


def update_question(db: Session, question: Question, payload: "QuestionPatch") -> Question:
    """Change a question's wording or marks in place.

    The rubric is a separate, versioned object and is not touched here. Note
    that raising `max_marks` can leave an existing rubric no longer summing to
    the question - deliberately: it is reported by validation rather than
    silently rescaled, because quietly changing what each criterion is worth
    is not a decision software should make on an examiner's behalf.
    """
    fields = payload.model_dump(exclude_unset=True)
    changed: dict[str, object] = {}

    for name in ("number", "text", "topic", "question_type", "max_marks"):
        if name in fields and fields[name] is not None:
            if getattr(question, name) != fields[name]:
                changed[name] = fields[name]
                setattr(question, name, fields[name])

    if changed:
        db.commit()
        db.refresh(question)
        audit.record(
            db,
            action="question.updated",
            object_type="question",
            object_id=question.id,
            details=changed,
        )
    return question


def delete_question(db: Session, question: Question) -> None:
    """Remove a question, its rubrics and its answer keys.

    Refused once anything has been marked against it: an evaluation that
    cites a rubric which no longer exists is an unauditable score, and the
    whole point of the append-only design is that past decisions stay
    explicable.
    """
    from app.db.models import Answer, Evaluation

    marked = db.execute(
        select(Evaluation.id)
        .join(Answer, Answer.id == Evaluation.answer_id)
        .where(Answer.question_id == question.id)
        .limit(1)
    ).first()
    if marked:
        raise RubricError(
            f"Question {question.number or question.id[:8]} has already been "
            f"marked, so it cannot be deleted - the scores that cite its "
            f"rubric would no longer be explicable. Edit its wording or its "
            f"rubric instead."
        )

    number = question.number
    exam_id = question.exam_id

    # Delete the children explicitly. The relationships are not configured to
    # cascade, so SQLAlchemy would otherwise try to null their question_id and
    # fail the NOT NULL constraint - leaving the question undeleted and the
    # session broken.
    for rubric in rubric_versions(db, question.id):
        for criterion in list(rubric.criteria):
            db.delete(criterion)
        db.delete(rubric)
    for key in (
        db.execute(select(AnswerKey).where(AnswerKey.question_id == question.id))
        .scalars()
        .all()
    ):
        db.delete(key)
    db.flush()

    db.delete(question)
    db.commit()

    audit.record(
        db,
        action="question.deleted",
        object_type="exam",
        object_id=exam_id,
        details={"question": number},
    )


def delete_exam(db: Session, exam: Exam) -> None:
    """Remove a whole paper. Refused once anything has been marked against it.

    Importing a paper is cheap, so deleting one has to be possible or the
    picker fills up with half-finished experiments. The guard is the same as
    for a single question: a score that cites a rubric which no longer exists
    cannot be explained to the student who received it.
    """
    from app.db.models import Answer, Evaluation

    marked = db.execute(
        select(Evaluation.id)
        .join(Answer, Answer.id == Evaluation.answer_id)
        .join(Question, Question.id == Answer.question_id)
        .where(Question.exam_id == exam.id)
        .limit(1)
    ).first()
    if marked:
        raise RubricError(
            f"'{exam.title}' has answers marked against it, so it cannot be "
            f"deleted - those scores cite its rubrics. Edit the paper instead."
        )

    title = exam.title
    _delete_exam(db, exam)
    db.commit()

    audit.record(
        db,
        action="exam.deleted",
        object_type="exam",
        object_id=exam.id,
        details={"title": title},
    )


def set_answer_key(db: Session, question: Question, reference_answer: str) -> AnswerKey:
    """Write a new answer-key version and retire the previous one.

    Versioned for the same reason rubrics are: an examiner looking at a mark
    from last term needs the key that was in force then, not the one someone
    improved afterwards.
    """
    current = active_answer_key(db, question.id)
    next_version = (current.version + 1) if current else 1
    if current:
        current.is_active = False

    key = AnswerKey(
        question_id=question.id,
        reference_answer=reference_answer,
        version=next_version,
        is_active=True,
    )
    db.add(key)
    db.commit()
    db.refresh(key)

    audit.record(
        db,
        action="answer_key.replaced",
        object_type="question",
        object_id=question.id,
        details={"version": next_version},
    )
    return key


def rubric_versions(db: Session, question_id: str) -> list[Rubric]:
    """Every rubric ever written for a question, newest first."""
    return list(
        db.execute(
            select(Rubric)
            .where(Rubric.question_id == question_id)
            .order_by(Rubric.version.desc())
        )
        .scalars()
        .all()
    )


def exam_to_seed(db: Session, exam: Exam) -> dict:
    """Export an exam in exactly the shape `seed_exam.json` uses.

    Round-trips with `exam_from_seed`, so a paper edited in the interface can
    be written to the repository, reviewed in a diff and seeded on another
    machine. A rubric that lives only in one laptop's database is not an
    institution-owned marking scheme.

    The shape is the seed file's, not a convenient one: metadata under
    `exam`, criteria directly on each question, and `scoring_rules` shared at
    the top. Inventing a second format here would mean the export could not
    be fed back in, which is the only thing that makes it worth having.
    """
    questions: list[dict] = []
    shared_rules: dict = {}

    for question in questions_for(db, exam.id):
        rubric = active_rubric(db, question.id)
        key = active_answer_key(db, question.id)

        entry: dict = {
            "number": question.number,
            "text": question.text,
            "topic": question.topic,
            "question_type": question.question_type,
            "max_marks": question.max_marks,
        }
        if key:
            entry["answer_key"] = key.reference_answer

        if rubric:
            if rubric.marking_scheme:
                entry["marking_scheme"] = rubric.marking_scheme
            # The rules are a property of the paper in the seed format, so the
            # first rubric that carries them supplies them for the document.
            if not shared_rules and rubric.scoring_rules:
                shared_rules = {
                    k: v
                    for k, v in rubric.scoring_rules.items()
                    if k != "load_bearing_positions"
                }
            load_bearing = load_bearing_positions(rubric)
            entry["criteria"] = [
                {
                    "position": c.position,
                    "description": c.description,
                    "max_marks": c.max_marks,
                    "essential_concepts": list(c.essential_concepts or []),
                    "acceptable_alternatives": list(c.acceptable_alternatives or []),
                    "common_mistakes": list(c.common_mistakes or []),
                    "allows_partial": bool(c.allows_partial),
                    "load_bearing": c.position in load_bearing,
                }
                for c in sorted(rubric.criteria, key=lambda c: c.position)
            ]

        questions.append(entry)

    document: dict = {
        "exam": {
            "code": exam.subject_code,
            "title": exam.title,
            "subject": exam.subject,
            "total_marks": round(sum(q.max_marks for q in questions_for(db, exam.id)), 4),
        },
        "questions": questions,
    }
    if exam.term:
        document["exam"]["term"] = exam.term
    if shared_rules:
        document["scoring_rules"] = shared_rules
    return document


# ---------------------------------------------------------------------------
# Seeding from a file
# ---------------------------------------------------------------------------


def exam_from_seed(document: dict) -> ExamIn:
    """Turn a `seed_exam.json` document into the API's own input shape.

    Going through `ExamIn` rather than writing rows directly means a seed file
    is validated by exactly the same rules as an exam posted to the API.
    """
    if not isinstance(document, dict):
        raise RubricError("An exam definition must be a JSON object.")

    meta = document.get("exam") or {}
    shared_rules = document.get("scoring_rules") or {}
    entries = document.get("questions")

    # Without this, a document with no recognisable fields imported happily as
    # "Untitled exam" with no questions - an empty paper that silently cannot
    # mark anything, which is worse than a refusal.
    if not isinstance(entries, list) or not entries:
        raise RubricError(
            "This document has no 'questions' list, so it is not an exam "
            "definition. Export a paper to see the expected shape."
        )
    if not meta.get("title") and not document.get("title"):
        raise RubricError(
            "This document has no exam title. Expected a top-level 'exam' "
            "object with at least a 'title'."
        )

    questions: list[QuestionIn] = []
    for entry in entries:
        if not isinstance(entry, dict) or "text" not in entry or "max_marks" not in entry:
            raise RubricError(
                "Every question needs at least 'text' and 'max_marks'."
            )
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
        title=meta.get("title") or document.get("title") or "Untitled exam",
        subject=meta.get("subject") or document.get("subject") or "Unspecified",
        subject_code=meta.get("code") or document.get("subject_code"),
        term=meta.get("term") or document.get("term"),
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
