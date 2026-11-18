"""Rubric marking with a Gemini text model.

The model is used for exactly one thing it is good at: deciding whether a
criterion stated in English is satisfied by an answer written in English. It
is used for nothing it is bad at - it never sees a mark value, never adds
anything up, and never decides a total.

Three constraints are built into the request rather than hoped for:

* **A fixed response schema.** The reply is JSON matching a declared schema,
  so parsing cannot drift into prose and a missing verdict is visible rather
  than guessed at.
* **Mark values withheld.** `MarkingTask` arrives without them and the prompt
  never mentions marks, scores or totals, so the model cannot anchor on a
  grade and work backwards.
* **A quotation per verdict.** Every judgement must cite the student's own
  words. The service checks each quotation really occurs in the
  transcription, which turns "did the model make this up?" from a worry into
  a measurement.
"""

from __future__ import annotations

import json
import logging

from app.providers.evaluation.base import (
    CriterionJudgement,
    EvaluationProvider,
    EvaluatorInfo,
    MarkingJudgement,
    MarkingTask,
)
from app.providers.gemini_rest import (
    SERVED_BY,
    GeminiRequestError,
    first_text,
    generate,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "mark-criteria-v1"

INSTRUCTIONS = """You are an experienced university examiner marking one answer from a handwritten examination script.

You are given the question, the model answer, and a numbered list of marking criteria. For EACH criterion you decide whether the student's answer satisfies it.

How to decide:
- Judge only what the student actually wrote. Never credit knowledge the student did not express, and never fill in a step they omitted.
- Credit the idea, not the wording. A correct point made in the student's own words, or by a correct alternative method, is satisfied.
- Ignore spelling, grammar, capitalisation, handwriting and layout unless the criterion is explicitly about them.
- A longer answer is not a better answer. Do not reward fluency, confidence or padding.
- The answer comes from automatic handwriting recognition, so it may contain garbled words. Where the student's intent is clear despite a misread character, credit the intent. Where a passage is genuinely unreadable, do not invent a reading of it - judge the criterion on the rest.
- "[illegible]" and "[diagram]" are markers inserted by the transcriber, not the student's words.

Verdicts:
- "satisfied": the answer contains the point the criterion asks for.
- "partially_satisfied": the answer gestures at the point but is incomplete, imprecise or partly wrong. Set "coverage" to the fraction of the criterion the answer achieves, between 0 and 1.
- "not_satisfied": the point is absent or wrong.
Use "partially_satisfied" only where a criterion is marked as allowing partial credit. Where it does not, choose satisfied or not_satisfied.

For every criterion you must supply "evidence_quote": a short span copied EXACTLY, character for character, from the student's answer that justifies your verdict. Copy it; do not paraphrase, tidy or complete it. If nothing in the answer bears on the criterion, set it to null - do not invent a quotation.

Give "reason" as one short sentence a student could be shown.

Never mention marks, scores, grades, percentages or totals. You are not deciding how much the answer is worth."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "position": {"type": "integer"},
                    "verdict": {
                        "type": "string",
                        "enum": ["satisfied", "partially_satisfied", "not_satisfied"],
                    },
                    "coverage": {"type": "number"},
                    "reason": {"type": "string"},
                    "evidence_quote": {"type": "string", "nullable": True},
                },
                "required": ["position", "verdict", "reason"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["criteria", "summary"],
}


def build_prompt(task: MarkingTask) -> str:
    """Assemble the marking request. No mark values appear anywhere in it."""
    lines: list[str] = []

    lines.append(f"QUESTION {task.question_number} ({task.question_type})")
    lines.append(task.question_text.strip())
    lines.append("")

    if task.answer_key:
        lines.append("MODEL ANSWER (for reference - the student need not match it)")
        lines.append(task.answer_key.strip())
        lines.append("")

    conventions: list[str] = []
    if task.rules.get("spelling_penalised") is False:
        conventions.append("Spelling mistakes are not penalised.")
    if task.rules.get("indentation_penalised") is False:
        conventions.append("Code indentation and formatting are not penalised.")
    if task.rules.get("partial_credit") is False:
        conventions.append("Partial credit is not awarded on this paper.")
    if conventions:
        lines.append("MARKING CONVENTIONS FOR THIS PAPER")
        lines.extend(f"- {c}" for c in conventions)
        lines.append("")

    lines.append("MARKING CRITERIA")
    for criterion in task.criteria:
        lines.append(f"{criterion.position}. {criterion.description}")
        if criterion.essential_concepts:
            lines.append(
                f"   Must convey: {'; '.join(criterion.essential_concepts)}"
            )
        if criterion.acceptable_alternatives:
            lines.append(
                f"   Also acceptable: {'; '.join(criterion.acceptable_alternatives)}"
            )
        if criterion.common_mistakes:
            lines.append(
                f"   Known mistakes to watch for: {'; '.join(criterion.common_mistakes)}"
            )
        lines.append(
            "   Partial credit: "
            + ("allowed" if criterion.allows_partial else "NOT allowed, all or nothing")
        )
    lines.append("")

    lines.append("STUDENT'S ANSWER (automatic transcription of handwriting)")
    lines.append('"""')
    lines.append(task.student_text.strip() or "(the student wrote nothing)")
    lines.append('"""')
    lines.append("")
    lines.append(
        f"Return a verdict for each of the {len(task.criteria)} criteria, "
        "by position."
    )
    return "\n".join(lines)


def parse_judgement(text: str, expected_positions: list[int]) -> MarkingJudgement:
    """Turn the model's JSON into judgements, one per expected criterion.

    A criterion the model omitted becomes `not_satisfied` with a warning, never
    a silent full mark. The failure mode of a missing verdict must be a lost
    mark that a human notices, not an awarded one that nobody does.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GeminiRequestError(
            f"The marker's reply was not valid JSON ({exc}). Nothing was marked."
        ) from exc

    if not isinstance(payload, dict):
        raise GeminiRequestError("The marker's reply was not a JSON object.")

    by_position: dict[int, dict] = {}
    for entry in payload.get("criteria") or []:
        if not isinstance(entry, dict):
            continue
        try:
            by_position[int(entry.get("position"))] = entry
        except (TypeError, ValueError):
            continue

    judgement = MarkingJudgement(summary=str(payload.get("summary") or "").strip())

    for position in expected_positions:
        entry = by_position.get(position)
        if entry is None:
            judgement.criteria.append(
                CriterionJudgement(
                    position=position,
                    verdict="not_satisfied",
                    reason="The marker returned no verdict for this criterion.",
                ).normalised()
            )
            judgement.warnings.append(
                f"Criterion {position} received no verdict and was scored zero. "
                f"An examiner should check it."
            )
            continue

        quote = entry.get("evidence_quote")
        judgement.criteria.append(
            CriterionJudgement(
                position=position,
                verdict=str(entry.get("verdict", "")),
                coverage=float(entry.get("coverage") or 0.0),
                reason=str(entry.get("reason") or ""),
                evidence_quote=str(quote).strip() if quote else None,
            ).normalised()
        )

    extra = set(by_position) - set(expected_positions)
    if extra:
        judgement.warnings.append(
            f"The marker invented criteria not in the rubric ({sorted(extra)}); "
            f"they were discarded."
        )
    return judgement


class GeminiEvaluationProvider(EvaluationProvider):
    name = "gemini"
    is_mock = False

    def __init__(
        self,
        api_key: str | None,
        model: str | list[str] = "gemini-3-flash-preview",
        timeout_seconds: float = 60.0,
        thinking_level: str | None = None,
    ) -> None:
        self._api_key = (api_key or "").strip() or None
        self._chain = [model] if isinstance(model, str) else [m for m in model if m]
        self._model = self._chain[0] if self._chain else ""
        # Which model actually served the last request. Recorded with the
        # evaluation, so a result marked by a fallback model says so.
        self._model_used: str | None = None
        self._timeout = timeout_seconds
        # Marking is reasoning, not transcription, so thinking is left on by
        # default where the model supports it. Switched off for the session
        # the first time the API rejects the field.
        self._thinking_level = thinking_level
        self._thinking_supported = bool(thinking_level)
        self._schema_supported: bool | None = None

    def _body(self, prompt: str, temperature: float, use_schema: bool) -> dict:
        config: dict = {
            "temperature": temperature,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        }
        if use_schema:
            config["responseSchema"] = RESPONSE_SCHEMA
        if self._thinking_supported and self._thinking_level:
            config["thinkingConfig"] = {"thinkingLevel": self._thinking_level}

        return {
            "systemInstruction": {"parts": [{"text": INSTRUCTIONS}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }

    def judge(self, task: MarkingTask, *, temperature: float = 0.0) -> MarkingJudgement:
        if not self._api_key:
            raise GeminiRequestError(
                "No Gemini API key is configured, so answers cannot be marked. "
                "Add EVALNOVA_GEMINI_API_KEY to .env."
            )
        if not task.criteria:
            raise GeminiRequestError(
                "This question has no rubric criteria, so there is nothing to mark against."
            )

        prompt = build_prompt(task)
        positions = [c.position for c in task.criteria]
        use_schema = self._schema_supported is not False

        while True:
            try:
                reply = generate(
                    api_key=self._api_key,
                    model=self._chain,
                    body=self._body(prompt, temperature, use_schema),
                    timeout_seconds=self._timeout,
                )
                self._model_used = reply.get(SERVED_BY) or self._model
                break
            except GeminiRequestError as exc:
                message = str(exc).lower()
                # Shed optional request features the model refuses, rather
                # than failing the whole marking run over a config mismatch.
                if use_schema and ("responseschema" in message or "schema" in message):
                    logger.info("Model %s rejects responseSchema", self._model)
                    self._schema_supported = False
                    use_schema = False
                    continue
                if self._thinking_supported and "thinking" in message:
                    logger.info("Model %s rejects thinkingConfig", self._model)
                    self._thinking_supported = False
                    continue
                raise

        if use_schema:
            self._schema_supported = True
        return parse_judgement(first_text(reply), positions)

    def info(self) -> EvaluatorInfo:
        served = self._model_used or self._model
        if not self._api_key:
            detail = "No Gemini API key set. Add EVALNOVA_GEMINI_API_KEY to .env."
        else:
            detail = (
                f"Rubric marking with {served}. The question, rubric and "
                "transcribed answer are sent to Google; mark values are not."
            )
            if self._model_used and self._model_used != self._model:
                detail += (
                    f" The preferred model ({self._model}) was unavailable, so "
                    f"{served} was used instead."
                )
        return EvaluatorInfo(
            name=self.name,
            model_name=served,
            model_version=served,
            prompt_version=PROMPT_VERSION,
            is_ready=bool(self._api_key),
            is_mock=False,
            detail=detail,
        )
