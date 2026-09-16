"""Shared enumerations.

These are frozen contracts: all four workstreams depend on them, so changes
need a second reviewer.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class UserRole(StrEnum):
    ADMIN = "admin"
    EXAMINER = "examiner"
    OPERATOR = "operator"


class AnswerStatus(StrEnum):
    """Lifecycle of a single answer. Transitions are enforced in the service
    layer, never set ad hoc by a router."""

    REGISTERED = "registered"
    OCR_RUNNING = "ocr_running"
    OCR_DONE = "ocr_done"
    OCR_FAILED = "ocr_failed"
    EVALUATED = "evaluated"
    UNDER_REVIEW = "under_review"
    FINALIZED = "finalized"


class TranscriptionBand(StrEnum):
    """How far a transcription can be trusted (Part 1)."""

    RELIABLE = "reliable"
    SPOT_CHECK = "spot_check"
    VERIFY = "verify"
    UNUSABLE = "unusable"


class ReviewBand(StrEnum):
    """Where an evaluation gets routed (Part 3)."""

    AUTO_ACCEPT = "auto_accept"
    QUICK_REVIEW = "quick_review"
    MANDATORY_REVIEW = "mandatory_review"
    DETAILED_VERIFICATION = "detailed_verification"


class TextSource(StrEnum):
    """Which transcription the downstream evaluator should consume."""

    MACHINE = "machine"
    HUMAN_CORRECTED = "human_corrected"


class ReviewAction(StrEnum):
    ACCEPT = "accept"
    MODIFY = "modify"
