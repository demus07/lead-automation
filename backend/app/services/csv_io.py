"""CSV import (companies + optional contacts in the same file) and export."""
from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.discovery.normalize import normalize_domain, normalize_email
from app.discovery.providers.base import size_bucket
from app.models import Company, Contact, EmailStatus
from app.services.companies import upsert_company, upsert_contact
from app.services.suppression import is_suppressed

MAX_ROWS = 20_000
ALIASES: dict[str, list[str]] = {
    "company": ["company", "company_name", "company name", "organization", "organisation", "account", "name"],
    "domain": ["domain", "website", "url", "company_website", "company website", "web", "site", "homepage"],
    "industry": ["industry", "sector", "vertical"],
    "location": ["location", "city", "hq", "headquarters", "address"],
    "country": ["country", "company_country"],
    "size": ["size", "company_size", "employees", "headcount", "employee_count", "team_size"],
    "description": ["description", "about", "summary"],
    "full_name": ["full_name", "full name", "contact_name", "contact name", "contact", "person"],
    "first_name": ["first_name", "first name", "firstname", "given name"],
    "last_name": ["last_name", "last name", "lastname", "surname", "family name"],
    "title": ["title", "job_title", "job title", "position", "role", "designation"],
    "email": ["email", "email_address", "email address", "work email", "business email"],
    "profile_url": ["linkedin", "linkedin_url", "profile_url", "profile", "linkedin profile"],
    "tags": ["tags", "labels"],
}


@dataclass
class ImportReport:
    rows: int = 0
    companies_created: int = 0
    companies_matched: int = 0
    contacts_created: int = 0
    contacts_matched: int = 0
    skipped: int = 0
    suppressed: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)
    company_ids: list[str] = field(default_factory=list)


def detect_mapping(headers: list[str]) -> dict[str, str]:
    norm = {h: h.strip().lower().replace("-", "_") for h in headers}
    mapping: dict[str, str] = {}
    for target, aliases in ALIASES.items():
        for h, n in norm.items():
            if n in aliases or n.replace("_", " ") in aliases:
                if h not in mapping.values():
                    mapping[target] = h
                    break
    # "name" is ambiguous: if a contact name column also exists, "name" means company.
    return mapping


def import_csv(db: Session, content: bytes, *, campaign_id: uuid.UUID | None = None,
               mapping: dict[str, str] | None = None, tags: list[str] | None = None) -> ImportReport:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    mapping = mapping or detect_mapping(headers)
    rep = ImportReport(mapping=mapping)
    if "company" not in mapping and "domain" not in mapping:
        rep.errors.append({"row": 0, "error": "CSV needs a company name or domain/website column"})
        return rep

    def get(row: dict, key: str) -> str:
        col = mapping.get(key)
        return (row.get(col) or "").strip() if col else ""

    for i, row in enumerate(reader, start=2):
        if rep.rows >= MAX_ROWS:
            rep.errors.append({"row": i, "error": f"Row limit {MAX_ROWS} reached"})
            break
        rep.rows += 1
        try:
            with db.begin_nested():  # savepoint per row
                name, website = get(row, "company"), get(row, "domain")
                domain = normalize_domain(website)
                if not name and not domain:
                    rep.skipped += 1
                    continue
                if is_suppressed(db, domain=domain):
                    rep.suppressed += 1
                    continue
                size = get(row, "size")
                if size.isdigit():
                    size = size_bucket(int(size)) or size
                row_tags = [t.strip() for t in get(row, "tags").split(",") if t.strip()] + (tags or [])
                res = upsert_company(
                    db, name=name or domain or "", domain=domain, website=website if domain else None,
                    campaign_id=campaign_id,
                    fields={"industry": get(row, "industry"), "location": get(row, "location"),
                            "country": get(row, "country"), "size_range": size, "description": get(row, "description"),
                            "tags": row_tags},
                    source={"provider": "csv", "source_type": "csv_import", "title": "CSV import",
                            "raw": {k: v for k, v in row.items() if k}},
                )
                if res.created:
                    rep.companies_created += 1
                    rep.company_ids.append(str(res.company.id))
                else:
                    rep.companies_matched += 1
                full = get(row, "full_name") or " ".join(x for x in [get(row, "first_name"), get(row, "last_name")] if x)
                email = get(row, "email")
                if full or email:
                    if email and not normalize_email(email):
                        rep.errors.append({"row": i, "error": f"Invalid email '{email}' ignored"})
                        email = ""
                    if email and is_suppressed(db, email=email):
                        rep.suppressed += 1
                        continue
                    _, created = upsert_contact(
                        db, res.company, full_name=full or email.split("@")[0], job_title=get(row, "title") or None,
                        email=email or None, email_status=EmailStatus.UNVERIFIED if email else None,
                        profile_url=get(row, "profile_url") or None, source_type="csv_import", confidence=0.6)
                    rep.contacts_created += int(created)
                    rep.contacts_matched += int(not created)
        except Exception as e:  # noqa: BLE001 - report row-level errors, continue import
            rep.errors.append({"row": i, "error": f"{type(e).__name__}: {e}"[:300]})
    db.flush()
    return rep


COMPANY_COLUMNS = ["id", "name", "domain", "website", "industry", "location", "country", "size_range", "status",
                   "website_score", "brain_score", "recommended_service", "tags", "created_at", "last_researched_at"]
CONTACT_COLUMNS = ["id", "company", "domain", "full_name", "job_title", "email", "email_status", "profile_url",
                   "source_url", "source_type", "confidence", "status", "discovered_at"]


def export_companies(companies: list[Company]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COMPANY_COLUMNS)
    for c in companies:
        w.writerow([_cell(c.id), _cell(c.name), c.domain_normalized, c.website, _cell(c.industry), _cell(c.location),
                    c.country, c.size_range, c.status.value, c.website_score, c.brain_score, c.recommended_service,
                    ",".join(c.tags or []), c.created_at.isoformat(),
                    c.last_researched_at.isoformat() if c.last_researched_at else ""])
    return buf.getvalue()


def export_contacts(contacts: list[Contact]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CONTACT_COLUMNS)
    for c in contacts:
        w.writerow([c.id, _cell(c.company.name if c.company else ""), c.company.domain_normalized if c.company else "",
                    _cell(c.full_name), _cell(c.job_title), c.email, c.email_status.value, c.profile_url, c.source_url,
                    c.source_type, c.confidence, c.status, c.discovered_at.isoformat() if c.discovered_at else ""])
    return buf.getvalue()


def _cell(v: Any) -> str:
    """Neutralise spreadsheet formula injection."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s
