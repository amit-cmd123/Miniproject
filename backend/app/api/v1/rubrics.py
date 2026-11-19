"""Question bank and rubric endpoints - Part 2's public surface."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT
from app.db.models import Exam, Question, Rubric
from app.db.session import get_db
from app.schemas.rubrics import (
    AnswerKeyIn,
    AnswerKeyOut,
    CriterionOut,
    ExamDetailOut,
    ExamIn,
    ExamOut,
    QuestionIn,
    QuestionOut,
    ParsedPaperOut,
    ParsedSourceOut,
    QuestionPatch,
    RubricIn,
    RubricOut,
    RubricValidationOut,
    RubricVersionOut,
)
from app.services import document_text, rubric_import, rubric_service
from app.services.document_text import DocumentTextError
from app.services.rubric_import import RubricImportError
from app.services.rubric_service import RubricError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["questions & rubrics"])

# The exam shipped with the project: a 30-mark C programming paper with a
# rubric per question. Seeding it is how a demo gets something to mark.
SEED_PATH = REPO_ROOT / "data" / "exam" / "seed_exam.json"

# A typed marking scheme is a text document. The large allowance that
# scanned answer booklets get does not apply, and a 100 MB upload here is
# a mistake worth catching early.
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024


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


# ---------------------------------------------------------------------------
# Editing the paper
#
# Everything below changes institution-owned truth, so each route is explicit
# about what it keeps: a rubric is replaced by version and never mutated, an
# answer key the same, and a question that has been marked against cannot be
# deleted at all.
# ---------------------------------------------------------------------------


@router.post(
    "/exams/{exam_id}/questions",
    response_model=QuestionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_question(
    exam_id: str, payload: QuestionIn, db: Session = Depends(get_db)
) -> QuestionOut:
    """Add a question, optionally with its answer key and rubric."""
    exam = _get_exam(db, exam_id)

    if payload.rubric:
        total = round(sum(c.max_marks for c in payload.rubric.criteria), 4)
        if abs(total - payload.max_marks) > rubric_service.MARK_TOLERANCE:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"The criteria sum to {total:g} but the question is worth "
                f"{payload.max_marks:g}. A rubric that does not sum caps every "
                f"student silently, so it is refused here.",
            )
        positions = [c.position for c in payload.rubric.criteria]
        if len(set(positions)) != len(positions):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Two criteria share the same position."
            )

    if payload.number:
        existing = {q.number for q in rubric_service.questions_for(db, exam.id)}
        if payload.number in existing:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This paper already has a question numbered {payload.number}. "
                f"Booklet splitting matches on that number, so they must be "
                f"unique.",
            )

    try:
        question = rubric_service.add_question(db, exam, payload)
    except RubricError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _question_out(db, question)


@router.patch("/questions/{question_id}", response_model=QuestionOut)
def update_question(
    question_id: str, payload: QuestionPatch, db: Session = Depends(get_db)
) -> QuestionOut:
    """Edit a question's wording, topic, type or marks.

    Changing `max_marks` does not rescale the rubric. If the two no longer
    agree, validation says so and marking refuses - which is intended, because
    deciding what each criterion is now worth is an examiner's judgement, not
    an arithmetic convenience.
    """
    question = _get_question(db, question_id)

    if payload.number and payload.number != question.number:
        clash = [
            q
            for q in rubric_service.questions_for(db, question.exam_id)
            if q.number == payload.number and q.id != question.id
        ]
        if clash:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Another question on this paper is already numbered "
                f"{payload.number}.",
            )

    try:
        question = rubric_service.update_question(db, question, payload)
    except RubricError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _question_out(db, question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(question_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a question. Refused once anything has been marked against it."""
    question = _get_question(db, question_id)
    try:
        rubric_service.delete_question(db, question)
    except RubricError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/questions/{question_id}/answer-key", response_model=AnswerKeyOut)
def get_answer_key(question_id: str, db: Session = Depends(get_db)) -> AnswerKeyOut:
    question = _get_question(db, question_id)
    key = rubric_service.active_answer_key(db, question.id)
    if key is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "This question has no answer key yet."
        )
    return AnswerKeyOut.model_validate(key)


@router.put("/questions/{question_id}/answer-key", response_model=AnswerKeyOut)
def set_answer_key(
    question_id: str, payload: AnswerKeyIn, db: Session = Depends(get_db)
) -> AnswerKeyOut:
    """Write a new answer-key version. The previous one is kept, deactivated.

    The key is shown to the marker as a reference answer, not as text to
    match: it describes what a good answer contains, and a student who says
    the same thing differently still scores.
    """
    question = _get_question(db, question_id)
    key = rubric_service.set_answer_key(db, question, payload.reference_answer)
    return AnswerKeyOut.model_validate(key)


@router.get(
    "/questions/{question_id}/rubric/versions", response_model=list[RubricVersionOut]
)
def rubric_versions(
    question_id: str, db: Session = Depends(get_db)
) -> list[RubricVersionOut]:
    """Every rubric ever written for this question, newest first.

    Kept because evaluations cite a version number: without this, a score
    marked under version 2 of a rubric now on version 5 cannot be explained
    to the student it belongs to.
    """
    question = _get_question(db, question_id)
    return [
        RubricVersionOut(
            id=rubric.id,
            version=rubric.version,
            is_active=rubric.is_active,
            criteria_count=len(rubric.criteria),
            total_criterion_marks=rubric_service.total_criterion_marks(rubric),
            marking_scheme=rubric.marking_scheme,
            created_at=rubric.created_at,
        )
        for rubric in rubric_service.rubric_versions(db, question.id)
    ]


@router.get("/exams/{exam_id}/export")
def export_exam(exam_id: str, db: Session = Depends(get_db)) -> dict:
    """The whole paper as seed JSON, ready to commit to the repository.

    Round-trips with the import below, so a paper edited in the interface can
    be reviewed in a diff and seeded on another machine. A marking scheme
    that lives only in one laptop's database is not institution-owned.
    """
    exam = _get_exam(db, exam_id)
    return rubric_service.exam_to_seed(db, exam)


@router.post(
    "/exams/import", response_model=ExamDetailOut, status_code=status.HTTP_201_CREATED
)
def import_exam(payload: dict, db: Session = Depends(get_db)) -> ExamDetailOut:
    """Create a paper from seed JSON of the same shape `export` produces."""
    try:
        exam_in = rubric_service.exam_from_seed(payload)
    except RubricError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:  # malformed JSON shape
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"That does not look like an exam definition: {exc}",
        ) from exc

    try:
        exam = rubric_service.create_exam(db, exam_in)
    except RubricError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return ExamDetailOut(
        **_exam_out(db, exam).model_dump(),
        questions=[
            _question_out(db, question)
            for question in rubric_service.questions_for(db, exam.id)
        ],
    )


@router.delete("/exams/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exam(exam_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a whole paper. Refused once anything has been marked against it."""
    exam = _get_exam(db, exam_id)
    try:
        rubric_service.delete_exam(db, exam)
    except RubricError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/exams/parse-document", response_model=ParsedPaperOut)
async def parse_document(
    file: UploadFile = File(...),
    engine: str | None = Query(
        None,
        description=(
            "'gemini' reads the document with the cloud model; 'local' uses "
            "the built-in parser. Defaults to the local parser."
        ),
    ),
) -> ParsedPaperOut:
    """Read a typed question paper and propose a rubric from it.

    Nothing is saved. The reply is a proposal for the examiner to check and
    edit, which they then commit through `POST /exams/import`. A marking
    scheme decides a student's grade, so it does not enter the database on a
    parser's say-so.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That file is empty.")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"That document is larger than the {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB "
            f"limit for marking schemes.",
        )

    try:
        extracted = document_text.extract(data, file.filename or "", file.content_type)
    except DocumentTextError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        parsed = rubric_import.parse(extracted.text, engine=engine)
    except RubricImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    # Validate the proposal through the same door a hand-written paper uses,
    # so a preview that cannot be imported is caught here rather than after
    # the examiner has spent ten minutes editing it.
    try:
        rubric_service.exam_from_seed(parsed.seed)
    except RubricError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"The document was read, but the paper built from it is not usable: {exc}",
        ) from exc

    questions = parsed.seed.get("questions") or []
    return ParsedPaperOut(
        seed=parsed.seed,
        strategy=parsed.strategy,
        warnings=[*extracted.warnings, *parsed.warnings],
        unplaced_lines=parsed.unplaced_lines,
        source=ParsedSourceOut(
            filename=file.filename or "document",
            kind=extracted.kind,
            page_count=extracted.page_count,
            table_count=extracted.table_count,
            characters=len(extracted.text),
        ),
        question_count=len(questions),
        total_marks=round(sum(float(q["max_marks"]) for q in questions), 2),
    )
