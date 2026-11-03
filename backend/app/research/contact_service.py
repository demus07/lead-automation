"""Contact discovery for a company from its official pages (and optional AI extraction)."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.ai.sanitize import wrap_untrusted
from app.core import http as core_http
from app.discovery.normalize import normalize_domain
from app.models import Company, EmailStatus
from app.models.base import utcnow
from app.research.contacts import PersonCandidate, _is_name, attach_emails, extract_people, generic_emails
from app.research.email_verify import check_contact_email
from app.research.evidence import quote_in
from app.research.extractor import extract
from app.research.fetcher import fetch
from app.research.service import latest_report
from app.services import settings_service
from app.services.companies import upsert_contact
from app.services.suppression import is_suppressed

log = logging.getLogger(__name__)
CONTACT_PAGE_KINDS = ("team", "about", "contact", "home")


def find_contacts(db: Session, company: Company, *, job_id=None) -> dict[str, Any]:
    from app.ai.llm.providers import llm_available

    report = latest_report(db, company.id)
    stats = {"pages": 0, "candidates": 0, "created": 0, "updated": 0, "emails_published": 0, "ai_used": False}
    if not report or not report.pages:
        stats["note"] = "No research pages available; run research first."
        return stats
    rcfg = settings_service.get_section(db, "research")
    llm_on = llm_available(settings_service.get_section(db, "llm"))
    pages = [p for p in report.pages if p.get("kind") in CONTACT_PAGE_KINDS]
    company_domain = company.domain_normalized
    candidates: list[PersonCandidate] = []
    all_emails: set[str] = set()
    with core_http.client(timeout=20) as http:
        for p in pages:
            res = fetch(db, p["final_url"], http=http, min_delay=float(rcfg["request_delay_seconds"]),
                        max_age_days=int(rcfg["recrawl_after_days"]))
            if not res.ok:
                continue
            stats["pages"] += 1
            pd = extract(res.html or "", res.url, res.final_url)
            pd.kind = p.get("kind") or "home"
            # only addresses on the company's own domain count as business contact details
            pd.emails = [e for e in pd.emails if normalize_domain(e) == company_domain]
            all_emails.update(pd.emails)
            found = extract_people(pd, res.html or "")
            if llm_on and p.get("kind") in ("team", "about") and len(found) < 3:
                found += _ai_people(db, company, pd, job_id)
                stats["ai_used"] = True
            candidates += found
    # merge by name keeping the highest-confidence version
    merged: dict[str, PersonCandidate] = {}
    for c in candidates:
        k = c.full_name.lower()
        if k not in merged or c.confidence > merged[k].confidence:
            merged[k] = c
    people = list(merged.values())
    attach_emails(people, sorted(all_emails))
    stats["candidates"] = len(people)
    for c in people:
        if c.email and is_suppressed(db, email=c.email):
            c.email = None
        contact, created = upsert_contact(
            db, company, full_name=c.full_name, job_title=c.job_title, email=c.email,
            email_status=EmailStatus.PUBLISHED if c.email else None, profile_url=c.profile_url,
            source_url=c.source_url, source_type=f"website:{c.method}", confidence=c.confidence,
            data={"method": c.method})
        stats["created" if created else "updated"] += 1
        if c.email:
            stats["emails_published"] += 1
            if not contact.email_checked_at:
                try:
                    check_contact_email(db, contact)
                except Exception as e:  # noqa: BLE001 - DNS issues shouldn't fail the workflow
                    log.info("email check failed: %s", e)
    company.data = {**(company.data or {}), "public_emails": generic_emails(sorted(all_emails))}
    company.last_contacts_at = utcnow()
    db.flush()
    return stats


def _ai_people(db: Session, company: Company, pd, job_id) -> list[PersonCandidate]:
    from app.ai.agents.schemas import ContactResearchOutput
    from app.ai.runtime import AgentFailed, AgentUnavailable, BudgetExceeded, load_prompt, run_agent

    user = f"Company: {company.name}\nPage: {pd.final_url}\n" + wrap_untrusted(pd.text, source=pd.final_url,
                                                                                 max_chars=8000)
    try:
        res = run_agent(db, agent="contact_research", system=load_prompt("contact_research"), user=user,
                        schema=ContactResearchOutput, tier="fast", company_id=company.id, job_id=job_id)
    except (AgentUnavailable, AgentFailed, BudgetExceeded) as e:
        log.info("contact agent skipped: %s", e)
        return []
    out = []
    for p in res.output.people:
        # deterministic validation: name and quote must be on the page
        if not _is_name(p.full_name) or not quote_in(p.full_name, pd.text) or not quote_in(p.quote, pd.text):
            continue
        if p.full_name.lower() not in p.quote.lower():
            continue
        title = p.job_title if p.job_title and quote_in(p.job_title, pd.text) else None
        out.append(PersonCandidate(p.full_name, title, pd.final_url, "ai_extraction", 0.55))
    return out
