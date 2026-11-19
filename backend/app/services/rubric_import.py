"""Turning a typed marking scheme into a paper EvalNova can mark against.

`document_text.py` hands this module plain text. This module finds the
questions in it, finds the criteria under each question, finds what each is
worth, and emits the same seed document that `rubric_service.exam_from_seed`
already accepts - so an imported paper and a hand-written one are the same
thing from the first moment, with no second code path to keep in step.

### Two parsers, and why the weaker one is the default

`parse_locally` is deterministic regular expressions. It handles the shapes a
marking scheme is actually written in - numbered questions, bulleted or
tabulated criteria, marks in brackets or in a right-hand column - and it
cannot invent a criterion that was not in the document, because it can only
copy spans of it.

`parse_with_gemini` reads the document properly and handles prose that the
regular expressions cannot. It is better at messy input and it is the one
worth demonstrating, but it is also capable of *paraphrasing* a criterion, so
what comes back is a proposal.

Both are proposals. Nothing imported here is written to the database by this
module: the caller gets a seed document to show the examiner, who edits it in
the rubric editor and commits it. A marking scheme is the document that
decides a student's grade, and it is not something to accept from a parser
unseen.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MARK_TOLERANCE = 0.001

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# "(5 marks)", "[5]", "- 5 marks", "5 M", "Marks: 5"
_MARKS_BRACKET = re.compile(
    r"[\(\[]\s*(\d+(?:\.\d+)?)\s*(?:marks?|mks?|m)?\s*[\)\]]", re.I
)
_MARKS_LABELLED = re.compile(r"\bmarks?\s*[:\-]\s*(\d+(?:\.\d+)?)", re.I)
_MARKS_TRAILING = re.compile(r"[-–:\s]\s*(\d+(?:\.\d+)?)\s*marks?\s*$", re.I)
_MARKS_BARE_TRAIL = re.compile(r"(?:\.{2,}|\t+|\s{3,})\s*(\d+(?:\.\d+)?)\s*$")
# "Defines break as exiting the loop - 3". Only ever applied to lines already
# identified as criteria, because on a question line a trailing "- 2" is as
# likely to be part of the question as a mark value.
_MARKS_DASH_TRAIL = re.compile(r"\s[-–:]\s*(\d+(?:\.\d+)?)\s*$")

# "Q1.", "Q 2)", "Question 3 -"
_Q_EXPLICIT = re.compile(
    r"^\s*(?:Q(?:ue?s(?:tion)?)?)\s*\.?\s*(\d{1,2})\s*([a-dA-D])?\s*[).:\-]?\s+(.*)$",
    re.I,
)
# "1. Explain ... (5 marks)" - only treated as a question when it carries marks
_Q_NUMBERED = re.compile(r"^\s*(\d{1,2})\s*([a-dA-D])?\s*[).]\s+(.+)$")

# Criteria
_BULLET = re.compile(r"^\s*(?:[-*•·●▪]|o\s)\s*(.+)$")
_LETTERED = re.compile(r"^\s*\(?([a-z]|[ivx]{1,4})[).]\s+(.+)$", re.I)
_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")

_ANSWER_KEY = re.compile(
    r"^\s*(?:answer\s*key|model\s*answer|expected\s*answer|ideal\s*answer|"
    r"solution|answer)\s*[:\-]\s*(.*)$",
    re.I,
)

_META = re.compile(
    r"^\s*(subject\s*code|subject|course\s*code|course|code|term|semester|"
    r"session|title|exam|examination|paper|class|total\s*marks|duration|time)"
    r"\s*[:\-]\s*(.+)$",
    re.I,
)

# Table header cells, so "| Criterion | Marks |" is not read as a criterion
# called "Criterion" worth nothing.
_HEADER_WORDS = {
    "criterion", "criteria", "description", "marking", "marking scheme",
    "marks", "mark", "points", "score", "weightage", "weight", "max marks",
    "maximum marks", "particulars", "details", "sl no", "sr no", "s no", "no",
    "question", "questions", "q no", "answer", "remarks",
}

_NOISE = re.compile(
    r"^\s*(?:page\s+\d+|\d+\s*/\s*\d+|-+\s*\d+\s*-+|"
    r"(?:university|college|department|institute)\b.*)$",
    re.I,
)


class RubricImportError(ValueError):
    """The document could not be turned into a paper. Message is user-facing."""


@dataclass
class ParsedPaper:
    seed: dict
    strategy: str  # "local" | "gemini"
    warnings: list[str] = field(default_factory=list)
    # Lines the parser could not place. Shown to the examiner so that a
    # criterion silently dropped on the floor is visible rather than simply
    # absent from a rubric that otherwise looks complete.
    unplaced_lines: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _marks_in(line: str, *, allow_dash: bool = False) -> tuple[float | None, str]:
    """Pull a mark value out of a line, returning it and the line without it.

    `allow_dash` adds the bare "... - 3" form. It is off by default because a
    question's own text ends in a number often enough ("Explain Figure - 2")
    that applying it everywhere would silently rewrite questions.
    """
    patterns = [_MARKS_LABELLED, _MARKS_TRAILING, _MARKS_BARE_TRAIL, _MARKS_BRACKET]
    if allow_dash:
        patterns.insert(3, _MARKS_DASH_TRAIL)
    for pattern in patterns:
        match = pattern.search(line)
        if match:
            try:
                value = float(match.group(1))
            except ValueError:  # pragma: no cover - the group is always numeric
                continue
            # A bracketed number is only a mark if it is plausible as one. "(2)"
            # in "step (2) of the algorithm" is not, and neither is "(1995)".
            if 0 < value <= 100:
                cleaned = (line[: match.start()] + " " + line[match.end() :]).strip()
                return value, _strip_tail(cleaned)
    return None, _strip_tail(line)


def _strip_tail(text: str) -> str:
    return re.sub(r"[\s.:;,\-–]+$", "", text).strip()


def _is_header_cell(text: str) -> bool:
    return _strip_tail(text).strip().lower() in _HEADER_WORDS


def _cells(line: str) -> list[str] | None:
    match = _TABLE_ROW.match(line)
    if not match:
        return None
    return [cell.strip() for cell in match.group(1).split("|")]


def _looks_like_noise(line: str) -> bool:
    return bool(_NOISE.match(line)) or len(line.strip()) <= 2


# ---------------------------------------------------------------------------
# The local parser
# ---------------------------------------------------------------------------


@dataclass
class _Draft:
    number: str
    text: str
    max_marks: float | None = None
    criteria: list[dict] = field(default_factory=list)
    answer_key: list[str] = field(default_factory=list)
    collecting_key: bool = False


def _start_question(line: str, *, allow_bare_numbers: bool = True) -> _Draft | None:
    """A question header, or None.

    Two shapes count. "Q1." and "Question 1" are unambiguous. A bare "1." is
    not - it is equally the first criterion under the question above it - so
    it only counts when the line carries a mark value *and* the document does
    not number its questions with a Q prefix somewhere else.

    That second condition is what `allow_bare_numbers` carries. A paper
    written as

        Q1. Explain pointers. (4 marks)
        1. Defines a pointer as an address (2)
        2. Gives a declaration example (2)

    has four marks of criteria under one question, not three questions; the
    document already showed which convention it uses for questions, so the
    numbered lines must be something else.
    """
    match = _Q_EXPLICIT.match(line)
    if match:
        number, part, rest = match.group(1), match.group(2) or "", match.group(3)
        marks, text = _marks_in(rest)
        return _Draft(number=f"Q{number}{part}", text=text.strip(), max_marks=marks)

    if not allow_bare_numbers:
        return None

    match = _Q_NUMBERED.match(line)
    if match:
        rest = match.group(3)
        marks, text = _marks_in(rest)
        if marks is not None and len(text.split()) >= 3:
            number, part = match.group(1), match.group(2) or ""
            return _Draft(number=f"Q{number}{part}", text=text.strip(), max_marks=marks)
    return None


def _criterion_from(line: str) -> tuple[str, float | None] | None:
    """A criterion line reduced to its text and its marks, or None."""
    cells = _cells(line)
    if cells is not None:
        meaningful = [c for c in cells if c]
        if not meaningful or all(_is_header_cell(c) for c in meaningful):
            return None
        marks: float | None = None
        # The marks column is the rightmost cell that is just a number.
        for index in range(len(cells) - 1, -1, -1):
            cell = cells[index].strip()
            if re.fullmatch(r"\d+(?:\.\d+)?", cell):
                marks = float(cell)
                cells = cells[:index] + cells[index + 1 :]
                break
        # Drop a leading serial-number column: "| 1 | Defines ... | 2 |".
        if cells and re.fullmatch(r"\d{1,2}[.)]?", cells[0].strip()):
            cells = cells[1:]
        text = " - ".join(c for c in cells if c).strip()
        if not text:
            return None
        if marks is None:
            marks, text = _marks_in(text, allow_dash=True)
        return _strip_tail(text), marks

    match = _BULLET.match(line)
    if match:
        marks, text = _marks_in(match.group(1), allow_dash=True)
        return text, marks

    match = _LETTERED.match(line)
    if match:
        marks, text = _marks_in(match.group(2), allow_dash=True)
        return text, marks

    # An unprefixed line that nonetheless ends in a mark value - the "dot
    # leader" style: "Defines the term correctly ............ 2"
    marks, text = _marks_in(line)
    if marks is not None and text and len(text.split()) >= 2:
        return text, marks
    return None


def parse_locally(text: str) -> ParsedPaper:
    """Find questions, criteria and marks with regular expressions only."""
    lines = text.splitlines()
    meta: dict[str, str] = {}
    drafts: list[_Draft] = []
    unplaced: list[str] = []
    warnings: list[str] = []
    current: _Draft | None = None

    # Decided once for the whole document, before parsing anything: a paper
    # that writes "Q1" anywhere is telling us that bare numbers are criteria.
    uses_q_prefix = any(_Q_EXPLICIT.match(line) for line in lines)

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            if current:
                current.collecting_key = False
            continue
        if _looks_like_noise(line):
            continue

        started = _start_question(line, allow_bare_numbers=not uses_q_prefix)
        if started:
            drafts.append(started)
            current = started
            continue

        if current is None:
            match = _META.match(line)
            if match:
                meta[match.group(1).strip().lower()] = match.group(2).strip()
            else:
                unplaced.append(line.strip())
            continue

        key = _ANSWER_KEY.match(line)
        if key:
            current.collecting_key = True
            if key.group(1).strip():
                current.answer_key.append(key.group(1).strip())
            continue

        criterion = _criterion_from(line)
        if criterion and not current.collecting_key:
            description, marks = criterion
            if len(description) >= 3:
                current.criteria.append(
                    {
                        "position": len(current.criteria) + 1,
                        "description": description[:1000],
                        "max_marks": marks,
                    }
                )
                continue

        if current.collecting_key:
            current.answer_key.append(line.strip())
            continue

        # A table row that was not a criterion is the table's header. It is
        # never part of the question: appending it would turn "Define a stack"
        # into "Define a stack | Sr No | Criterion | Marks |".
        if _cells(line) is not None:
            continue

        # A continuation of the question text, as long as the question is
        # still short enough that this is plausibly its second line.
        if len(current.text) < 400 and not current.criteria:
            current.text = (current.text + " " + line.strip()).strip()
        else:
            unplaced.append(line.strip())

    if not drafts:
        raise RubricImportError(
            "No questions were recognised in that document. The importer looks "
            "for lines beginning 'Q1', 'Question 1' or '1.' followed by a mark "
            "value such as '(5 marks)'. Check the file, or add the questions by "
            "hand in the rubric editor."
        )

    questions = [_finish(draft, warnings) for draft in drafts]
    return ParsedPaper(
        seed=_seed(meta, questions, text),
        strategy="local",
        warnings=warnings,
        unplaced_lines=unplaced[:40],
    )


def _finish(draft: _Draft, warnings: list[str]) -> dict:
    """Resolve one question's marks against its criteria."""
    criteria = [c for c in draft.criteria if c["description"]]

    # Criteria with no mark of their own share whatever the question has left.
    known = [c for c in criteria if c["max_marks"] is not None]
    unknown = [c for c in criteria if c["max_marks"] is None]
    total_known = sum(float(c["max_marks"]) for c in known)

    if unknown:
        if draft.max_marks is not None and draft.max_marks > total_known:
            remaining = draft.max_marks - total_known
            share = round(remaining / len(unknown), 2)
            for criterion in unknown:
                criterion["max_marks"] = share
            # Three criteria sharing 7 marks give 2.33 each, which sums to
            # 6.99 and would raise a sum-mismatch warning about a split this
            # function just made. The last one absorbs the rounding error.
            unknown[-1]["max_marks"] = round(
                remaining - share * (len(unknown) - 1), 2
            )
            warnings.append(
                f"{draft.number}: {len(unknown)} criterion/criteria had no mark "
                f"value, so the question's remaining {draft.max_marks - total_known:g} "
                f"marks were split evenly between them. Check that split."
            )
        else:
            for criterion in unknown:
                criterion["max_marks"] = 1.0
            warnings.append(
                f"{draft.number}: {len(unknown)} criterion/criteria had no mark "
                f"value and the question's total was unknown, so each was given "
                f"1 mark. These need setting before marking."
            )

    total = sum(float(c["max_marks"]) for c in criteria)

    if draft.max_marks is None:
        max_marks = total if criteria else 1.0
        if not criteria:
            warnings.append(
                f"{draft.number}: no marks found for this question, so it was "
                f"given 1. Set it in the editor."
            )
    else:
        max_marks = draft.max_marks
        if criteria and abs(total - max_marks) > MARK_TOLERANCE:
            warnings.append(
                f"{draft.number}: the criteria sum to {total:g} but the question "
                f"is marked out of {max_marks:g}. Imported as found - fix it in "
                f"the rubric editor before marking, or the rubric is rejected."
            )

    entry: dict = {
        "number": draft.number,
        "text": draft.text or f"Question {draft.number}",
        "question_type": "theory",
        "max_marks": round(float(max_marks), 2),
    }
    if draft.answer_key:
        entry["answer_key"] = " ".join(draft.answer_key).strip()
    if criteria:
        entry["criteria"] = [
            {
                "position": index,
                "description": criterion["description"],
                "max_marks": round(float(criterion["max_marks"]), 2),
                # Left empty on purpose. The marker reads the description as
                # the meaning of the criterion when no concepts are given, and
                # concepts invented by a parser would be worse than none.
                "essential_concepts": [],
                "acceptable_alternatives": [],
                "common_mistakes": [],
                "allows_partial": True,
            }
            for index, criterion in enumerate(criteria, start=1)
        ]
    return entry


def _seed(meta: dict[str, str], questions: list[dict], text: str) -> dict:
    title = (
        meta.get("title")
        or meta.get("exam")
        or meta.get("examination")
        or meta.get("paper")
        or _first_line(text)
        or "Imported paper"
    )
    subject = (
        meta.get("subject") or meta.get("course") or meta.get("class") or "Unspecified"
    )
    code = meta.get("subject code") or meta.get("course code") or meta.get("code")
    term = meta.get("term") or meta.get("semester") or meta.get("session")

    exam: dict = {
        "title": title[:200],
        "subject": subject[:120],
        "total_marks": round(sum(float(q["max_marks"]) for q in questions), 2),
    }
    if code:
        exam["code"] = code[:60]
    if term:
        exam["term"] = term[:60]

    return {
        "exam": exam,
        "questions": questions,
        "scoring_rules": {
            "spelling_penalised": False,
            "indentation_penalised": False,
            "partial_credit": True,
            "round_to": 0.5,
        },
    }


def _first_line(text: str) -> str | None:
    """The document's own heading, used as a title when it declares none.

    Metadata lines are skipped: "Subject: Physics" is where the subject comes
    from, and using it as the title as well reads as a parsing mistake to
    anyone looking at the imported paper.
    """
    for line in text.splitlines():
        stripped = line.strip()
        # A heading appears before the first question, by definition. Reading
        # past that point finds criteria and uses one of them as the title.
        if _start_question(stripped):
            return None
        if len(stripped) < 8 or _looks_like_noise(stripped):
            continue
        if _META.match(stripped) or _cells(stripped) or _criterion_from(stripped):
            continue
        return stripped
    return None


# ---------------------------------------------------------------------------
# The Gemini parser
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are reading an examination paper with its marking \
scheme. Convert it into JSON.

Rules you must follow:
- Copy the question text and every criterion from the document. Do not invent \
criteria, do not merge two criteria into one, and do not reword a criterion \
beyond removing numbering and trailing dots.
- A criterion's "max_marks" is what the document allots it. The criteria of a \
question must sum to that question's "max_marks". If the document is \
inconsistent, keep what the document says and do not silently rebalance it.
- "answer_key" is the model or expected answer if the document gives one, \
otherwise omit it.
- Leave "essential_concepts" empty unless the document itself lists key \
points or keywords for that criterion.
- Keep the document's own question numbering in "number" (for example "Q1", \
"Q2a").

Return ONLY a JSON object of this exact shape, with no commentary and no code \
fence:

{
  "exam": {"title": "...", "subject": "...", "code": "...", "term": "...", \
"total_marks": 30},
  "questions": [
    {
      "number": "Q1",
      "text": "the full question as written",
      "topic": "short topic label",
      "question_type": "theory",
      "max_marks": 5,
      "answer_key": "the expected answer, if the document gives one",
      "criteria": [
        {
          "position": 1,
          "description": "what the marker looks for",
          "max_marks": 2,
          "essential_concepts": [],
          "acceptable_alternatives": [],
          "common_mistakes": [],
          "allows_partial": true
        }
      ]
    }
  ]
}

The document follows.

"""


def _strip_fence(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        return fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


def parse_with_gemini(text: str, *, timeout: float | None = None) -> ParsedPaper:
    """Ask the cloud model to structure the document.

    The result is normalised through `parse_locally`'s own finishing logic for
    marks, so a paper imported this way carries the same warnings about sums
    not adding up as one imported locally.
    """
    from app.core.config import settings
    from app.providers.gemini_rest import (
        SERVED_BY,
        GeminiRequestError,
        first_text,
        generate,
    )

    if not settings.gemini_api_key:
        raise RubricImportError(
            "Reading a document with Gemini needs an API key. Set "
            "EVALNOVA_GEMINI_API_KEY in the .env file, or import with the "
            "local parser instead."
        )

    # Very long papers are truncated rather than rejected: the questions are at
    # the front, and a partial paper the examiner can extend beats a refusal.
    excerpt = text[:60_000]
    truncated = len(text) > len(excerpt)

    body = {
        "contents": [{"role": "user", "parts": [{"text": EXTRACTION_PROMPT + excerpt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
            # A paper of thirty criteria is a long reply, and a truncated one
            # parses as invalid JSON rather than as a short paper.
            "maxOutputTokens": 16384,
        },
    }

    try:
        reply = generate(
            api_key=settings.gemini_api_key,
            model=settings.evaluation_model_chain,
            body=body,
            timeout_seconds=timeout or settings.gemini_timeout_seconds,
        )
        raw = first_text(reply)
        model_used = reply.get(SERVED_BY) or settings.evaluation_model_chain[0]
    except GeminiRequestError as exc:
        raise RubricImportError(
            f"Gemini could not read that document: {exc}"
        ) from exc

    try:
        document = json.loads(_strip_fence(raw))
    except json.JSONDecodeError as exc:
        raise RubricImportError(
            "Gemini's reply was not valid JSON, so the paper could not be "
            "built from it. Try the local parser."
        ) from exc

    if not isinstance(document, dict) or not isinstance(document.get("questions"), list):
        raise RubricImportError(
            "Gemini did not find any questions in that document."
        )

    warnings: list[str] = []
    if truncated:
        warnings.append(
            "The document was longer than the importer reads in one pass; only "
            "the first part was processed. Check that no questions are missing."
        )
    warnings.append(
        f"Read by {model_used}. Every question and criterion below is a "
        f"proposal - check it against the original before saving."
    )

    seed = _normalise_model_output(document, warnings)
    return ParsedPaper(seed=seed, strategy="gemini", warnings=warnings)


def _normalise_model_output(document: dict, warnings: list[str]) -> dict:
    """Force the model's reply into the seed shape, dropping what is unusable."""
    questions: list[dict] = []

    for index, entry in enumerate(document.get("questions") or [], start=1):
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue

        draft = _Draft(
            number=str(entry.get("number") or f"Q{index}").strip()[:16],
            text=text[:4000],
        )
        try:
            draft.max_marks = float(entry.get("max_marks"))
        except (TypeError, ValueError):
            draft.max_marks = None

        for position, criterion in enumerate(entry.get("criteria") or [], start=1):
            if not isinstance(criterion, dict):
                continue
            description = str(criterion.get("description") or "").strip()
            if len(description) < 3:
                continue
            try:
                marks = float(criterion.get("max_marks"))
            except (TypeError, ValueError):
                marks = None
            draft.criteria.append(
                {
                    "position": position,
                    "description": description[:1000],
                    "max_marks": marks,
                }
            )

        finished = _finish(draft, warnings)

        topic = str(entry.get("topic") or "").strip()
        if topic:
            finished["topic"] = topic[:120]
        key = str(entry.get("answer_key") or "").strip()
        if key:
            finished["answer_key"] = key[:8000]

        # Concepts are kept only when the model actually produced them, and
        # only as strings - the rubric editor is where they get curated.
        for source, target in zip(entry.get("criteria") or [], finished.get("criteria") or []):
            if not isinstance(source, dict):
                continue
            for field_name in (
                "essential_concepts",
                "acceptable_alternatives",
                "common_mistakes",
            ):
                values = source.get(field_name)
                if isinstance(values, list):
                    target[field_name] = [
                        str(v).strip()[:300] for v in values if str(v).strip()
                    ][:12]
            if isinstance(source.get("allows_partial"), bool):
                target["allows_partial"] = source["allows_partial"]

        questions.append(finished)

    if not questions:
        raise RubricImportError(
            "Gemini returned no usable questions for that document."
        )

    meta_in = document.get("exam") or {}
    meta = {
        "title": str(meta_in.get("title") or "Imported paper"),
        "subject": str(meta_in.get("subject") or "Unspecified"),
    }
    if meta_in.get("code"):
        meta["code"] = str(meta_in["code"])
    if meta_in.get("term"):
        meta["term"] = str(meta_in["term"])

    return _seed(
        {
            "title": meta["title"],
            "subject": meta["subject"],
            **({"code": meta["code"]} if "code" in meta else {}),
            **({"term": meta["term"]} if "term" in meta else {}),
        },
        questions,
        meta["title"],
    )


def parse(text: str, *, engine: str | None = None) -> ParsedPaper:
    """Parse with the requested engine, falling back to the local parser.

    Gemini failing is not a reason to hand back nothing: the regular
    expressions usually still find the questions, and a rough paper in the
    editor is a better place to start from than an error message.
    """
    from app.providers.ocr.registry import GEMINI, normalise

    if normalise(engine) == GEMINI:
        try:
            return parse_with_gemini(text)
        except RubricImportError as exc:
            logger.warning("Gemini import failed (%s); falling back locally", exc)
            parsed = parse_locally(text)
            parsed.warnings.insert(
                0,
                f"Gemini could not read this document ({exc}). These questions "
                f"were found by the local parser instead, which is stricter "
                f"about layout - check for anything missing.",
            )
            return parsed
    return parse_locally(text)
