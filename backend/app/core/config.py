"""Application configuration.

Every tunable value in EvalNova Core lives here or in the database, never
inline in business logic. Overridable through environment variables or a
`.env` file at the repository root.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_prefix="EVALNOVA_",
        extra="ignore",
    )

    # ---- application -----------------------------------------------------
    app_name: str = "EvalNova Core"
    api_prefix: str = "/api/v1"
    debug: bool = True

    # ---- persistence -----------------------------------------------------
    # SQLite by default so the project runs with no external services.
    # Point this at PostgreSQL to switch; nothing else in the code changes.
    database_url: str = Field(default=f"sqlite:///{REPO_ROOT / 'data' / 'evalnova.db'}")
    storage_dir: Path = Field(default=REPO_ROOT / "data" / "storage")

    # ---- OCR provider ----------------------------------------------------
    # "mock"      - deterministic stand-in, no model download, always available
    # "trocr"     - Hugging Face TrOCR handwriting model (CPU or CUDA)
    # "gemini"    - Google Gemini vision model over the network; falls back to
    #               TrOCR if no key is set or a request fails
    ocr_provider: str = "trocr"
    # small, not base: on cleaned pages the two measured within 2 points of
    # character error rate of each other, and small reads ~10x faster on CPU.
    ocr_model_name: str = "microsoft/trocr-small-handwritten"
    ocr_device: str = "auto"  # auto | cpu | cuda
    ocr_max_lines: int = 40
    ocr_fallback_to_mock: bool = True

    # ---- Gemini (cloud handwriting recognition) --------------------------
    # Answer images are sent to Google when this provider is selected. Read
    # from EVALNOVA_GEMINI_API_KEY, or the conventional GEMINI_API_KEY.
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EVALNOVA_GEMINI_API_KEY", "GEMINI_API_KEY"),
    )
    gemini_model: str = "gemini-3.5-flash"
    gemini_timeout_seconds: float = 90.0
    gemini_thinking_level: str | None = "low"
    # Fall back to the local engine when a Gemini request fails outright.
    gemini_fallback_to_local: bool = True

    # ---- evaluation provider (Part 3 - not yet implemented) --------------
    evaluation_provider: str = "mock"

    # ---- uploads ---------------------------------------------------------
    max_upload_bytes: int = 25 * 1024 * 1024
    # A scanned multi-page booklet at 200-300 DPI runs to tens of megabytes,
    # so PDFs get their own, larger allowance.
    max_pdf_bytes: int = 120 * 1024 * 1024
    # Each page is several seconds of work, so an unbounded booklet could tie
    # up the process for a very long time.
    max_pdf_pages: int = 30
    allowed_image_types: tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/bmp",
        "image/tiff",
    )

    @property
    def images_dir(self) -> Path:
        return self.storage_dir / "images"

    @property
    def debug_dir(self) -> Path:
        return self.storage_dir / "debug"

    def ensure_dirs(self) -> None:
        for directory in (self.storage_dir, self.images_dir, self.debug_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


settings = get_settings()
