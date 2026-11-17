"""Splitting a booklet's transcription into per-question answers.

A scanned booklet is read page by page, but it is marked question by question,
and the two do not line up: one answer can run across a page break and one
page can hold the end of Q3 and the start of Q4. Something has to decide which
words belong to which question before any rubric can be applied.

Two strategies, in this order:

1. **Markers.** Students number their answers. A line beginning `Q3`, `3)`,
   `Ans 3` or `Question 3` is a boundary, and finding them is exact, free,
   instant and verifiable - the located position can be shown to a human. This
   handles the overwhelming majority of real booklets.

2. **A model**, only when markers fail. Numbering can be missing, misread by
   the transcriber, or written in a margin the page segmentation dropped. Then
   the numbered transcription is handed to a text model, which returns line
   ranges per question.

Strategy 1 is tried first on purpose. Reaching for a model to do work that a
regular expression does exactly is how a system becomes slow, expensive and
unexplainable, and the fallback is recorded on every segment so a reader can
see which one was used.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

PROMPT_VERSION = "split-booklet-v1"

# Markers that name a question unambiguously: "Q3", "Q.3", "Ans 3",
# "Answer 3:", "Question 3". A line starting like this is an answer boundary
# and almost nothing else.
EXPLICIT_PATTERNS = (
    re.compile(r"^\s*(?:question|ques|ans(?:wer)?)\s*[.\-:)]?\s*(\d{1,2})\b", re.I),
    re.compile(r"^\s*q\s*[.\-:]?\s*(\d{1,2})\b", re.I),
)

# A bare leading number: "3)", "3.", "(3)". Also how every numbered list
# inside an answer begins, so these are only trusted when nothing better
# exists on the page.
BARE_PATTERNS = (
    re.compile(r"^\s*\(?(\d{1,2})\s*[.)\-:]\s+"),
    re.compile(r"^\s*\(?(\d{1,2})\s*[.)]\s*$"),
)

MARKER_PATTERNS = EXPLICIT_PATTERNS + BARE_PATTERNS


@dataclass
class Boundary:
    """A detected answer boundary."""

    line_index: int
    question_number: int
    located_by: str
    # The line that announced it, for showing a human where the split was made.
    marker_line: str = ""


@dataclass
class SplitResult:
    boundaries: list[Boundary] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    method: str = "marker"


def find_markers(lines: list[str], valid_numbers: set[int]) -> list[Boundary]:
    """Locate answer markers in a transcribed booklet.

    The hard case is a numbered list *inside* an answer. A student answering
    Q4 writes:

        Q4
        1. declare the variables
        2. loop from 2 to n
        3. print the result
        Q5

    and "1.", "2.", "3." are indistinguishable from answer markers by shape
    alone. Simply keeping the longest ascending run of numbers picks
    1, 2, 3, 5 over the correct 4, 5 - the list is longer than the truth.

    So explicit markers win. A line beginning "Q4" or "Ans 4" names its
    question and is trusted; a bare "4." is only consulted when the page has
    no explicit markers to go on, which is the case where it is the best
    evidence available. Within whichever set is used, the numbers must still
    ascend, because a booklet is answered in order.
    """
    explicit: list[Boundary] = []
    bare: list[Boundary] = []

    for index, line in enumerate(lines):
        for pattern in MARKER_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            number = int(match.group(1))
            if number not in valid_numbers:
                break
            boundary = Boundary(
                line_index=index,
                question_number=number,
                located_by="marker",
                marker_line=line.strip()[:120],
            )
            (explicit if pattern in EXPLICIT_PATTERNS else bare).append(boundary)
            break

    # Explicit markers are evidence; bare numbers are a guess. One explicit
    # marker alone could be a stray, so two are required before the bare ones
    # are discarded.
    candidates = explicit if len({b.question_number for b in explicit}) >= 2 else (
        explicit + bare
    )
    candidates.sort(key=lambda b: b.line_index)
    return _longest_ascending_run(candidates)


def _longest_ascending_run(found: list[Boundary]) -> list[Boundary]:
    """The longest run of strictly ascending question numbers, earliest first.

    A marker that goes backwards is a sub-part or a list item, not a new
    answer, so it is dropped rather than treated as a boundary.
    """
    best: list[Boundary] = []
    for start in range(len(found)):
        run: list[Boundary] = []
        last = 0
        for candidate in found[start:]:
            if candidate.question_number > last:
                run.append(candidate)
                last = candidate.question_number
        if len(run) > len(best):
            best = run
    return best


def split_by_markers(
    lines: list[str], valid_numbers: set[int]
) -> tuple[dict[int, tuple[int, int]], SplitResult]:
    """Line ranges per question number, from markers alone.

    Returns `{question_number: (start_line, end_line_exclusive)}`. The marker
    line itself is included: students often write the answer on the same line
    as the number.
    """
    boundaries = find_markers(lines, valid_numbers)
    result = SplitResult(boundaries=boundaries, method="marker")

    if not boundaries:
        result.warnings.append(
            "No answer numbering was found in the transcription, so the "
            "booklet could not be split by markers."
        )
        return {}, result

    ranges: dict[int, tuple[int, int]] = {}
    for position, boundary in enumerate(boundaries):
        end = (
            boundaries[position + 1].line_index
            if position + 1 < len(boundaries)
            else len(lines)
        )
        ranges[boundary.question_number] = (boundary.line_index, end)

    missing = sorted(valid_numbers - set(ranges))
    if missing:
        result.warnings.append(
            "No answer marker was found for question(s) "
            + ", ".join(str(n) for n in missing)
            + ". They were either not attempted or not numbered."
        )
    return ranges, result


# ---------------------------------------------------------------------------
# Model fallback
# ---------------------------------------------------------------------------

SPLIT_INSTRUCTIONS = """You are given the automatic transcription of a handwritten examination answer booklet, with every line numbered, and the list of questions on the paper.

Decide which lines belong to which question's answer.

Rules:
- Work only from the transcription. Do not write, complete or improve any answer.
- An answer may run over many lines and may continue after a page break.
- A question the student did not attempt gets no range at all. Leave it out rather than guessing.
- Lines that belong to no answer - the student's name, a roll number, a page header, scribbles - are left out of every range.
- Ranges must not overlap, and must use the line numbers exactly as given.
- Judge by content: match what the lines are about against what each question asks for.

Return, for each question that was attempted, its number and the first and last line of its answer."""

SPLIT_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_number": {"type": "integer"},
                    "first_line": {"type": "integer"},
                    "last_line": {"type": "integer"},
                },
                "required": ["question_number", "first_line", "last_line"],
            },
        }
    },
    "required": ["answers"],
}


def build_split_prompt(lines: list[str], questions: list[tuple[int, str]]) -> str:
    parts = ["QUESTIONS ON THE PAPER"]
    for number, text in questions:
        parts.append(f"{number}. {text.strip()[:400]}")
    parts.append("")
    parts.append("TRANSCRIBED BOOKLET")
    for index, line in enumerate(lines):
        parts.append(f"{index}: {line}")
    parts.append("")
    parts.append("Return the line range of each question that was attempted.")
    return "\n".join(parts)


def parse_split(text: str, line_count: int, valid: set[int]) -> dict[int, tuple[int, int]]:
    """Line ranges from the model's reply, with every range sanity-checked."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]

    payload = json.loads(cleaned)
    ranges: dict[int, tuple[int, int]] = {}

    for entry in payload.get("answers") or []:
        try:
            number = int(entry["question_number"])
            first = int(entry["first_line"])
            last = int(entry["last_line"])
        except (KeyError, TypeError, ValueError):
            continue
        if number not in valid:
            continue
        first = max(0, min(first, line_count - 1))
        last = max(first, min(last, line_count - 1))
        ranges[number] = (first, last + 1)

    return ranges


class GeminiSplitter:
    """Splits a booklet with a Gemini text model. Used only when markers fail."""

    name = "gemini"

    def __init__(
        self,
        api_key: str | None,
        model: str | list[str],
        timeout_seconds: float = 60.0,
    ):
        self._api_key = (api_key or "").strip() or None
        self._chain = [model] if isinstance(model, str) else [m for m in model if m]
        self._model = self._chain[0] if self._chain else ""
        self._timeout = timeout_seconds

    @property
    def is_ready(self) -> bool:
        return bool(self._api_key)

    def split(
        self, lines: list[str], questions: list[tuple[int, str]]
    ) -> tuple[dict[int, tuple[int, int]], SplitResult]:
        from app.providers.gemini_rest import GeminiRequestError, first_text, generate

        result = SplitResult(method="model")
        if not self._api_key:
            result.warnings.append(
                "The booklet could not be split by answer numbering, and no "
                "Gemini key is configured to split it by content."
            )
            return {}, result
        if not lines:
            return {}, result

        valid = {number for number, _ in questions}
        body = {
            "systemInstruction": {"parts": [{"text": SPLIT_INSTRUCTIONS}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": build_split_prompt(lines, questions)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
                "responseSchema": SPLIT_SCHEMA,
            },
        }

        try:
            reply = generate(
                api_key=self._api_key,
                model=self._chain,
                body=body,
                timeout_seconds=self._timeout,
            )
            ranges = parse_split(first_text(reply), len(lines), valid)
        except (GeminiRequestError, json.JSONDecodeError) as exc:
            logger.warning("Model booklet split failed: %s", exc)
            result.warnings.append(f"Splitting the booklet by content failed: {exc}")
            return {}, result

        if not ranges:
            result.warnings.append(
                "The booklet was split by content but no answer could be "
                "located for any question."
            )
        else:
            result.warnings.append(
                "Answer numbering was not found, so the booklet was split by "
                "content using a model. Check the boundaries before accepting "
                "these marks."
            )
        result.boundaries = [
            Boundary(line_index=start, question_number=number, located_by="model")
            for number, (start, _) in sorted(ranges.items())
        ]
        return ranges, result


def get_splitter() -> GeminiSplitter:
    from app.core.config import settings

    return GeminiSplitter(
        api_key=settings.gemini_api_key,
        model=settings.evaluation_model_chain,
        timeout_seconds=settings.gemini_timeout_seconds,
    )
