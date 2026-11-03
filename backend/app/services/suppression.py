"""Suppression (do-not-contact) handling. Records are never deleted by retention jobs."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.discovery.normalize import normalize_domain, normalize_email
from app.models import Company, Contact, DraftStatus, LeadStatus, OutreachDraft, Suppression, User
from app.services.audit import audit
from app.services.state_machine import try_transition


def is_suppressed(db: Session, *, email: str | None = None, domain: str | None = None) -> Suppression | None:
    conds = []
    e = normalize_email(email)
    if e:
        conds.append((Suppression.kind == "email") & (Suppression.value == e))
        d = e.split("@", 1)[1]
        conds.append((Suppression.kind == "domain") & (Suppression.value == normalize_domain(d)))
    dn = normalize_domain(domain)
    if dn:
        conds.append((Suppression.kind == "domain") & (Suppression.value == dn))
    if not conds:
        return None
    return db.scalar(select(Suppression).where(Suppression.active.is_(True), or_(*conds)).limit(1))


def contact_suppressed(db: Session, contact: Contact | None, company: Company | None) -> Suppression | None:
    if contact is not None and contact.status == "do_not_contact":
        return Suppression(kind="contact", value=str(contact.id), reason="dnc")
    if company is not None and company.status == LeadStatus.DO_NOT_CONTACT:
        return Suppression(kind="company", value=str(company.id), reason="dnc")
    return is_suppressed(db, email=contact.email if contact else None,
                         domain=company.domain_normalized if company else None)


def suppress(
    db: Session,
    *,
    email: str | None = None,
    domain: str | None = None,
    reason: str = "manual",
    source: str | None = None,
    contact: Contact | None = None,
    company: Company | None = None,
    user: User | None = None,
    block_company: bool = False,
) -> list[Suppression]:
    """Add suppression entries and immediately block pending outreach."""
    created: list[Suppression] = []
    items: list[tuple[str, str]] = []
    e = normalize_email(email or (contact.email if contact else None))
    if e:
        items.append(("email", e))
    d = normalize_domain(domain)
    if d:
        items.append(("domain", d))
    for kind, value in items:
        row = db.scalar(select(Suppression).where(Suppression.kind == kind, Suppression.value == value))
        if row:
            row.active = True
            continue
        row = Suppression(kind=kind, value=value, reason=reason, source=source,
                          contact_id=contact.id if contact else None, company_id=company.id if company else None,
                          created_by_id=user.id if user else None)
        db.add(row)
        created.append(row)
    if contact is not None:
        contact.status = "do_not_contact"
    if company is not None and (block_company or d):
        try_transition(db, company, LeadStatus.DO_NOT_CONTACT, actor=user, reason=f"suppression:{reason}")
    # Block any drafts that have not yet become mailbox drafts.
    q = select(OutreachDraft).where(OutreachDraft.status.in_([
        DraftStatus.PENDING_APPROVAL, DraftStatus.NEEDS_REVIEW, DraftStatus.SAVED_FOR_LATER, DraftStatus.GENERATING,
        DraftStatus.APPROVED]))
    if contact is not None:
        q = q.where(OutreachDraft.contact_id == contact.id)
    elif company is not None:
        q = q.where(OutreachDraft.company_id == company.id)
    else:
        q = None
    if q is not None:
        for dr in db.scalars(q).all():
            dr.status = DraftStatus.BLOCKED
    audit(db, "suppression.added", actor=user, entity_type="contact" if contact else "company",
          entity_id=(contact.id if contact else company.id if company else None),
          detail={"items": items, "reason": reason, "source": source})
    db.flush()
    return created
