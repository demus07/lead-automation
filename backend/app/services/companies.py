"""Company & contact upsert with deterministic deduplication."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.discovery.normalize import (
    clean_company_name,
    name_key,
    normalize_domain,
    normalize_email,
    normalize_url,
    split_name,
)
from app.models import Company, Contact, EmailStatus, LeadSource
from app.models.base import utcnow

# Ranking of decision-maker titles. Lower = higher priority.
ROLE_PRIORITY: list[tuple[int, tuple[str, ...]]] = [
    (1, ("founder", "co-founder", "cofounder")),
    (2, ("ceo", "chief executive", "managing director", "president", "owner")),
    (3, ("cto", "chief technology", "cio", "chief information", "chief digital")),
    (3, ("coo", "chief operating", "cmo", "chief marketing", "chief growth")),
    (4, ("head of marketing", "head of growth", "vp marketing", "vp of marketing", "vp growth",
         "director of marketing", "marketing director")),
    (4, ("vp operations", "vp of operations", "head of operations", "director of operations")),
    (4, ("director of digital", "head of digital", "digital director", "head of knowledge",
         "knowledge management", "head of brand", "brand director")),
    (5, ("head of", "vp", "vice president", "director", "partner")),
    (8, ("manager", "lead")),
]


def seniority_rank(title: str | None) -> int:
    t = (title or "").lower()
    for rank, keys in ROLE_PRIORITY:
        if any(k in t for k in keys):
            return rank
    return 99


@dataclass
class UpsertResult:
    company: Company
    created: bool
    matched_on: str | None = None


def find_company(db: Session, domain_norm: str | None, name: str | None) -> tuple[Company | None, str | None]:
    if domain_norm:
        c = db.scalar(select(Company).where(Company.domain_normalized == domain_norm, Company.deleted_at.is_(None)))
        if c:
            return c, "domain"
    if name:
        key = name_key(name)
        if key and len(key) >= 3:
            # only match domain-less records by name to avoid merging distinct companies sharing a name
            candidates = db.scalars(
                select(Company).where(func.lower(Company.name) == name.lower().strip(), Company.deleted_at.is_(None))
            ).all()
            for c in candidates:
                if c.domain_normalized is None or c.domain_normalized == domain_norm:
                    return c, "name"
    return None, None


def upsert_company(
    db: Session,
    *,
    name: str,
    domain: str | None = None,
    website: str | None = None,
    campaign_id: uuid.UUID | None = None,
    fields: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
) -> UpsertResult:
    fields = fields or {}
    domain_norm = normalize_domain(domain or website)
    existing, matched_on = find_company(db, domain_norm, name)
    if existing:
        # Fill only missing attributes — never overwrite human-edited data.
        for k in ("industry", "location", "country", "size_range", "description"):
            if fields.get(k) and not getattr(existing, k):
                setattr(existing, k, str(fields[k])[:2000])
        if domain_norm and not existing.domain_normalized:
            existing.domain_normalized = domain_norm
            existing.domain = domain_norm
            existing.website = normalize_url(website) or f"https://{domain_norm}"
        if fields.get("data"):
            existing.data = {**fields["data"], **(existing.data or {})}
        company, created = existing, False
    else:
        company = Company(
            name=clean_company_name(name) or (domain_norm or "Unknown"),
            domain=domain_norm,
            domain_normalized=domain_norm,
            website=normalize_url(website) or (f"https://{domain_norm}" if domain_norm else None),
            campaign_id=campaign_id,
            industry=_s(fields.get("industry"), 200),
            location=_s(fields.get("location"), 300),
            country=_s(fields.get("country"), 100),
            size_range=_s(fields.get("size_range"), 40),
            description=_s(fields.get("description"), 4000),
            tags=fields.get("tags") or [],
            data=fields.get("data") or {},
        )
        db.add(company)
        db.flush()
        created = True
    if source:
        db.add(LeadSource(company_id=company.id, campaign_id=campaign_id, **source))
    return UpsertResult(company, created, matched_on)


def _s(v: Any, n: int) -> str | None:
    if v is None or v == "":
        return None
    return str(v)[:n]


def upsert_contact(
    db: Session,
    company: Company | None,
    *,
    full_name: str,
    job_title: str | None = None,
    email: str | None = None,
    email_status: EmailStatus | None = None,
    profile_url: str | None = None,
    source_url: str | None = None,
    source_type: str = "website",
    confidence: float = 0.5,
    data: dict[str, Any] | None = None,
) -> tuple[Contact, bool]:
    email_norm = normalize_email(email)
    if email_status == EmailStatus.VERIFIED and source_type != "verification_provider":
        # Guard: only a mailbox-verification provider may assert "verified".
        email_status = EmailStatus.UNVERIFIED
    contact = None
    if email_norm:
        contact = db.scalar(select(Contact).where(Contact.email_normalized == email_norm, Contact.deleted_at.is_(None)))
    if contact is None and company is not None:
        contact = db.scalar(select(Contact).where(
            Contact.company_id == company.id, func.lower(Contact.full_name) == full_name.lower().strip(),
            Contact.deleted_at.is_(None)))
    if contact:
        if job_title and not contact.job_title:
            contact.job_title = job_title[:200]
            contact.seniority_rank = seniority_rank(job_title)
        if email_norm and not contact.email_normalized:
            contact.email = email.strip()
            contact.email_normalized = email_norm
            contact.email_status = email_status or EmailStatus.UNVERIFIED
        elif email_norm and email_status and _status_rank(email_status) > _status_rank(contact.email_status):
            # Upgrade only to a *stronger* status (never downgrade a provider verification).
            contact.email_status = email_status
        if profile_url and not contact.profile_url:
            contact.profile_url = profile_url
        contact.confidence = max(contact.confidence or 0, confidence)
        return contact, False
    first, last = split_name(full_name)
    contact = Contact(
        company_id=company.id if company else None,
        full_name=full_name.strip()[:200],
        first_name=first,
        last_name=last,
        job_title=(job_title or None) and job_title[:200],
        seniority_rank=seniority_rank(job_title),
        email=email.strip() if email_norm else None,
        email_normalized=email_norm,
        email_status=(email_status or EmailStatus.UNVERIFIED) if email_norm else EmailStatus.NONE,
        profile_url=profile_url,
        source_url=source_url,
        source_type=source_type,
        discovered_at=utcnow(),
        confidence=confidence,
        data=data or {},
    )
    db.add(contact)
    db.flush()
    return contact, True


_STATUS_ORDER = [EmailStatus.NONE, EmailStatus.INVALID, EmailStatus.UNVERIFIED, EmailStatus.DOMAIN_VALID,
                 EmailStatus.PUBLISHED, EmailStatus.VERIFIED]


def _status_rank(s: EmailStatus) -> int:
    return _STATUS_ORDER.index(s) if s in _STATUS_ORDER else 0
