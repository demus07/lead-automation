from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.models.base import utcnow


def audit(
    db: Session,
    action: str,
    *,
    actor: User | None = None,
    actor_type: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
) -> AuditLog:
    """Append an audit entry (flushed with the caller's transaction)."""
    entry = AuditLog(
        created_at=utcnow(),
        actor_id=actor.id if actor else None,
        actor_type=actor_type or ("user" if actor else "system"),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        detail=_jsonable(detail or {}),
        ip=ip,
    )
    db.add(entry)
    return entry


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if hasattr(v, "value"):
        return v.value
    return str(v)
