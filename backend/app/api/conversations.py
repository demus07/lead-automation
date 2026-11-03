from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api._common import PageParams, get_or_404, paginate
from app.core.db import get_db
from app.core.deps import require_operator, require_viewer
from app.models import Company, Contact, Interaction, User
from app.services.replies import apply_classification, classify, log_manual_inbound

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def inter_out(db: Session, i: Interaction) -> dict:
    c = db.get(Company, i.company_id) if i.company_id else None
    ct = db.get(Contact, i.contact_id) if i.contact_id else None
    return {"id": i.id, "company_id": i.company_id, "company_name": c.name if c else None,
            "contact_id": i.contact_id, "contact_name": ct.full_name if ct else None, "channel": i.channel,
            "direction": i.direction, "from_email": i.from_email, "to_email": i.to_email, "subject": i.subject,
            "snippet": i.snippet, "occurred_at": i.occurred_at, "classification": i.classification,
            "classification_confidence": i.classification_confidence,
            "classification_detail": {k: v for k, v in (i.classification_detail or {}).items() if k != "ai_run_id"},
            "suggested_reply": i.suggested_reply, "suggested_action": i.suggested_action, "handled": i.handled,
            "external_thread_id": i.external_thread_id}


@router.get("")
def list_conversations(classification: str | None = None, direction: str | None = None, handled: bool | None = None,
                       company_id: uuid.UUID | None = None, pp: PageParams = Depends(), db: Session = Depends(get_db),
                       _: User = Depends(require_viewer)):
    stmt = select(Interaction)
    if classification:
        stmt = stmt.where(Interaction.classification == classification)
    if direction:
        stmt = stmt.where(Interaction.direction == direction)
    if handled is not None:
        stmt = stmt.where(Interaction.handled.is_(handled))
    if company_id:
        stmt = stmt.where(Interaction.company_id == company_id)
    stmt = stmt.order_by(Interaction.occurred_at.desc().nullslast())
    return paginate(db, stmt, pp, lambda i: inter_out(db, i))


@router.get("/{interaction_id}")
def get_conversation(interaction_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return inter_out(db, get_or_404(db, Interaction, interaction_id))


class InboundIn(BaseModel):
    company_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    channel: str = Field("email", pattern="^(email|linkedin|call|meeting|other)$")
    subject: str | None = Field(None, max_length=500)
    body: str = Field(min_length=1, max_length=20_000)
    occurred_at: datetime | None = None


@router.post("/inbound")
def log_inbound(body: InboundIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    """Record a reply received outside a connected mailbox (e.g. LinkedIn) and classify it."""
    c = get_or_404(db, Company, body.company_id)
    ct = get_or_404(db, Contact, body.contact_id) if body.contact_id else None
    if ct and ct.company_id != c.id:
        raise HTTPException(422, "Contact does not belong to this company")
    i = log_manual_inbound(db, company=c, contact=ct, channel=body.channel, subject=body.subject, body=body.body,
                           occurred_at=body.occurred_at, user=user)
    db.commit()
    return inter_out(db, i)


@router.post("/{interaction_id}/reclassify")
def reclassify(interaction_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    i = get_or_404(db, Interaction, interaction_id)
    c = db.get(Company, i.company_id) if i.company_id else None
    apply_classification(db, i, classify(db, i, c), user=user)
    db.commit()
    return inter_out(db, i)


class LabelIn(BaseModel):
    classification: str = Field(pattern="^(interested|meeting_requested|needs_information|objection|not_interested|"
                                        "unsubscribe|out_of_office|automatic_reply|unknown)$")


@router.post("/{interaction_id}/label")
def set_label(interaction_id: uuid.UUID, body: LabelIn, db: Session = Depends(get_db),
              user: User = Depends(require_operator)):
    i = get_or_404(db, Interaction, interaction_id)
    apply_classification(db, i, {"label": body.classification, "confidence": 1.0, "method": "human",
                                 "opt_out_requested": body.classification == "unsubscribe"}, user=user)
    db.commit()
    return inter_out(db, i)


@router.post("/{interaction_id}/handled")
def mark_handled(interaction_id: uuid.UUID, handled: bool = True, db: Session = Depends(get_db),
                 user: User = Depends(require_operator)):
    i = get_or_404(db, Interaction, interaction_id)
    i.handled = handled
    db.commit()
    return inter_out(db, i)
