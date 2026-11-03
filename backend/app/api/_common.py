from __future__ import annotations

import uuid
from typing import Any, TypeVar

from fastapi import HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class PageParams:
    def __init__(self, page: int = Query(1, ge=1, le=100_000), page_size: int = Query(25, ge=1, le=200)):
        self.page = page
        self.page_size = page_size


def paginate(db: Session, stmt: Select, params: PageParams, serializer=None) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(stmt.offset((params.page - 1) * params.page_size).limit(params.page_size)).all()
    items = [serializer(r) for r in rows] if serializer else rows
    return {"items": items, "total": total or 0, "page": params.page, "page_size": params.page_size}


def get_or_404(db: Session, model: type[T], id_: uuid.UUID, *, include_deleted: bool = False) -> T:
    obj = db.get(model, id_)
    if obj is None or (not include_deleted and getattr(obj, "deleted_at", None) is not None):
        raise HTTPException(404, f"{model.__name__} not found")
    return obj


def apply_sort(stmt: Select, model: Any, sort: str | None, allowed: set[str], default: str = "-created_at") -> Select:
    s = sort or default
    desc = s.startswith("-")
    field = s.lstrip("-")
    if field not in allowed:
        field, desc = default.lstrip("-"), default.startswith("-")
    col = getattr(model, field)
    return stmt.order_by(col.desc().nullslast() if desc else col.asc().nullsfirst(), model.id)


def like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
