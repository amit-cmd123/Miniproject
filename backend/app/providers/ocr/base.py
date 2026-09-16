"""The handwriting-recognition provider boundary.

Nothing above this layer may import torch, transformers, or any vendor SDK.
`OCRService` talks only to this interface, which is what lets the recognition
engine be swapped - for a cloud API, a fine-tuned checkpoint, or the mock -
without touching a single line of application code.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

import numpy as np


@dataclass
class RecognisedLine:
    """One line of handwriting, read."""

    index: int
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]


@dataclass
class ProviderInfo:
    name: str
    model_name: str
    model_version: str
    device: str
    is_ready: bool
    is_mock: bool
    detail: str


@dataclass
class RecognitionResult:
    """What a provider returns for one page."""

    lines: list[RecognisedLine] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # How the line confidences were measured, so a reader of the stored
    # result knows what kind of number it is looking at.
    confidence_method: str = "token_probability"
    # The engine that actually produced this result. Differs from the
    # configured provider when a fallback had to step in.
    engine: ProviderInfo | None = None

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text.strip())


class OCRProvider(abc.ABC):
    """Reads handwriting. Knows nothing about answers, rubrics or marks."""

    name: str = "base"
    is_mock: bool = False
    # Line-level engines (TrOCR) read the crops the service cuts out. A
    # page-level engine (a vision-language model) reads the whole photograph
    # and does its own layout analysis, so it is handed the page instead.
    reads_full_page: bool = False

    @abc.abstractmethod
    def recognise(
        self,
        line_images: list[np.ndarray],
        boxes: list[tuple[int, int, int, int]],
    ) -> RecognitionResult:
        """Transcribe pre-cropped line images, in order."""

    def recognise_page(
        self,
        page: np.ndarray,
        line_images: list[np.ndarray],
        boxes: list[tuple[int, int, int, int]],
    ) -> RecognitionResult:
        """Transcribe a whole page (BGR). Line crops are supplied as well, so
        a page-level engine can hand over to a line-level one if it fails."""
        return self.recognise(line_images, boxes)

    @abc.abstractmethod
    def info(self) -> ProviderInfo:
        """Describe the loaded engine for the UI and for result metadata."""

    def warmup(self) -> None:
        """Optional: load weights ahead of the first request."""
        return None
