from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.api._common import PageParams, apply_sort, get_or_404, like, paginate
from app.core.db import get_db
from app.core.deps import require_operator, require_viewer
from app.discovery.normalize import normalize_email, normalize_url, split_name
from app.models import Company, Contact, EmailStatus, User
from app.models.base import utcnow
from app.schemas.common import Msg
from app.schemas.crm import ContactIn, ContactOut, ContactPatch, ContactWithCompany
from app.services.audit import audit
from app.services.companies import seniority_rank, upsert_contact
from app.services.csv_io import export_contacts
from app.services.suppression import is_suppressed, suppress

router = APIRouter(prefix="/api/contacts", tags=["contacts"])
SORTABLE = {"created_at", "full_name", "seniority_rank", "confidence", "discovered_at"}


def _out(c: Contact) -> dict:
    o = ContactWithCompany.model_validate(c)
    if c.company:
        o.company_name, o.company_domain = c.company.name, c.company.domain_normalized
    return o.model_dump()


def _filtered(q, company_id, email_status, has_email, status):
    stmt = select(Contact).options(joinedload(Contact.company)).where(Contact.deleted_at.is_(None))
    if q:
        stmt = stmt.outerjoin(Company, Company.id == Contact.company_id).where(or_(
            Contact.full_name.ilike(like(q)), Contact.email_normalized.ilike(like(q)),
            Contact.job_title.ilike(like(q)), Company.name.ilike(like(q))))
    if company_id:
        stmt = stmt.where(Contact.company_id == company_id)
    if email_status:
        stmt = stmt.where(Contact.email_status.in_([EmailStatus(s) for s in email_status]))
    if has_email is not None:
        stmt = stmt.where(Contact.email_normalized.is_not(None) if has_email else Contact.email_normalized.is_(None))
    if status:
        stmt = stmt.where(Contact.status == status)
    return stmt


@router.get("")
def list_contacts(q: str | None = Query(None, max_length=200), company_id: uuid.UUID | None = None,
                  email_status: list[str] | None = Query(None), has_email: bool | None = None,
                  status: str | None = None, sort: str | None = "seniority_rank", pp: PageParams = Depends(),
                  db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    stmt = apply_sort(_filtered(q, company_id, email_status, has_email, status), Contact, sort, SORTABLE)
    return paginate(db, stmt, pp, _out)


@router.get("/export")
def export(q: str | None = None, company_id: uuid.UUID | None = None, db: Session = Depends(get_db),
           user: User = Depends(require_viewer)):
    rows = db.scalars(_filtered(q, company_id, None, None, None).limit(50_000)).unique().all()
    audit(db, "export.contacts", actor=user)
    db.commit()
    return Response(export_contacts(rows), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=contacts.csv"})


@router.post("", response_model=ContactOut, status_code=201)
def create_contact(body: ContactIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    company = get_or_404(db, Company, body.company_id)
    if body.email and not normalize_email(body.email):
        raise HTTPException(422, "Invalid email address")
    if body.email and is_suppressed(db, email=body.email):
        raise HTTPException(409, "This email is on the suppression list")
    c, created = upsert_contact(db, company, full_name=body.full_name, job_title=body.job_title, email=body.email,
                                email_status=EmailStatus.UNVERIFIED if body.email else None,
                                profile_url=normalize_url(body.profile_url), source_url=body.source_url,
                                source_type="manual", confidence=0.9)
    if not created:
        raise HTTPException(409, "Contact already exists")
    audit(db, "contact.created", actor=user, entity_type="contact", entity_id=c.id)
    db.commit()
    return c


@router.get("/{contact_id}")
def get_contact(contact_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return _out(get_or_404(db, Contact, contact_id))


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: uuid.UUID, body: ContactPatch, db: Session = Depends(get_db),
                   user: User = Depends(require_operator)):
    c = get_or_404(db, Contact, contact_id)
    ch = body.model_dump(exclude_unset=True)
    if "full_name" in ch:
        c.full_name = ch["full_name"]
        c.first_name, c.last_name = split_name(ch["full_name"])
    if "job_title" in ch:
        c.job_title = ch["job_title"]
        c.seniority_rank = seniority_rank(ch["job_title"])
    if "email" in ch:
        e = normalize_email(ch["email"]) if ch["email"] else None
        if ch["email"] and not e:
            raise HTTPException(422, "Invalid email address")
        if e and is_suppressed(db, email=e):
            raise HTTPException(409, "This email is on the suppression list")
        if e != c.email_normalized:
            c.email, c.email_normalized = (ch["email"].strip() if e else None), e
            # A changed email is unverified until checked again.
            c.email_status = EmailStatus.UNVERIFIED if e else EmailStatus.NONE
            c.email_checked_at, c.email_check_detail = None, {}
    if "profile_url" in ch:
        c.profile_url = normalize_url(ch["profile_url"])
    if ch.get("is_primary"):
        for other in db.scalars(select(Contact).where(Contact.company_id == c.company_id, Contact.id != c.id)):
            other.is_primary = False
        c.is_primary = True
    elif ch.get("is_primary") is False:
        c.is_primary = False
    audit(db, "contact.updated", actor=user, entity_type="contact", entity_id=c.id, detail={"fields": list(ch)})
    db.commit()
    return c


@router.post("/{contact_id}/verify-email", response_model=ContactOut)
def verify_email(contact_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    from app.research.email_verify import check_contact_email

    c = get_or_404(db, Contact, contact_id)
    if not c.email_normalized:
        raise HTTPException(400, "Contact has no email")
    check_contact_email(db, c)
    db.commit()
    return c


class DNCIn(BaseModel):
    reason: str = Field("manual", max_length=60)
    note: str | None = Field(None, max_length=1000)


@router.post("/{contact_id}/do-not-contact", response_model=Msg)
def do_not_contact(contact_id: uuid.UUID, body: DNCIn, db: Session = Depends(get_db),
                   user: User = Depends(require_operator)):
    c = get_or_404(db, Contact, contact_id)
    suppress(db, email=c.email, reason=body.reason, source=body.note or "manual", contact=c, user=user)
    db.commit()
    return Msg(message="Contact added to suppression list")


@router.delete("/{contact_id}", response_model=Msg)
def delete_contact(contact_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    c = get_or_404(db, Contact, contact_id)
    c.deleted_at = utcnow()
    audit(db, "contact.deleted", actor=user, entity_type="contact", entity_id=c.id)
    db.commit()
    return Msg(message="Contact deleted")
