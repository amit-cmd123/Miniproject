"""Chooses which marker the application uses.

Mirrors the OCR registry: the rest of the codebase asks for
`get_evaluation_provider()` and receives *an* `EvaluationProvider`. Which one
is a configuration decision, made here and nowhere else.

Unlike recognition, marking does **not** silently fall back. If the configured
marker cannot run, the request fails with a message saying why. A fallback
here would quietly replace a language model's judgement with keyword counting
and still return a confident-looking score - the one failure this system
exists to prevent.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import settings
from app.providers.evaluation.base import EvaluationProvider
from app.providers.evaluation.mock_evaluator import MockEvaluationProvider

logger = logging.getLogger(__name__)


@lru_cache
def get_evaluation_provider() -> EvaluationProvider:
    name = (settings.evaluation_provider or "mock").lower()

    if name == "mock":
        return MockEvaluationProvider()

    if name == "gemini":
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
        f"Unknown evaluation provider '{settings.evaluation_provider}'. "
        "Use 'gemini' or 'mock'."
    )


def reset_evaluation_cache() -> None:
    """Used by tests that switch markers between cases."""
    get_evaluation_provider.cache_clear()
