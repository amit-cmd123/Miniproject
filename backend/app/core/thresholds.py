"""Confidence thresholds and routing bands.

These values are deliberately *not* scattered through the codebase. They are
starting hypotheses that Phase 3 will move based on measured calibration, so
they live in one place and are read through functions rather than inlined.

In Phase 2 these defaults get backed by the `config_settings` table so they
are tunable at runtime without a redeploy; the accessors below are already
shaped for that change.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.enums import ReviewBand, TranscriptionBand


@dataclass(frozen=True)
class Band:
    band: str
    min_confidence: float
    label: str
    description: str


# --- transcription (Part 1) ------------------------------------------------
# How much should a human trust this transcription before it is evaluated?
TRANSCRIPTION_BANDS: tuple[Band, ...] = (
    Band(
        TranscriptionBand.RELIABLE,
        0.95,
        "Reliable",
        "Transcription may proceed to evaluation without routine checking.",
    ),
    Band(
        TranscriptionBand.SPOT_CHECK,
        0.85,
        "Spot check",
        "Largely trustworthy; a quick read-through is advised.",
    ),
    Band(
        TranscriptionBand.VERIFY,
        0.70,
        "Verify",
        "Enough uncertainty that a human should confirm the text before marks depend on it.",
    ),
    Band(
        TranscriptionBand.UNUSABLE,
        0.0,
        "Manual transcription",
        "Too unreliable to evaluate. Correct the text by hand before continuing.",
    ),
)

# --- evaluation (Part 3) ---------------------------------------------------
# Recorded here now so Part 3 has a contract to build against.
EVALUATION_BANDS: tuple[Band, ...] = (
    Band(ReviewBand.AUTO_ACCEPT, 0.95, "Auto-accept candidate",
         "Eligible for automatic acceptance once the false-auto-accept rate has been measured."),
    Band(ReviewBand.QUICK_REVIEW, 0.90, "Quick review",
         "Examiner confirms the total; criterion detail optional."),
    Band(ReviewBand.MANDATORY_REVIEW, 0.85, "Mandatory review",
         "Examiner must open the criterion breakdown before submitting."),
    Band(ReviewBand.DETAILED_VERIFICATION, 0.0, "Detailed verification",
         "Original handwriting must be inspected."),
)


def _classify(value: float, bands: tuple[Band, ...]) -> Band:
    for band in bands:
        if value >= band.min_confidence:
            return band
    return bands[-1]


def classify_transcription(confidence: float) -> Band:
    """Map a transcription confidence onto a human-facing trust band."""
    return _classify(confidence, TRANSCRIPTION_BANDS)


def classify_evaluation(confidence: float) -> Band:
    """Map an evaluation confidence onto a review-routing band."""
    return _classify(confidence, EVALUATION_BANDS)


def describe_bands() -> dict[str, list[dict[str, object]]]:
    """Expose the current banding so the UI never hard-codes these numbers."""

    def dump(bands: tuple[Band, ...]) -> list[dict[str, object]]:
        return [
            {
                "band": b.band,
                "min_confidence": b.min_confidence,
                "label": b.label,
                "description": b.description,
            }
            for b in bands
        ]

    return {
        "transcription": dump(TRANSCRIPTION_BANDS),
        "evaluation": dump(EVALUATION_BANDS),
    }
