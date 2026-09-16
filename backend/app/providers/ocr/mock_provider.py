"""A deterministic stand-in for handwriting recognition.

This is not a toy. It exists so that:

  * Parts 2, 3 and 4 can develop and run tests without a 1.4 GB model download,
  * CI has something fast and offline to run against,
  * and a demonstration can proceed even if the real engine is unavailable.

It produces plausible, *stable* output for a given image - the same page always
yields the same text - so tests can assert on it.
"""

from __future__ import annotations

import hashlib

import numpy as np

from app.providers.ocr.base import (
    OCRProvider,
    ProviderInfo,
    RecognisedLine,
    RecognitionResult,
)

# A short passage on polymorphism: the worked example from the product
# reference, so a mock run still demonstrates the full evaluation story.
_SAMPLE_LINES = [
    "Polymorphism means that one interface can take many forms.",
    "In object oriented programming, a single reference of a base",
    "class can point to objects of different derived classes.",
    "It is mainly of two types: compile time polymorphism which is",
    "achieved by method overloading, and run time polymorphism",
    "which is achieved by method overriding.",
    "For example, a Shape class may declare a draw() method and",
    "Circle and Square override it with their own implementation.",
    "The correct method is selected based on the actual object type.",
    "This makes the code easier to extend and maintain.",
]


class MockOCRProvider(OCRProvider):
    name = "mock"
    is_mock = True

    def recognise(
        self,
        line_images: list[np.ndarray],
        boxes: list[tuple[int, int, int, int]],
    ) -> RecognitionResult:
        result = RecognitionResult()
        result.warnings.append(
            "Mock recognition engine - this text is generated, not read from the image."
        )

        for index, (image, box) in enumerate(zip(line_images, boxes)):
            text = _SAMPLE_LINES[index % len(_SAMPLE_LINES)]
            # Derive a stable pseudo-confidence from the pixels so that the
            # same image always scores identically.
            digest = hashlib.sha256(np.ascontiguousarray(image).tobytes()).digest()
            jitter = digest[0] / 255.0
            confidence = 0.84 + 0.13 * jitter
            result.lines.append(
                RecognisedLine(
                    index=index,
                    text=text,
                    confidence=round(min(confidence, 0.97), 4),
                    bbox=box,
                )
            )

        return result

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            model_name="mock-handwriting",
            model_version="1.0",
            device="cpu",
            is_ready=True,
            is_mock=True,
            detail="Deterministic stand-in. No model is loaded and the image is not read.",
        )
