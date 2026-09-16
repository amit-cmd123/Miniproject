"""Audit logging.

Every state change gets a row. Traceability is a product requirement, not a
debugging nicety: the point of EvalNova is that a marks decision can be
explained afterwards.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models import AuditLog

logger = logging.getLogger(__name__)


def record(
    db: Session,
    *,
    action: str,
    object_type: str,
    object_id: str,
    actor_id: str | None = None,
    actor_label: str = "system",
    details: dict | None = None,
) -> None:
    entry = AuditLog(
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        object_type=object_type,
        object_id=object_id,
        details=details or {},
    )
    db.add(entry)
    try:
        db.commit()
    except Exception:  # pragma: no cover - auditing must never break a request
        logger.warning("Could not write audit entry for %s", action, exc_info=True)
        db.rollback()


def recent(db: Session, limit: int = 50) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
