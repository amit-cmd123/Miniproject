"""Answer registration and image storage."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Answer
from app.schemas.enums import AnswerStatus
from app.services import audit

EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}


class UploadRejected(ValueError):
    """The upload failed validation. The message is shown to the user, so it
    says what to do about it."""


def validate_upload(content_type: str | None, size_bytes: int) -> None:
    if size_bytes == 0:
        raise UploadRejected("The file is empty. Choose a photograph or scan of an answer.")
    if size_bytes > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / (1024 * 1024)
        raise UploadRejected(
            f"That file is larger than the {limit_mb:.0f} MB limit. "
            "Try a JPEG export or a lower-resolution scan."
        )
    if content_type not in settings.allowed_image_types:
        allowed = ", ".join(sorted(t.split("/")[1].upper() for t in settings.allowed_image_types))
        raise UploadRejected(
            f"'{content_type or 'unknown'}' is not a supported image type. Use {allowed}."
        )


def store_image(data: bytes, content_type: str | None) -> Path:
    suffix = EXTENSIONS.get(content_type or "", ".png")
    filename = f"{uuid.uuid4()}{suffix}"
    target = Path(settings.images_dir) / filename
    target.write_bytes(data)
    return target


def register_answer(
    db: Session,
    *,
    data: bytes,
    content_type: str | None,
    original_filename: str | None,
    question_id: str | None = None,
    booklet_ref: str | None = None,
    document_ref: str | None = None,
    page_number: int | None = None,
    source_filename: str | None = None,
    skip_validation: bool = False,
) -> Answer:
    """Register one answer image.

    `skip_validation` is used for pages we rendered ourselves from a PDF: the
    bytes came from our own encoder, so the upload checks have already been
    applied to the originating document.
    """
    if not skip_validation:
        validate_upload(content_type, len(data))
    path = store_image(data, content_type)

    answer = Answer(
        question_id=question_id,
        booklet_ref=booklet_ref,
        document_ref=document_ref,
        page_number=page_number,
        source_filename=source_filename,
        image_path=str(path),
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=len(data),
        status=AnswerStatus.REGISTERED,
    )
    db.add(answer)
    db.commit()
    db.refresh(answer)

    audit.record(
        db,
        action="answer.registered",
        object_type="answer",
        object_id=answer.id,
        details={"filename": original_filename, "bytes": len(data)},
    )
    return answer


def list_answers(db: Session, limit: int = 100) -> list[Answer]:
    return (
        db.query(Answer)
        .order_by(Answer.created_at.desc())
        .limit(limit)
        .all()
    )
