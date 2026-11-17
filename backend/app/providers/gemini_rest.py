"""Shared REST transport for the Gemini API.

One place that knows the endpoint, the retry policy and how to turn an HTTP
status into a message worth showing a user. Used by the marking provider; the
recognition provider predates it and carries its own copy, which is left alone
rather than refactored under a deadline.

No vendor SDK: the whole request is visible here, which matters for a project
that has to explain exactly what leaves the machine.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
# Key `generate` adds to a reply naming the model that served it.
SERVED_BY = "_evalnova_served_by"
# Two attempts per model, not more. With a model chain to fall back on, a
# third retry against a model that is plainly overloaded only adds latency to
# a request that is going to be served by a different model anyway.
MAX_ATTEMPTS = 2


class GeminiRequestError(RuntimeError):
    """The request failed in a way retrying will not fix. Message is shown."""


def explain(status: int, message: str, model: str) -> str:
    """Turn an API failure into something a user can act on."""
    if status in (401, 403):
        return (
            f"Google rejected the API key ({status}): {message} "
            "Check EVALNOVA_GEMINI_API_KEY in .env."
        )
    if status == 404:
        return (
            f"Model '{model}' is not available to this key: {message} "
            "Set EVALNOVA_GEMINI_MODEL to a model the key can use - run "
            "scripts/check_gemini.py --list to see them."
        )
    if status == 429:
        return (
            f"Google rate limit or quota reached: {message} "
            "Wait a minute, or mark fewer answers at once."
        )
    return f"The Gemini request failed ({status}): {message}"


def error_message(response) -> str:
    try:
        body = response.json()
        return str(body.get("error", {}).get("message", "")) or response.text[:300]
    except Exception:
        return response.text[:300]


def generate(
    *,
    api_key: str,
    model: str | list[str],
    body: dict,
    timeout_seconds: float,
) -> dict:
    """POST one generateContent request.

    `model` may be a list: the first is preferred and the rest are tried in
    order if it is overloaded, missing or out of quota. That is not
    belt-and-braces - Google returns 503 on popular models routinely, and a
    marking run that fails because one model was busy is worse than one that
    completes on a weaker model and records which model it used.

    A failure that a different model would not fix - a bad key, a malformed
    request - is raised immediately rather than retried down the chain.
    """
    chain = [model] if isinstance(model, str) else [m for m in model if m]
    if not chain:
        raise GeminiRequestError("No Gemini model was configured.")

    last_error: GeminiRequestError | None = None
    for index, candidate in enumerate(chain):
        try:
            reply = _generate_one(
                api_key=api_key,
                model=candidate,
                body=body,
                timeout_seconds=timeout_seconds,
            )
            # Which model actually served the request. Callers record it, so a
            # result produced by a fallback is never reported as the primary's.
            reply[SERVED_BY] = candidate
            return reply
        except GeminiRequestError as exc:
            message = str(exc).lower()
            switchable = any(
                hint in message
                for hint in ("high demand", "unavailable", "not available",
                             "quota", "overload", "did not respond", "reach google")
            )
            if not switchable or index == len(chain) - 1:
                raise
            logger.warning(
                "Model %s is unusable (%s); falling back to %s",
                candidate,
                str(exc)[:120],
                chain[index + 1],
            )
            last_error = exc

    raise last_error or GeminiRequestError("No model could be reached.")


def _generate_one(
    *,
    api_key: str,
    model: str,
    body: dict,
    timeout_seconds: float,
) -> dict:
    """POST one generateContent request, retrying transient failures."""
    import httpx

    url = f"{API_ROOT}/{model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    delay = 2.0

    for attempt in range(MAX_ATTEMPTS):
        last = attempt == MAX_ATTEMPTS - 1
        try:
            response = httpx.post(url, json=body, headers=headers, timeout=timeout_seconds)
        except httpx.HTTPError as exc:
            if last:
                raise GeminiRequestError(f"Could not reach Google: {exc}") from exc
            time.sleep(delay)
            delay *= 2
            continue

        if response.status_code == 200:
            return response.json()

        message = error_message(response)
        if response.status_code in RETRYABLE_STATUS and not last:
            logger.warning(
                "Gemini returned %s (%s); retrying in %.0fs",
                response.status_code,
                message,
                delay,
            )
            time.sleep(delay)
            delay *= 2
            continue
        raise GeminiRequestError(explain(response.status_code, message, model))

    raise GeminiRequestError("Google did not respond.")  # pragma: no cover


def first_text(reply: dict) -> str:
    """The text of the first candidate, with thinking parts discarded."""
    feedback = reply.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise GeminiRequestError(
            f"Google's safety filter refused the request ({feedback['blockReason']})."
        )

    candidates = reply.get("candidates") or []
    if not candidates:
        raise GeminiRequestError("Gemini returned no content.")

    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts if not part.get("thought"))

    finish = candidate.get("finishReason")
    if not text.strip():
        if finish == "MAX_OUTPUT_TOKENS" or finish == "MAX_TOKENS":
            raise GeminiRequestError(
                "Gemini ran out of output budget before answering. "
                "The answer may be unusually long."
            )
        raise GeminiRequestError(
            f"Gemini stopped without producing anything ({finish or 'unknown reason'})."
        )
    return text


def list_models(*, api_key: str, timeout_seconds: float = 30.0) -> list[dict]:
    """Models this key may call, newest-looking first.

    Used by `scripts/check_gemini.py` so the configured model name can be
    checked against reality rather than guessed at.
    """
    import httpx

    response = httpx.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": api_key},
        timeout=timeout_seconds,
    )
    if response.status_code != 200:
        raise GeminiRequestError(
            explain(response.status_code, error_message(response), "(model list)")
        )
    models = response.json().get("models") or []
    return [
        m
        for m in models
        if "generateContent" in (m.get("supportedGenerationMethods") or [])
    ]
