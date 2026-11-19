"""Chooses which recognition engine the application uses.

The rest of the codebase asks for `get_ocr_provider()` and receives *an*
`OCRProvider`. Which one is a configuration decision, made here and nowhere
else.

### Two ways to choose

`get_ocr_provider()` honours `EVALNOVA_OCR_PROVIDER` and is what the
application uses when nobody says otherwise. `get_ocr_provider_for(engine)`
lets a single request override that - the interface has a Gemini switch, and
an examiner turning it off expects *that upload* to be read by the local
model, not the next restart.

An explicit choice is never quietly substituted. Asking for Gemini without a
key raises `EngineUnavailable`; it does not hand back the local model wearing
Gemini's name. The configured default still falls back, because that path is
a deployment preference rather than someone's stated intent.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import settings
from app.providers.ocr.base import OCRProvider
from app.providers.ocr.mock_provider import MockOCRProvider

logger = logging.getLogger(__name__)

# What the interface and the API accept. "local" is the public name for the
# handwriting model we trained and ship; "trocr" is its implementation.
LOCAL = "local"
GEMINI = "gemini"
MOCK = "mock"
AUTO = "auto"

_ALIASES = {"trocr": LOCAL, "offline": LOCAL, "": AUTO, "default": AUTO}


class EngineUnavailable(RuntimeError):
    """A specifically requested engine cannot run. The message is shown to a user."""


def normalise(engine: str | None) -> str:
    name = (engine or AUTO).strip().lower()
    return _ALIASES.get(name, name)


def _local_provider() -> OCRProvider:
    try:
        from app.providers.ocr.trocr_provider import TrOCRProvider

        return TrOCRProvider(
            model_name=settings.ocr_model_name,
            device=settings.ocr_device,
        )
    except ImportError as exc:
        if not settings.ocr_fallback_to_mock:
            raise
        logger.warning(
            "torch/transformers not installed (%s); using the mock engine", exc
        )
        return MockOCRProvider()


def _gemini_provider(*, with_fallback: bool) -> OCRProvider:
    from app.providers.ocr.gemini_provider import GeminiOCRProvider

    chain = settings.gemini_model_chain
    gemini = GeminiOCRProvider(
        api_key=settings.gemini_api_key,
        model=chain[0],
        timeout_seconds=settings.gemini_timeout_seconds,
        thinking_level=settings.gemini_thinking_level,
        confidence_samples=settings.ocr_confidence_samples,
        fallback_models=chain[1:],
    )
    if not with_fallback:
        return gemini

    from app.providers.ocr.fallback import FallbackOCRProvider

    return FallbackOCRProvider(gemini, _local_provider)


@lru_cache
def _build(name: str) -> OCRProvider:
    """One instance per engine name.

    Cached because the local model holds ~1.4 GB of weights: building a second
    TrOCRProvider per request would reload them, and two copies do not fit
    comfortably in memory on the machines this runs on.
    """
    if name == MOCK:
        return MockOCRProvider()
    if name == LOCAL:
        return _local_provider()
    if name == GEMINI:
        return _gemini_provider(with_fallback=settings.gemini_fallback_to_local)
    if name == f"{GEMINI}:strict":
        return _gemini_provider(with_fallback=False)
    raise ValueError(
        f"Unknown OCR provider '{name}'. Use 'gemini', 'local' or 'mock'."
    )


def get_ocr_provider() -> OCRProvider:
    """The configured engine. Falls back to local if Gemini has no key."""
    name = normalise(settings.ocr_provider) or MOCK
    if name == AUTO:
        name = MOCK
    if name == GEMINI and not settings.gemini_api_key:
        logger.warning(
            "EVALNOVA_OCR_PROVIDER=gemini but no EVALNOVA_GEMINI_API_KEY is set; "
            "using the local engine"
        )
        return _build(LOCAL)
    return _build(name)


def get_ocr_provider_for(engine: str | None) -> OCRProvider:
    """The engine this *request* asked for.

    `None` or "auto" means "whatever is configured". Anything else is taken
    literally, including its failure: a request that says Gemini and gets the
    local model back would make the comparison the switch exists to offer
    meaningless.
    """
    name = normalise(engine)
    if name == AUTO:
        return get_ocr_provider()
    if name == GEMINI:
        if not settings.gemini_api_key:
            raise EngineUnavailable(
                "Gemini is switched on but no API key is configured. Set "
                "EVALNOVA_GEMINI_API_KEY in the .env file, or switch Gemini off "
                "to read this page with the local handwriting model."
            )
        # An explicit request is strict: no silent substitution, because the
        # result is labelled with the engine that produced it.
        return _build(f"{GEMINI}:strict")
    if name in (LOCAL, MOCK):
        return _build(name)
    raise EngineUnavailable(
        f"Unknown engine '{engine}'. Use 'gemini', 'local' or 'auto'."
    )


def reset_provider_cache() -> None:
    """Used by tests that switch engines between cases."""
    _build.cache_clear()
