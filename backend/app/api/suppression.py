from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api._common import PageParams, get_or_404, like, paginate
from app.core.db import get_db
from app.core.deps import require_admin, require_operator, require_viewer
from app.discovery.normalize import normalize_domain, normalize_email
from app.models import Company, Contact, Suppression, User
from app.schemas.common import ORM
from app.services.audit import audit
from app.services.suppression import suppress

router = APIRouter(prefix="/api/suppression", tags=["suppression"])


class SuppressionOut(ORM):
    id: uuid.UUID
    kind: str
    value: str
    reason: str
    source: str | None
    active: bool
    contact_id: uuid.UUID | None
    company_id: uuid.UUID | None
    created_at: datetime


class SuppressionIn(BaseModel):
    value: str = Field(min_length=3, max_length=320)
    kind: str = Field(pattern="^(email|domain)$")
    reason: str = Field("manual", max_length=60)
    note: str | None = Field(None, max_length=1000)


@router.get("")
def list_suppressions(q: str | None = Query(None, max_length=200),
                      active: str = Query("true", pattern="^(true|false|all)$"),
                      pp: PageParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    stmt = select(Suppression)
    if q:
        stmt = stmt.where(Suppression.value.ilike(like(q.lower())))
    if active != "all":
        stmt = stmt.where(Suppression.active.is_(active == "true"))
    return paginate(db, stmt.order_by(Suppression.created_at.desc()), pp,
                    lambda s: SuppressionOut.model_validate(s).model_dump())


@router.post("", status_code=201)
def add(body: SuppressionIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    value = normalize_email(body.value) if body.kind == "email" else normalize_domain(body.value)
    if not value:
        raise HTTPException(422, f"Invalid {body.kind}")
    contact = db.scalar(select(Contact).where(Contact.email_normalized == value)) if body.kind == "email" else None
    company = db.scalar(select(Company).where(Company.domain_normalized == value,
                                              Company.deleted_at.is_(None))) if body.kind == "domain" else None
    suppress(db, email=value if body.kind == "email" else None, domain=value if body.kind == "domain" else None,
             reason=body.reason, source=body.note or "manual", contact=contact, company=company, user=user,
             block_company=company is not None)
    db.commit()
    row = db.scalar(select(Suppression).where(Suppression.kind == body.kind, Suppression.value == value))
    return SuppressionOut.model_validate(row)


@router.post("/{sid}/deactivate")
def deactivate(sid: uuid.UUID, reason: str = Query(..., min_length=3, max_length=500), db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    """Admin-only. The record is preserved (never deleted); use only to correct a mistaken entry."""
    s = get_or_404(db, Suppression, sid)
    if s.reason in ("opt_out", "unsubscribe"):
        raise HTTPException(409, "Opt-out suppressions cannot be deactivated")
    s.active = False
    audit(db, "suppression.deactivated", actor=user, entity_type="suppression", entity_id=s.id,
          detail={"value": s.value, "reason": reason})
    db.commit()
    return SuppressionOut.model_validate(s)
