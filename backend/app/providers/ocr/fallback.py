"""A cloud engine with a local engine behind it.

A demonstration that depends on the network needs a plan for when the network
is not there. This wraps a page-level primary (Gemini) and a line-level
secondary (TrOCR): the primary reads every page it can, and a page it cannot
read is handed to the secondary instead of failing - with a warning on the
result saying so, and the secondary recorded as the engine that produced it.

The secondary is not loaded until it is first needed, so a session where the
cloud never fails never pays for loading local weights.
"""

from __future__ import annotations

import logging
from typing import Callable

from app.providers.ocr.base import OCRProvider, ProviderInfo, RecognitionResult

logger = logging.getLogger(__name__)


class FallbackOCRProvider(OCRProvider):
    reads_full_page = True

    def __init__(
        self, primary: OCRProvider, make_secondary: Callable[[], OCRProvider]
    ) -> None:
        self._primary = primary
        self._make_secondary = make_secondary
        self._secondary: OCRProvider | None = None
        self.name = primary.name
        self.is_mock = primary.is_mock

    def _fallback(self) -> OCRProvider:
        if self._secondary is None:
            self._secondary = self._make_secondary()
        return self._secondary

    def recognise(self, line_images, boxes) -> RecognitionResult:
        return self._fallback().recognise(line_images, boxes)

    def recognise_page(self, page, line_images, boxes) -> RecognitionResult:
        try:
            return self._primary.recognise_page(page, line_images, boxes)
        except Exception as exc:
            logger.warning("%s failed, reading locally instead: %s", self._primary.name, exc)
            secondary = self._fallback()
            result = secondary.recognise_page(page, line_images, boxes)
            result.engine = result.engine or secondary.info()
            result.warnings.insert(
                0,
                f"Cloud recognition was unavailable ({exc}). This page was read "
                "by the local engine instead, which is less accurate.",
            )
            return result

    def warmup(self) -> None:
        self._primary.warmup()

    def info(self) -> ProviderInfo:
        return self._primary.info()
