from __future__ import annotations

import io
import json
import uuid
import zipfile

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api._common import PageParams, get_or_404, paginate
from app.core.db import get_db
from app.core.deps import require_admin
from app.models import (
    AuditLog,
    BuyingSignal,
    Company,
    Contact,
    Interaction,
    Note,
    OutreachDraft,
    ResearchReport,
    Suppression,
    User,
)
from app.models.base import utcnow
from app.schemas.common import Msg
from app.services.audit import audit

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/audit")
def audit_log(action: str | None = None, entity_type: str | None = None, entity_id: str | None = None,
              pp: PageParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_admin)):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    users = {u.id: u.email for u in db.scalars(select(User)).all()}
    return paginate(db, stmt, pp, lambda a: {
        "id": a.id, "created_at": a.created_at, "actor": users.get(a.actor_id) if a.actor_id else a.actor_type,
        "actor_type": a.actor_type, "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id,
        "detail": a.detail, "ip": a.ip})


def _rows(db, model, **filters):
    stmt = select(model)
    for k, v in filters.items():
        stmt = stmt.where(getattr(model, k) == v)
    return [{c.name: (str(getattr(r, c.name)) if getattr(r, c.name) is not None and not isinstance(
        getattr(r, c.name), (int, float, bool, dict, list, str)) else getattr(r, c.name))
             for c in model.__table__.columns} for r in db.scalars(stmt).all()]


@router.get("/export/contact/{contact_id}")
def export_contact_data(contact_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Data-subject access export: everything stored about one contact (JSON)."""
    c = get_or_404(db, Contact, contact_id, include_deleted=True)
    data = {"contact": _rows(db, Contact, id=c.id), "drafts": _rows(db, OutreachDraft, contact_id=c.id),
            "interactions": _rows(db, Interaction, contact_id=c.id), "notes": _rows(db, Note, contact_id=c.id),
            "suppression": _rows(db, Suppression, contact_id=c.id)}
    audit(db, "privacy.export_contact", actor=user, entity_type="contact", entity_id=c.id)
    db.commit()
    return Response(json.dumps(data, default=str, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename=contact-{c.id}.json"})


@router.post("/erase/contact/{contact_id}", response_model=Msg)
def erase_contact(contact_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Right to erasure: removes personal data but keeps a suppression entry so the person is never re-contacted."""
    from app.services.suppression import suppress

    c = get_or_404(db, Contact, contact_id, include_deleted=True)
    if c.email_normalized:
        suppress(db, email=c.email_normalized, reason="erasure", source="data deletion request", contact=c, user=user)
    for d in db.scalars(select(OutreachDraft).where(OutreachDraft.contact_id == c.id)).all():
        d.body, d.subject, d.opening_line, d.linkedin_message, d.linkedin_connection_note = "[erased]", "[erased]", None, None, None
        d.original, d.deleted_at = {}, utcnow()
    for i in db.scalars(select(Interaction).where(Interaction.contact_id == c.id)).all():
        i.snippet, i.subject, i.suggested_reply, i.from_email = None, "[erased]", None, None
    c.full_name, c.first_name, c.last_name = "[erased]", None, None
    c.email, c.profile_url, c.job_title, c.data, c.email_check_detail = None, None, None, {}, {}
    c.email_normalized = None
    c.deleted_at = utcnow()
    audit(db, "privacy.erase_contact", actor=user, entity_type="contact", entity_id=c.id)
    db.commit()
    return Msg(message="Personal data erased; a suppression record was kept to prevent future contact.")


@router.get("/export/all")
def export_all(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Full CRM data export (zip of JSON files)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, model in [("companies", Company), ("contacts", Contact), ("signals", BuyingSignal),
                            ("research_reports", ResearchReport), ("drafts", OutreachDraft),
                            ("interactions", Interaction), ("notes", Note), ("suppression", Suppression)]:
            z.writestr(f"{name}.json", json.dumps(_rows(db, model), default=str))
    audit(db, "export.all", actor=user)
    db.commit()
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=agency-growth-engine-export.zip"})
