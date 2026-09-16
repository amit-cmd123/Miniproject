"""EvalNova Core - application entry point."""

from __future__ import annotations

import logging
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import answers, roadmap
from app.core.config import settings
from app.db.session import init_db
from app.providers.ocr.registry import get_ocr_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Confidence-aware, rubric-driven evaluation of handwritten examination "
        "answers.\n\n"
        "**Part 1 (Handwriting & OCR) is implemented.** Parts 2-4 are registered "
        "as planned endpoints that return 501 with the workstream that owns them."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local development only; tightened before any deployment
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("Database ready at %s", settings.database_url)
    logger.info(
        "Recognition engine: %s (%s)", settings.ocr_provider, settings.ocr_model_name
    )

    # Load the handwriting weights in the background. Without this the first
    # upload of a session pays ~10s of model loading on top of recognition,
    # which reads as a broken page rather than a slow one.
    def _warmup() -> None:
        try:
            get_ocr_provider().warmup()
            logger.info("Recognition engine warmed up and ready")
        except Exception:  # pragma: no cover - never block startup
            logger.warning("Warm-up failed; the engine will load on first use",
                           exc_info=True)

    threading.Thread(target=_warmup, name="ocr-warmup", daemon=True).start()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak a stack trace, and never return a plausible-looking success.

    A failure here must be visible as a failure - silently producing an empty
    transcription would be worse than an error.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "Something went wrong handling that request. The details "
            "have been logged.",
        },
    )


@app.get("/health", tags=["system"])
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "ocr_provider": settings.ocr_provider,
        "database": settings.database_url.split("///")[-1],
    }


app.include_router(answers.router, prefix=settings.api_prefix)
app.include_router(roadmap.router, prefix=settings.api_prefix)
