"""Approval queue. Approval is explicit, logged, and at most creates an UNSENT mailbox draft."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api._common import PageParams, get_or_404, paginate
from app.api.drafts import DraftEdit, apply_edit, draft_out
from app.core.db import get_db
from app.core.deps import client_ip, require_operator, require_viewer
from app.integrations.email.base import MailboxAuthError, MailboxError
from app.integrations.email.service import create_mailbox_draft, default_account
from app.models import (
    Approval,
    Company,
    Contact,
    DraftStatus,
    EmailAccount,
    LeadStatus,
    OutreachDraft,
    User,
)
from app.models.base import utcnow
from app.research.service import latest_report
from app.services.audit import audit
from app.services.state_machine import try_transition
from app.services.suppression import contact_suppressed, suppress

router = APIRouter(prefix="/api/approvals", tags=["approvals"])
QUEUE_STATES = [DraftStatus.PENDING_APPROVAL, DraftStatus.NEEDS_REVIEW, DraftStatus.SAVED_FOR_LATER]


@router.get("/queue")
def queue(state: str = "pending", service: str | None = None, pp: PageParams = Depends(),
          db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    states = {"pending": [DraftStatus.PENDING_APPROVAL], "review": [DraftStatus.NEEDS_REVIEW],
              "later": [DraftStatus.SAVED_FOR_LATER], "all": QUEUE_STATES}.get(state, [DraftStatus.PENDING_APPROVAL])
    stmt = select(OutreachDraft).where(OutreachDraft.deleted_at.is_(None), OutreachDraft.status.in_(states))
    if service:
        stmt = stmt.where(OutreachDraft.service == service)
    stmt = stmt.order_by(OutreachDraft.quality_score.desc().nullslast(), OutreachDraft.created_at)

    def ser(d: OutreachDraft) -> dict:
        o = draft_out(d, db=db)
        rep = latest_report(db, d.company_id)
        o["research_summary"] = rep.summary if rep else None
        o["research_report_id"] = rep.id if rep else None
        return o

    counts = dict(db.execute(select(OutreachDraft.status, func.count()).where(
        OutreachDraft.deleted_at.is_(None), OutreachDraft.status.in_(QUEUE_STATES)).group_by(OutreachDraft.status)).all())
    page = paginate(db, stmt, pp, ser)
    page["counts"] = {k.value: v for k, v in counts.items()}
    return page


class ApproveIn(BaseModel):
    email_account_id: uuid.UUID | None = None
    edits: DraftEdit | None = None
    override_quality: bool = False
    comment: str | None = Field(None, max_length=1000)


def _snapshot(d: OutreachDraft) -> dict:
    return {"subject": d.subject, "body": d.body, "linkedin_connection_note": d.linkedin_connection_note,
            "linkedin_message": d.linkedin_message, "quality_score": d.quality_score, "version": d.version}


@router.post("/{draft_id}/approve")
def approve(draft_id: uuid.UUID, body: ApproveIn, request: Request,
            db: Session = Depends(get_db), user: User = Depends(require_operator)):
    d = get_or_404(db, OutreachDraft, draft_id)
    company = db.get(Company, d.company_id)
    contact = db.get(Contact, d.contact_id) if d.contact_id else None
    already = d.status in (DraftStatus.APPROVED, DraftStatus.EMAIL_DRAFT_CREATED)
    if not already:
        if d.status not in QUEUE_STATES:
            raise HTTPException(409, f"Draft in status {d.status.value} cannot be approved")
        if body.edits:
            apply_edit(db, d, body.edits, user)
        if contact_suppressed(db, contact, company):
            d.status = DraftStatus.BLOCKED
            db.commit()
            raise HTTPException(409, "Recipient is on the suppression list — draft blocked")
        if contact is None or not contact.email_normalized:
            raise HTTPException(409, "Draft has no recipient email")
        passed = (d.quality_report or {}).get("passed", False)
        if not passed and not body.override_quality:
            raise HTTPException(409, "Draft is below the quality threshold. Edit it, request regeneration, or "
                                     "approve with override_quality=true.")
        d.status = DraftStatus.APPROVED
        d.approved_at, d.approved_by_id = utcnow(), user.id
        db.add(Approval(outreach_draft_id=d.id, user_id=user.id, action="approve", comment=body.comment,
                        changes={"override_quality": body.override_quality} if body.override_quality else {},
                        draft_snapshot=_snapshot(d)))
        try_transition(db, company, LeadStatus.APPROVED, actor=user, reason="draft approved")
        audit(db, "draft.approved", actor=user, entity_type="outreach_draft", entity_id=d.id,
              detail={"quality": d.quality_score, "override_quality": body.override_quality}, ip=client_ip(request))
        db.commit()

    acct = db.get(EmailAccount, body.email_account_id) if body.email_account_id else default_account(db)
    result = {"approved": True, "email_draft": None, "message": ""}
    if acct is None or acct.deleted_at is not None:
        result["message"] = ("Approved. No email account is connected — connect Gmail or Outlook and the unsent "
                             "draft will be created automatically.")
    else:
        try:
            ed = create_mailbox_draft(db, d, acct, user)
            db.commit()
            result["email_draft"] = {"id": str(ed.id), "external_draft_id": ed.external_draft_id,
                                     "provider": acct.provider, "account": acct.email, "status": ed.status}
            result["message"] = (f"Unsent draft created in {acct.email} ({acct.provider}). "
                                 "Open your mail client to review and send it yourself.")
        except MailboxAuthError as e:
            db.commit()
            result["message"] = f"Approved, but the mailbox needs reconnecting: {e}"
        except MailboxError as e:
            db.commit()
            result["message"] = f"Approved. Draft creation will be retried automatically: {e}"
        except ValueError as e:
            db.commit()
            raise HTTPException(409, str(e)) from None
    db.refresh(d)
    result["draft"] = draft_out(d, db=db)
    return result


class ActionIn(BaseModel):
    comment: str | None = Field(None, max_length=2000)


def _act(db: Session, d: OutreachDraft, user: User, action: str, comment: str | None) -> None:
    db.add(Approval(outreach_draft_id=d.id, user_id=user.id, action=action, comment=comment, draft_snapshot=_snapshot(d)))
    audit(db, f"draft.{action}", actor=user, entity_type="outreach_draft", entity_id=d.id, detail={"comment": comment})


@router.post("/{draft_id}/reject")
def reject(draft_id: uuid.UUID, body: ActionIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    d = get_or_404(db, OutreachDraft, draft_id)
    if d.status not in QUEUE_STATES:
        raise HTTPException(409, f"Draft in status {d.status.value} cannot be rejected")
    d.status = DraftStatus.REJECTED
    _act(db, d, user, "reject", body.comment)
    company = db.get(Company, d.company_id)
    try_transition(db, company, LeadStatus.QUALIFIED, actor=user, reason="draft rejected")
    db.commit()
    return draft_out(d, db=db)


@router.post("/{draft_id}/save-for-later")
def save_for_later(draft_id: uuid.UUID, body: ActionIn, db: Session = Depends(get_db),
                   user: User = Depends(require_operator)):
    d = get_or_404(db, OutreachDraft, draft_id)
    if d.status not in (DraftStatus.PENDING_APPROVAL, DraftStatus.NEEDS_REVIEW):
        raise HTTPException(409, f"Draft in status {d.status.value} cannot be saved for later")
    d.status = DraftStatus.SAVED_FOR_LATER
    _act(db, d, user, "save_for_later", body.comment)
    db.commit()
    return draft_out(d, db=db)


@router.post("/{draft_id}/regenerate")
def regenerate(draft_id: uuid.UUID, body: ActionIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    from app.ai.runtime import AgentFailed, AgentUnavailable, BudgetExceeded
    from app.services.outreach import OutreachBlocked, generate_draft

    d = get_or_404(db, OutreachDraft, draft_id)
    if d.status not in QUEUE_STATES:
        raise HTTPException(409, f"Draft in status {d.status.value} cannot be regenerated")
    _act(db, d, user, "request_regeneration", body.comment)
    company = db.get(Company, d.company_id)
    contact = db.get(Contact, d.contact_id) if d.contact_id else None
    try_transition(db, company, LeadStatus.QUALIFIED, actor=user, reason="regeneration requested")
    try:
        new = generate_draft(db, company, contact=contact, user=user, previous=d,
                             regeneration_notes=body.comment or "Make it more specific and concise.")
    except OutreachBlocked as e:
        db.rollback()
        raise HTTPException(409, str(e)) from None
    except (AgentUnavailable, AgentFailed, BudgetExceeded) as e:
        db.rollback()
        raise HTTPException(503, f"Regeneration unavailable: {e}") from None
    db.commit()
    return draft_out(new, db=db)


@router.post("/{draft_id}/do-not-contact")
def mark_dnc(draft_id: uuid.UUID, body: ActionIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    d = get_or_404(db, OutreachDraft, draft_id)
    contact = db.get(Contact, d.contact_id) if d.contact_id else None
    company = db.get(Company, d.company_id)
    _act(db, d, user, "do_not_contact", body.comment)
    suppress(db, email=contact.email if contact else None, domain=company.domain_normalized, reason="dnc",
             source=body.comment or "approval queue", contact=contact, company=company, user=user, block_company=True)
    db.commit()
    db.refresh(d)
    return draft_out(d, db=db)
