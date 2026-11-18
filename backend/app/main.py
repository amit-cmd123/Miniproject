"""EvalNova Core - application entry point."""

from __future__ import annotations

import logging
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import answers, evaluations, roadmap, rubrics
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
        "The pipeline runs end to end: a scanned booklet is transcribed "
        "(Part 1), split per question and marked against a rubric with a "
        "composite confidence (Parts 2-3), and routed to an examiner who "
        "accepts or changes the score (Part 4). Every human decision is "
        "stored as a new row beside the machine's, so agreement can be "
        "measured rather than asserted."
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
    logger.info(
        "Marking engine: %s (%s)",
        settings.evaluation_provider,
        settings.evaluation_model or settings.gemini_model,
    )
    _seed_bundled_exam()

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


def _seed_bundled_exam() -> None:
    """Load the bundled paper and its rubrics if no exam exists yet.

    Marking needs a rubric, and an application that starts with nothing to
    mark against looks broken rather than empty. Seeding is idempotent by
    subject code, so a restart never duplicates the paper, and an exam edited
    through the API is left exactly as the user left it.
    """
    from app.api.v1.rubrics import SEED_PATH
    from app.db.session import SessionLocal
    from app.services import rubric_service

    if not SEED_PATH.exists():
        logger.info("No bundled exam at %s; none seeded", SEED_PATH)
        return

    with SessionLocal() as db:
        try:
            if rubric_service.list_exams(db):
                logger.info("An exam is already defined; not seeding")
                return
            exam = rubric_service.seed_from_file(db, SEED_PATH)
            report = rubric_service.validate_exam(db, exam)
            logger.info(
                "Seeded '%s': %s questions, %s criteria, %s marks (rubrics %s)",
                exam.title,
                report.questions_checked,
                report.criteria_checked,
                report.total_marks,
                "valid" if report.is_valid else "INVALID",
            )
            for problem in report.problems:
                if problem.severity == "error":
                    logger.error("Rubric %s: %s", problem.question, problem.message)
        except Exception:  # pragma: no cover - never block startup
            logger.warning("Could not seed the bundled exam", exc_info=True)


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
app.include_router(rubrics.router, prefix=settings.api_prefix)
app.include_router(evaluations.router, prefix=settings.api_prefix)
# Registered last: it only serves build status and the few routes that are
# still unimplemented, so a real router always wins the path.
app.include_router(roadmap.router, prefix=settings.api_prefix)
