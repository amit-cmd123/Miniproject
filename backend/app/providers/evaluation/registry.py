"""Chooses which marker the application uses.

Mirrors the OCR registry: the rest of the codebase asks for
`get_evaluation_provider()` and receives *an* `EvaluationProvider`. Which one
is a configuration decision, made here and nowhere else.

Unlike recognition, marking does **not** silently fall back. If the configured
marker cannot run, the request fails with a message saying why. A fallback
here would quietly replace a language model's judgement with keyword counting
and still return a confident-looking score - the one failure this system
exists to prevent.

That rule is exactly why the local marker has to be *asked for*. With the
Gemini switch off, marking runs on the rubric matcher in
`mock_evaluator.py`: it walks the same criteria, awards the same partial
credit and produces the same evidence quotes, but it decides by concept
overlap rather than by reading. Every score it produces is stamped with its
name and `is_mock`, and the interface says so on the result, so nobody can
mistake the baseline for the model.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import settings
from app.providers.evaluation.base import EvaluationProvider
from app.providers.evaluation.mock_evaluator import MockEvaluationProvider

logger = logging.getLogger(__name__)

LOCAL = "local"
GEMINI = "gemini"
MOCK = "mock"
AUTO = "auto"

# "local" and "mock" are the same marker. Two names because they answer two
# different questions: "what did the offline pipeline score?" and "what does
# the baseline we measure against score?".
_ALIASES = {"keyword": MOCK, LOCAL: MOCK, "offline": MOCK, "": AUTO, "default": AUTO}


class EngineUnavailable(RuntimeError):
    """A specifically requested marker cannot run. The message is shown to a user."""


def normalise(engine: str | None) -> str:
    name = (engine or AUTO).strip().lower()
    return _ALIASES.get(name, name)


@lru_cache
def _build(name: str) -> EvaluationProvider:
    if name == MOCK:
        return MockEvaluationProvider()

    if name == GEMINI:
        from app.providers.evaluation.gemini_evaluator import GeminiEvaluationProvider

        if not settings.gemini_api_key:
            logger.warning(
                "EVALNOVA_EVALUATION_PROVIDER=gemini but no API key is set. "
                "Marking requests will fail with an explanation rather than "
                "falling back to the keyword baseline."
            )
        return GeminiEvaluationProvider(
            api_key=settings.gemini_api_key,
            model=settings.evaluation_model_chain,
            timeout_seconds=settings.gemini_timeout_seconds,
            thinking_level=settings.evaluation_thinking_level,
        )

    raise ValueError(
        f"Unknown evaluation provider '{name}'. Use 'gemini' or 'local'."
    )


def get_evaluation_provider() -> EvaluationProvider:
    name = normalise(settings.evaluation_provider)
    return _build(MOCK if name == AUTO else name)


def get_evaluation_provider_for(engine: str | None) -> EvaluationProvider:
    """The marker this *request* asked for.

    `None` or "auto" means "whatever is configured"; the Gemini switch in the
    interface sends "gemini" or "local" and gets precisely that.
    """
    name = normalise(engine)
    if name == AUTO:
        return get_evaluation_provider()
    if name == GEMINI and not settings.gemini_api_key:
        raise EngineUnavailable(
            "Gemini is switched on but no API key is configured. Set "
            "EVALNOVA_GEMINI_API_KEY in the .env file, or switch Gemini off to "
            "mark against the rubric with the local matcher."
        )
    if name not in (GEMINI, MOCK):
        raise EngineUnavailable(
            f"Unknown engine '{engine}'. Use 'gemini', 'local' or 'auto'."
        )
    return _build(name)


def reset_evaluation_cache() -> None:
    """Used by tests that switch markers between cases."""
    _build.cache_clear()
