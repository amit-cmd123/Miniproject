"""Request-scoped dependencies shared by the v1 routers.

The engine switch lives here. Every endpoint that reads handwriting or marks
an answer accepts `?engine=`, so the interface can run one upload through
Gemini and the next through the local model without restarting anything.

    ?engine=gemini   Google's model - the engine of record
    ?engine=local    the handwriting model we trained, and the rubric matcher
    ?engine=auto     whatever the .env file configures (the default)

A requested engine that cannot run returns 503 with the reason, rather than
quietly producing a result from the other one. The provider's name is written
onto every transcription and every score, so a substitution here would make
the stored record wrong.
"""

from __future__ import annotations

from fastapi import HTTPException, Query, status

from app.core.config import settings
from app.providers.evaluation.base import EvaluationProvider
from app.providers.evaluation.registry import (
    EngineUnavailable as MarkerUnavailable,
    get_evaluation_provider_for,
)
from app.providers.ocr.base import OCRProvider
from app.providers.ocr.registry import EngineUnavailable, get_ocr_provider_for

ENGINE_QUERY = Query(
    None,
    description=(
        "Which engine to use: 'gemini' (cloud), 'local' (the handwriting model "
        "bundled with this project), or 'auto' for the configured default."
    ),
)


def ocr_engine(engine: str | None = ENGINE_QUERY) -> OCRProvider:
    try:
        return get_ocr_provider_for(engine)
    except EngineUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def marking_engine(engine: str | None = ENGINE_QUERY) -> EvaluationProvider:
    try:
        return get_evaluation_provider_for(engine)
    except MarkerUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def gemini_is_configured() -> bool:
    """Whether the cloud engine could run at all.

    The interface uses this to decide whether the switch is even offerable,
    so that turning it on cannot produce a 503 the user had no way to predict.
    """
    return bool(settings.gemini_api_key)
