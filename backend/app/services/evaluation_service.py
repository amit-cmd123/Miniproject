"""Marking orchestration - Part 3's service layer.

Sits between the API and the marking provider, and owns everything the
provider must not: how many independent readings to take, how they are
reconciled, how marks are computed from verdicts, how confidence is composed,
and how all of it is persisted so a score can be defended months later.

### The division of labour

    provider  ->  verdicts, with quotations     (judgement; a model)
    scoring   ->  marks and confidence          (arithmetic; pure Python)
    this file ->  which readings, what is kept  (orchestration; a database)

A provider never sees a mark value and never adds anything up. Re-running the
arithmetic on stored verdicts reproduces the score exactly, which is what
makes a disputed mark investigable rather than a matter of opinion.

### Booklets

A scanned booklet arrives as pages but is marked as questions. `segment_booklet`
splits the transcription per question and records, for each one, a derived
answer carrying just that question's text. Marks then hang off the same
`Answer`/`Evaluation`/`Review` chain as a single-answer upload, so the review
and audit paths have no special case for booklets.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.thresholds import classify_evaluation
from app.db.models import (
    Answer,
    Evaluation,
    EvaluationCriterion,
    Exam,
    OCRResult,
    Question,
    Rubric,
)
from app.providers.evaluation.base import (
    NOT_SATISFIED,
    CriterionSpec,
    EvaluationProvider,
    MarkingJudgement,
    MarkingTask,
)
from app.schemas.enums import AnswerStatus, ReviewBand, TextSource
from app.services import audit, rubric_service, scoring

logger = logging.getLogger(__name__)

# Temperature of each reading. The first is deterministic so the result is
# reproducible; later ones are sampled, because two identical requests to a
# zero-temperature model measure nothing at all.
SAMPLE_TEMPERATURES = (0.0, 0.7, 0.9, 1.0, 1.0)

# Below this, the transcription is too poor for a mark to mean anything.
MIN_TRANSCRIPTION_FOR_MARKING = 0.10


class EvaluationError(RuntimeError):
    """Marking could not be completed. Surfaced to the caller, never swallowed
    into a plausible-looking score of zero."""


@dataclass
class ScoredCriterion:
    position: int
    description: str
    max_marks: float
    awarded_marks: float
    verdict: str
    reason: str
    evidence_quote: str | None
    evidence_found: bool
    rubric_criterion_id: str | None


# ---------------------------------------------------------------------------
# Building the marking task
# ---------------------------------------------------------------------------


def build_task(
    question: Question,
    rubric: Rubric,
    answer_key: str | None,
    student_text: str,
) -> MarkingTask:
    """Assemble a marking request with the mark values stripped out."""
    specs = [
        CriterionSpec(
            position=criterion.position,
            description=criterion.description,
            essential_concepts=list(criterion.essential_concepts or []),
            acceptable_alternatives=list(criterion.acceptable_alternatives or []),
            common_mistakes=list(criterion.common_mistakes or []),
            allows_partial=bool(criterion.allows_partial),
        )
        for criterion in sorted(rubric.criteria, key=lambda c: c.position)
    ]
    return MarkingTask(
        question_number=question.number or "-",
        question_text=question.text,
        question_type=question.question_type,
        student_text=student_text,
        criteria=specs,
        answer_key=answer_key,
        rules=rubric_service.scoring_rules_for(rubric),
    )


def read_independently(
    provider: EvaluationProvider, task: MarkingTask, samples: int
) -> list[MarkingJudgement]:
    """Take `samples` independent readings, concurrently.

    A failure in a later reading is tolerated: one usable reading still yields
    a score, with the agreement signal recorded as unmeasured rather than
    quietly assumed. A failure in the *first* reading fails the request.
    """
    samples = max(1, min(samples, len(SAMPLE_TEMPERATURES)))
    if samples == 1:
        return [provider.judge(task, temperature=SAMPLE_TEMPERATURES[0])]

    with ThreadPoolExecutor(max_workers=samples) as pool:
        futures = [
            pool.submit(provider.judge, task, temperature=SAMPLE_TEMPERATURES[index])
            for index in range(samples)
        ]
        results: list[MarkingJudgement] = []
        errors: list[str] = []
        for index, future in enumerate(futures):
            try:
                results.append(future.result())
            except Exception as exc:  # provider-specific; reported, not raised
                logger.warning("Reading %s of %s failed: %s", index + 1, samples, exc)
                errors.append(str(exc))

    if not results:
        raise EvaluationError(errors[0] if errors else "No reading could be completed.")
    if errors:
        results[0].warnings.append(
            f"{len(errors)} of {samples} independent readings failed, so "
            f"agreement was measured over fewer. First error: {errors[0]}"
        )
    return results


# ---------------------------------------------------------------------------
# Scoring one answer
# ---------------------------------------------------------------------------


def score_judgement(
    judgement: MarkingJudgement,
    rubric: Rubric,
    question: Question,
    student_text: str,
) -> tuple[float, list[ScoredCriterion]]:
    """Attach marks to verdicts. The only place a score is decided."""
    rules = rubric_service.scoring_rules_for(rubric)
    step = float(rules.get("round_to") or 0.5)
    partial_allowed_globally = rules.get("partial_credit", True)

    by_position = {c.position: c for c in rubric.criteria}
    scored: list[ScoredCriterion] = []

    for verdict in judgement.criteria:
        criterion = by_position.get(verdict.position)
        if criterion is None:
            continue

        allows_partial = bool(criterion.allows_partial) and bool(partial_allowed_globally)
        awarded = scoring.criterion_marks(
            verdict.verdict,
            verdict.coverage,
            criterion.max_marks,
            allows_partial=allows_partial,
            step=step,
        )

        quote = verdict.evidence_quote
        found = True
        if verdict.verdict != NOT_SATISFIED and quote:
            found = scoring.grounding_ratio(quote, student_text) >= scoring.GROUNDING_MATCH
        elif verdict.verdict != NOT_SATISFIED and not quote:
            found = False

        scored.append(
            ScoredCriterion(
                position=verdict.position,
                description=criterion.description,
                max_marks=round(criterion.max_marks, 4),
                awarded_marks=awarded,
                verdict=verdict.verdict,
                reason=verdict.reason,
                evidence_quote=quote,
                evidence_found=found,
                rubric_criterion_id=criterion.id,
            )
        )

    total = scoring.quantise(sum(c.awarded_marks for c in scored), step)
    total = max(0.0, min(total, question.max_marks))
    return round(total, 4), scored


def compose_confidence(
    judgement: MarkingJudgement,
    consensus: scoring.Consensus,
    rubric: Rubric,
    question: Question,
    student_text: str,
    transcription_confidence: float,
) -> tuple[float, dict]:
    """Measure the four signals and combine them."""
    marks_by_position = {c.position: c.max_marks for c in rubric.criteria}
    load_bearing = rubric_service.load_bearing_positions(rubric)

    grounding, fabricated = scoring.evidence_grounding(judgement, student_text)
    decisive = scoring.decisiveness(judgement, marks_by_position, load_bearing)

    confidence, detail = scoring.composite_confidence(
        {
            "transcription": transcription_confidence,
            "agreement": consensus.agreement,
            "grounding": grounding,
            "decisiveness": decisive,
        }
    )

    detail["samples"] = consensus.samples
    detail["disputed_criteria"] = consensus.disputed
    detail["ungrounded_criteria"] = fabricated
    detail["load_bearing_criteria"] = sorted(load_bearing)
    if consensus.agreement is None:
        detail["note"] = (
            "Only one reading was taken, so marker agreement could not be "
            "measured and its weight was redistributed. "
            + str(detail.get("note", ""))
        ).strip()
    return confidence, detail


def _confidence_warnings(detail: dict, scored: list[ScoredCriterion]) -> list[str]:
    warnings: list[str] = []

    disputed = detail.get("disputed_criteria") or []
    if disputed:
        warnings.append(
            "The two independent markings disagreed on criterion "
            + ", ".join(str(p) for p in disputed)
            + ". The lower verdict was taken; an examiner should decide."
        )

    ungrounded = detail.get("ungrounded_criteria") or []
    if ungrounded:
        warnings.append(
            "The quotation cited for criterion "
            + ", ".join(str(p) for p in ungrounded)
            + " could not be found in the transcription, so that judgement was "
            "not read off the page. Treat those marks as unverified."
        )

    missing_quotes = [
        c.position for c in scored if c.verdict != NOT_SATISFIED and not c.evidence_quote
    ]
    if missing_quotes:
        warnings.append(
            "Marks were awarded on criterion "
            + ", ".join(str(p) for p in missing_quotes)
            + " without quoting the answer."
        )

    signals = detail.get("signals") or {}
    if signals.get("transcription", 1.0) < 0.70:
        warnings.append(
            "These marks rest on a transcription that is itself uncertain. "
            "Correct the text first, then re-mark - the score will change."
        )
    return warnings


# ---------------------------------------------------------------------------
# The public entry point for one answer
# ---------------------------------------------------------------------------


@dataclass
class _Prepared:
    """Everything needed to mark one answer, with no database left to touch.

    Splitting preparation from the network call is what lets a whole booklet
    be marked concurrently: a SQLAlchemy Session is not thread-safe, so the
    database work happens before and after the parallel phase, never during
    it.
    """

    answer: Answer
    question: Question
    ocr_result: OCRResult
    rubric: Rubric
    task: MarkingTask
    student_text: str
    transcription_confidence: float
    human_verified: bool
    samples: int
    started: float


def _prepare(
    db: Session,
    answer: Answer,
    question: Question,
    ocr_result: OCRResult,
    *,
    samples: int | None = None,
) -> _Prepared:
    """Validate the rubric and the transcription, and build the request.

    Raises before any network call is made, so a question that cannot be
    marked costs nothing.
    """
    started = time.perf_counter()

    rubric = rubric_service.active_rubric(db, question.id)
    if rubric is None or not rubric.criteria:
        raise EvaluationError(
            f"Question {question.number or question.id} has no active rubric, so "
            f"it cannot be marked. Add one in Questions & rubrics."
        )

    total_defined = rubric_service.total_criterion_marks(rubric)
    if abs(total_defined - question.max_marks) > rubric_service.MARK_TOLERANCE:
        raise EvaluationError(
            f"The rubric for {question.number or 'this question'} sums to "
            f"{total_defined:g} but the question is worth {question.max_marks:g}. "
            f"Fix the rubric before marking - every score would be wrong."
        )

    student_text = (ocr_result.effective_text or "").strip()
    human_verified = ocr_result.corrected_text is not None

    # A human-corrected transcription is ground truth, so transcription
    # uncertainty no longer applies to it.
    transcription_confidence = 1.0 if human_verified else float(ocr_result.confidence)

    if not student_text:
        raise EvaluationError(
            "There is no transcribed text for this answer, so there is nothing "
            "to mark. Re-run transcription, or type the text in by hand."
        )
    if transcription_confidence < MIN_TRANSCRIPTION_FOR_MARKING:
        raise EvaluationError(
            f"The transcription confidence is {transcription_confidence:.0%}, which "
            f"is too low for a mark to mean anything. Correct the text by hand "
            f"first - the system will then treat it as verified."
        )

    answer_key = rubric_service.active_answer_key(db, question.id)
    task = build_task(
        question, rubric, answer_key.reference_answer if answer_key else None, student_text
    )

    wanted = samples if samples is not None else settings.evaluation_samples
    wanted = max(1, min(wanted, len(SAMPLE_TEMPERATURES)))

    return _Prepared(
        answer=answer,
        question=question,
        ocr_result=ocr_result,
        rubric=rubric,
        task=task,
        student_text=student_text,
        transcription_confidence=transcription_confidence,
        human_verified=human_verified,
        samples=wanted,
        started=started,
    )


def _persist(
    db: Session,
    prep: _Prepared,
    readings: list[MarkingJudgement],
    provider: EvaluationProvider,
) -> Evaluation:
    """Turn finished readings into marks and rows. No network."""
    answer = prep.answer
    question = prep.question
    rubric = prep.rubric
    ocr_result = prep.ocr_result
    student_text = prep.student_text
    human_verified = prep.human_verified
    transcription_confidence = prep.transcription_confidence
    started = prep.started

    if not readings:
        raise EvaluationError("No reading could be completed.")

    agreed = scoring.consensus(readings)

    score, scored = score_judgement(agreed.judgement, rubric, question, student_text)
    confidence, detail = compose_confidence(
        agreed.judgement,
        agreed,
        rubric,
        question,
        student_text,
        transcription_confidence,
    )

    band = classify_evaluation(confidence)
    warnings = list(dict.fromkeys(agreed.judgement.warnings + _confidence_warnings(detail, scored)))
    info = provider.info()

    record = Evaluation(
        answer_id=answer.id,
        rubric_id=rubric.id,
        ocr_result_id=ocr_result.id,
        score=score,
        max_score=round(question.max_marks, 4),
        confidence=confidence,
        review_band=band.band,
        overall_explanation=agreed.judgement.summary,
        confidence_signals={**detail, "warnings": warnings},
        provider=info.name,
        model_name=info.model_name,
        model_version=info.model_version,
        prompt_version=info.prompt_version,
        rubric_version=rubric.version,
        text_source=TextSource.HUMAN_CORRECTED if human_verified else TextSource.MACHINE,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    db.add(record)
    db.flush()

    for criterion in scored:
        db.add(
            EvaluationCriterion(
                evaluation_id=record.id,
                rubric_criterion_id=criterion.rubric_criterion_id,
                position=criterion.position,
                description=criterion.description,
                awarded_marks=criterion.awarded_marks,
                max_marks=criterion.max_marks,
                verdict=criterion.verdict,
                reason=criterion.reason,
                evidence_quote=criterion.evidence_quote,
            )
        )

    if answer.question_id is None:
        answer.question_id = question.id
    answer.status = AnswerStatus.EVALUATED
    db.commit()
    db.refresh(record)

    audit.record(
        db,
        action="evaluation.completed",
        object_type="answer",
        object_id=answer.id,
        details={
            "question": question.number,
            "score": score,
            "max": question.max_marks,
            "confidence": confidence,
            "band": band.band,
            "samples": agreed.samples,
            "provider": info.name,
            "model": info.model_name,
            "rubric_version": rubric.version,
        },
    )
    return record


def evaluate_answer(
    db: Session,
    answer: Answer,
    question: Question,
    ocr_result: OCRResult,
    provider: EvaluationProvider,
    *,
    samples: int | None = None,
) -> Evaluation:
    """Mark one transcribed answer against its rubric, and persist the result."""
    prep = _prepare(db, answer, question, ocr_result, samples=samples)
    readings = read_independently(provider, prep.task, prep.samples)
    return _persist(db, prep, readings, provider)


def read_many(
    provider: EvaluationProvider,
    preps: list[_Prepared],
    *,
    max_workers: int | None = None,
) -> tuple[dict[int, list[MarkingJudgement]], dict[int, str]]:
    """Take every reading for every answer in one bounded pool.

    Marking a booklet one question at a time spent almost all of its wall
    clock waiting on Google in series. Every (answer, reading) pair is an
    independent request, so they go into a single pool instead: the model
    sees exactly the same bytes, so the marks are unchanged, and a six
    question script finishes in about the time one question used to take.

    The pool is bounded rather than unbounded because the free tier answers a
    burst of a dozen simultaneous requests with 429, and a rate limit is
    slower than a queue.

    Returns the readings per answer index, and a message per answer index
    that produced none - a question whose network calls all failed is
    reported, never silently scored from nothing.
    """
    jobs: list[tuple[int, float]] = [
        (index, SAMPLE_TEMPERATURES[sample])
        for index, prep in enumerate(preps)
        for sample in range(prep.samples)
    ]
    if not jobs:
        return {}, {}

    cap = max_workers or settings.evaluation_max_concurrency
    workers = max(1, min(cap, len(jobs)))

    readings: dict[int, list[MarkingJudgement]] = {i: [] for i in range(len(preps))}
    failures: dict[int, str] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(provider.judge, preps[index].task, temperature=temperature): index
            for index, temperature in jobs
        }
        for future in futures:
            index = futures[future]
            try:
                readings[index].append(future.result())
            except Exception as exc:  # provider-specific; reported, not raised
                logger.warning(
                    "A reading of %s failed: %s",
                    preps[index].question.number or preps[index].question.id[:8],
                    exc,
                )
                failures.setdefault(index, str(exc))

    for index, got in readings.items():
        if got:
            failures.pop(index, None)

    return readings, failures


def latest_evaluation(db: Session, answer_id: str) -> Evaluation | None:
    return db.scalars(
        select(Evaluation)
        .where(Evaluation.answer_id == answer_id)
        .order_by(Evaluation.created_at.desc())
    ).first()


def evaluations_for_answer(db: Session, answer_id: str) -> list[Evaluation]:
    return list(
        db.scalars(
            select(Evaluation)
            .where(Evaluation.answer_id == answer_id)
            .order_by(Evaluation.created_at.desc())
        )
    )


# ---------------------------------------------------------------------------
# Booklets
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """One question's answer, extracted from a booklet transcription."""

    question: Question
    text: str
    page_numbers: list[int]
    located_by: str
    transcription_confidence: float
    found: bool


def booklet_pages(db: Session, document_ref: str) -> list[Answer]:
    return list(
        db.scalars(
            select(Answer)
            .where(Answer.document_ref == document_ref)
            .order_by(Answer.page_number)
        )
    )


def _line_sources(pages: list[Answer]) -> tuple[list[str], list[int], list[float]]:
    """Flatten a booklet into lines, remembering each line's page and confidence."""
    lines: list[str] = []
    page_of: list[int] = []
    confidence_of: list[float] = []

    for page in pages:
        record = page.latest_ocr
        if record is None:
            continue
        text = (record.effective_text or "").strip()
        if not text:
            continue
        # A human-corrected page is ground truth for its own lines.
        page_confidence = 1.0 if record.corrected_text is not None else float(record.confidence)
        for line in text.splitlines():
            if not line.strip():
                continue
            lines.append(line.rstrip())
            page_of.append(page.page_number or 0)
            confidence_of.append(page_confidence)

    return lines, page_of, confidence_of


def segment_booklet(
    db: Session, document_ref: str, exam: Exam
) -> tuple[list[Segment], str, list[str]]:
    """Split a transcribed booklet into one answer per question.

    Markers first, a model only if those fail. Returns the segments, any text
    that belonged to no answer, and warnings describing how it was done.
    """
    from app.providers.segmentation import get_splitter, split_by_markers

    pages = booklet_pages(db, document_ref)
    if not pages:
        raise EvaluationError(f"No transcribed pages found for document {document_ref}.")

    questions = rubric_service.questions_for(db, exam.id)
    if not questions:
        raise EvaluationError(f"Exam '{exam.title}' has no questions to mark against.")

    numbered: dict[int, Question] = {}
    for question in questions:
        digits = "".join(c for c in (question.number or "") if c.isdigit())
        if digits:
            numbered[int(digits)] = question

    lines, page_of, confidence_of = _line_sources(pages)
    warnings: list[str] = []

    if not lines:
        raise EvaluationError(
            "The booklet has no transcribed text. Transcribe it before marking."
        )

    # Only one question on the paper: the whole booklet is its answer, and
    # splitting it would be a way to go wrong for no benefit.
    if len(questions) == 1:
        question = questions[0]
        return (
            [
                Segment(
                    question=question,
                    text="\n".join(lines),
                    page_numbers=sorted(set(page_of)),
                    located_by="whole_page",
                    transcription_confidence=_weighted(confidence_of, lines),
                    found=True,
                )
            ],
            "",
            warnings,
        )

    ranges, split = split_by_markers(lines, set(numbered))
    warnings.extend(split.warnings)

    # Fall back to a model only when markers found almost nothing. One or two
    # located answers out of six means the numbering was not readable.
    if len(ranges) < 2 and len(numbered) > 1:
        splitter = get_splitter()
        model_ranges, model_split = splitter.split(
            lines, [(number, q.text) for number, q in sorted(numbered.items())]
        )
        warnings.extend(model_split.warnings)
        if len(model_ranges) > len(ranges):
            ranges, split = model_ranges, model_split

    claimed: set[int] = set()
    segments: list[Segment] = []

    for number, question in sorted(numbered.items()):
        bounds = ranges.get(number)
        if bounds is None:
            segments.append(
                Segment(
                    question=question,
                    text="",
                    page_numbers=[],
                    located_by=split.method,
                    transcription_confidence=0.0,
                    found=False,
                )
            )
            continue

        start, end = bounds
        claimed.update(range(start, end))
        chunk = lines[start:end]
        segments.append(
            Segment(
                question=question,
                text="\n".join(chunk).strip(),
                page_numbers=sorted(set(page_of[start:end])),
                located_by=split.method,
                transcription_confidence=_weighted(confidence_of[start:end], chunk),
                found=bool("\n".join(chunk).strip()),
            )
        )

    leftover = "\n".join(
        line for index, line in enumerate(lines) if index not in claimed
    ).strip()

    return segments, leftover, warnings


def _weighted(confidences: list[float], lines: list[str]) -> float:
    """Length-weighted mean confidence, for the same reason pages are weighted."""
    if not confidences or not lines:
        return 0.0
    weights = np.array([max(len(line), 1) for line in lines[: len(confidences)]], dtype=float)
    values = np.array(confidences[: len(weights)], dtype=float)
    if not weights.sum():
        return 0.0
    return round(float((values * weights).sum() / weights.sum()), 4)


def derived_answer_for(
    db: Session,
    segment: Segment,
    pages: list[Answer],
    document_ref: str,
    booklet_ref: str | None,
) -> tuple[Answer, OCRResult]:
    """An `Answer` holding just one question's text, reusing an existing one.

    Marks must hang off an `Answer` so that review, audit and ground truth
    work identically for a booklet and for a single uploaded photograph. The
    row is keyed by document and question, so re-marking a booklet updates its
    derived answers instead of accumulating duplicates.

    No new table and no migration: the provenance of a derived answer lives in
    the transcription's `preprocessing` JSON, which already exists.
    """
    source_page = next(
        (p for p in pages if (p.page_number or 0) in segment.page_numbers), pages[0]
    )

    existing = db.scalars(
        select(Answer).where(
            Answer.document_ref == document_ref,
            Answer.question_id == segment.question.id,
            Answer.page_number.is_(None),
        )
    ).first()

    if existing is None:
        existing = Answer(
            question_id=segment.question.id,
            booklet_ref=booklet_ref or source_page.booklet_ref,
            document_ref=document_ref,
            page_number=None,
            source_filename=source_page.source_filename,
            image_path=source_page.image_path,
            original_filename=(
                f"{source_page.source_filename or 'booklet'} "
                f"{segment.question.number or ''}".strip()
            ),
            content_type=source_page.content_type,
            size_bytes=source_page.size_bytes,
            status=AnswerStatus.OCR_DONE,
        )
        db.add(existing)
        db.flush()

    template = source_page.latest_ocr
    record = OCRResult(
        answer_id=existing.id,
        extracted_text=segment.text,
        confidence=segment.transcription_confidence,
        transcription_band=(
            template.transcription_band if template else "unusable"
        ),
        needs_verification=segment.transcription_confidence < 0.95,
        line_count=len([line for line in segment.text.splitlines() if line.strip()]),
        word_count=len(segment.text.split()),
        provider=template.provider if template else "unknown",
        model_name=template.model_name if template else "unknown",
        model_version=template.model_version if template else "unknown",
        device=template.device if template else "unknown",
        duration_ms=0,
        lines=[],
        preprocessing={
            "derived_from_document": document_ref,
            "derived_from_pages": segment.page_numbers,
            "question_number": segment.question.number,
            "located_by": segment.located_by,
            "note": (
                "Text extracted from a booklet transcription, not read from an "
                "image directly. The image is the page the answer starts on."
            ),
        },
        warnings=[],
    )
    db.add(record)
    db.flush()
    return existing, record


def evaluate_booklet(
    db: Session,
    document_ref: str,
    exam: Exam,
    provider: EvaluationProvider,
    *,
    booklet_ref: str | None = None,
    samples: int | None = None,
) -> tuple[list[Evaluation], list[Segment], str, list[str]]:
    """Mark every attempted question in one transcribed booklet.

    A question that fails to mark is reported and the rest continue: one bad
    rubric or one network failure must not lose a whole script.
    """
    pages = booklet_pages(db, document_ref)
    segments, leftover, warnings = segment_booklet(db, document_ref, exam)

    evaluations: list[Evaluation] = []

    # Phase 1 - database only. Derive the per-question answer rows and
    # validate every rubric before a single request is sent, so a paper with
    # a broken rubric costs nothing.
    preps: list[_Prepared] = []
    labels: list[str] = []

    for segment in segments:
        label = segment.question.number or segment.question.id[:8]

        if not segment.found or not segment.text.strip():
            warnings.append(
                f"{label}: no answer was located in the booklet, so it was not "
                f"marked. It scores zero unless an examiner finds it."
            )
            continue

        try:
            answer, record = derived_answer_for(
                db, segment, pages, document_ref, booklet_ref
            )
            preps.append(
                _prepare(db, answer, segment.question, record, samples=samples)
            )
            labels.append(label)
        except EvaluationError as exc:
            db.rollback()
            logger.warning("Marking %s failed: %s", label, exc)
            warnings.append(f"{label} could not be marked: {exc}")

    # Phase 2 - network only, all questions and all readings at once.
    readings, failures = read_many(provider, preps)

    # Phase 3 - database only. Marks are computed here, in Python, exactly as
    # they were when this ran in series.
    for index, prep in enumerate(preps):
        label = labels[index]
        if index in failures:
            warnings.append(f"{label} could not be marked: {failures[index]}")
            continue
        try:
            evaluations.append(_persist(db, prep, readings.get(index, []), provider))
        except EvaluationError as exc:
            db.rollback()
            logger.warning("Marking %s failed: %s", label, exc)
            warnings.append(f"{label} could not be marked: {exc}")

    if leftover:
        warnings.append(
            f"{len(leftover.splitlines())} transcribed line(s) were not assigned "
            f"to any question. They are shown under 'unassigned text'."
        )

    return evaluations, segments, leftover, warnings


def booklet_totals(
    evaluations: list[Evaluation], segments: list[Segment]
) -> dict[str, object]:
    """Roll per-question marks up into a script total.

    The total maximum is the whole paper, not just the questions that were
    marked: a student who skipped a question scored zero on it, and reporting
    18/20 when the paper is worth 30 would be a lie of omission.
    """
    total_max = round(sum(s.question.max_marks for s in segments), 4)
    total_score = round(sum(e.score for e in evaluations), 4)

    if evaluations:
        weights = np.array([max(e.max_score, 0.01) for e in evaluations], dtype=float)
        values = np.array([e.confidence for e in evaluations], dtype=float)
        overall = round(float((values * weights).sum() / weights.sum()), 4)
    else:
        overall = 0.0

    band = classify_evaluation(overall)
    return {
        "total_score": total_score,
        "total_max": total_max,
        "percentage": round(100.0 * total_score / total_max, 2) if total_max else 0.0,
        "overall_confidence": overall,
        "review_band": band.band,
        "band_label": band.label,
        "needs_review": [_label(e) for e in evaluations
                         if e.review_band != ReviewBand.AUTO_ACCEPT],
    }


def _label(evaluation: Evaluation) -> str:
    """How to refer to one marked answer in a message to a human."""
    answer = evaluation.answer
    if answer is not None and answer.question is not None and answer.question.number:
        return answer.question.number
    return evaluation.answer_id[:8]
