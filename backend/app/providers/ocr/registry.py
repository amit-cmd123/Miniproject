"""Chooses which recognition engine the application uses.

The rest of the codebase asks for `get_ocr_provider()` and receives *an*
`OCRProvider`. Which one is a configuration decision, made here and nowhere
else.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import settings
from app.providers.ocr.base import OCRProvider
from app.providers.ocr.mock_provider import MockOCRProvider

logger = logging.getLogger(__name__)


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


@lru_cache
def get_ocr_provider() -> OCRProvider:
    name = (settings.ocr_provider or "mock").lower()

    if name == "mock":
        return MockOCRProvider()

    if name == "trocr":
        return _local_provider()

    if name == "gemini":
        from app.providers.ocr.gemini_provider import GeminiOCRProvider

        if not settings.gemini_api_key:
            logger.warning(
                "EVALNOVA_OCR_PROVIDER=gemini but no EVALNOVA_GEMINI_API_KEY is set; "
                "using the local engine"
            )
            return _local_provider()

        gemini = GeminiOCRProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            thinking_level=settings.gemini_thinking_level,
        )
        if not settings.gemini_fallback_to_local:
            return gemini

        from app.providers.ocr.fallback import FallbackOCRProvider

        return FallbackOCRProvider(gemini, _local_provider)

    raise ValueError(
        f"Unknown OCR provider '{settings.ocr_provider}'. Use 'gemini', 'trocr' or 'mock'."
    )


def reset_provider_cache() -> None:
    """Used by tests that switch engines between cases."""
    get_ocr_provider.cache_clear()
