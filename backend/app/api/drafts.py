from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api._common import PageParams, get_or_404, paginate
from app.core.db import get_db
from app.core.deps import require_operator, require_viewer
from app.models import Approval, Company, Contact, DraftStatus, EmailDraft, OutreachDraft, User
from app.services.audit import audit
from app.services.outreach import recheck_quality

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


def draft_out(d: OutreachDraft, brief: bool = False, db: Session | None = None) -> dict:
    out = {"id": d.id, "company_id": d.company_id, "contact_id": d.contact_id, "service": d.service,
           "status": d.status.value, "version": d.version, "subject": d.subject, "quality_score": d.quality_score,
           "confidence": d.confidence, "created_at": d.created_at, "updated_at": d.updated_at,
           "edited_by_user": d.edited_by_user, "approved_at": d.approved_at}
    if brief:
        return out
    out.update(body=d.body, opening_line=d.opening_line, linkedin_connection_note=d.linkedin_connection_note,
               linkedin_message=d.linkedin_message, recommended_offer=d.recommended_offer,
               personalisation_explanation=d.personalisation_explanation, evidence=d.evidence,
               quality_report=d.quality_report, regeneration_count=d.regeneration_count,
               regeneration_notes=d.regeneration_notes, original=d.original)
    if db is not None:
        c = db.get(Company, d.company_id)
        ct = db.get(Contact, d.contact_id) if d.contact_id else None
        out["company"] = {"id": c.id, "name": c.name, "domain": c.domain_normalized, "website": c.website,
                          "status": c.status.value, "website_score": c.website_score, "brain_score": c.brain_score,
                          "recommended_service": c.recommended_service, "brief": (c.data or {}).get("brief")}
        out["contact"] = {"id": ct.id, "full_name": ct.full_name, "job_title": ct.job_title, "email": ct.email,
                          "email_status": ct.email_status.value, "profile_url": ct.profile_url,
                          "source_url": ct.source_url} if ct else None
        names = {u.id: (u.full_name or u.email) for u in db.scalars(select(User)).all()}
        out["history"] = [{"action": a.action, "user_id": a.user_id, "user_name": names.get(a.user_id),
                           "comment": a.comment, "changes": a.changes, "created_at": a.created_at}
                          for a in db.scalars(select(Approval).where(Approval.outreach_draft_id == d.id)
                                              .order_by(Approval.created_at)).all()]
        out["email_drafts"] = [{"id": e.id, "status": e.status, "external_draft_id": e.external_draft_id,
                                "email_account_id": e.email_account_id, "to_email": e.to_email,
                                "attempts": e.attempts, "last_error": e.last_error, "created_at": e.created_at,
                                "sent_detected_at": e.sent_detected_at}
                               for e in db.scalars(select(EmailDraft).where(EmailDraft.outreach_draft_id == d.id)).all()]
    return out


@router.get("")
def list_drafts(status: list[str] | None = None, company_id: uuid.UUID | None = None, service: str | None = None,
                pp: PageParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    stmt = select(OutreachDraft).where(OutreachDraft.deleted_at.is_(None))
    if status:
        stmt = stmt.where(OutreachDraft.status.in_([DraftStatus(s) for s in status]))
    if company_id:
        stmt = stmt.where(OutreachDraft.company_id == company_id)
    if service:
        stmt = stmt.where(OutreachDraft.service == service)
    stmt = stmt.order_by(OutreachDraft.created_at.desc())

    def ser(d):
        o = draft_out(d, brief=True)
        c = db.get(Company, d.company_id)
        ct = db.get(Contact, d.contact_id) if d.contact_id else None
        o.update(company_name=c.name if c else None, contact_name=ct.full_name if ct else None)
        return o

    return paginate(db, stmt, pp, ser)


@router.get("/{draft_id}")
def get_draft(draft_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return draft_out(get_or_404(db, OutreachDraft, draft_id), db=db)


class GenerateIn(BaseModel):
    company_id: uuid.UUID
    contact_id: uuid.UUID | None = None


@router.post("/generate")
def generate(body: GenerateIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    from app.ai.runtime import AgentFailed, AgentUnavailable, BudgetExceeded
    from app.services.outreach import OutreachBlocked, generate_draft

    c = get_or_404(db, Company, body.company_id)
    ct = get_or_404(db, Contact, body.contact_id) if body.contact_id else None
    if ct and ct.company_id != c.id:
        raise HTTPException(422, "Contact does not belong to this company")
    try:
        d = generate_draft(db, c, contact=ct, user=user)
    except OutreachBlocked as e:
        raise HTTPException(409, str(e)) from None
    except AgentUnavailable as e:
        raise HTTPException(503, f"AI not configured: {e}") from None
    except BudgetExceeded as e:
        raise HTTPException(429, str(e)) from None
    except AgentFailed as e:
        raise HTTPException(502, f"Generation failed: {e}") from None
    db.commit()
    return draft_out(d, db=db)


class DraftEdit(BaseModel):
    subject: str | None = Field(None, min_length=1, max_length=300)
    body: str | None = Field(None, min_length=1, max_length=10_000)
    linkedin_connection_note: str | None = Field(None, max_length=300)
    linkedin_message: str | None = Field(None, max_length=2000)
    comment: str | None = Field(None, max_length=1000)


EDITABLE = {DraftStatus.PENDING_APPROVAL, DraftStatus.SAVED_FOR_LATER, DraftStatus.NEEDS_REVIEW}


def apply_edit(db: Session, d: OutreachDraft, body: DraftEdit, user: User) -> dict:
    if d.status not in EDITABLE:
        raise HTTPException(409, f"Draft in status {d.status.value} cannot be edited")
    changes = {}
    for k in ("subject", "body", "linkedin_connection_note", "linkedin_message"):
        v = getattr(body, k)
        if v is not None and v != getattr(d, k):
            changes[k] = {"from": getattr(d, k), "to": v}
            setattr(d, k, v)
    if not changes:
        return {}
    d.edited_by_user = True
    score, rep = recheck_quality(db, d)
    d.quality_score, d.quality_report = score, {**rep, "previous_ai_review": (d.quality_report or {}).get("ai_scores")}
    db.add(Approval(outreach_draft_id=d.id, user_id=user.id, action="edit", comment=body.comment, changes=changes,
                    draft_snapshot={"subject": d.subject, "body": d.body}))
    audit(db, "draft.edited", actor=user, entity_type="outreach_draft", entity_id=d.id, detail={"fields": list(changes)})
    return changes


@router.patch("/{draft_id}")
def edit_draft(draft_id: uuid.UUID, body: DraftEdit, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    d = get_or_404(db, OutreachDraft, draft_id)
    apply_edit(db, d, body, user)
    db.commit()
    return draft_out(d, db=db)
