"""Builds the agency context injected into agent prompts from the editable agency profile and
approved, non-confidential knowledge items. Nothing about the agency is hard-coded."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeItem
from app.services import settings_service


def approved_knowledge(db: Session, service: str | None = None, limit: int = 12) -> list[KnowledgeItem]:
    stmt = select(KnowledgeItem).where(
        KnowledgeItem.deleted_at.is_(None), KnowledgeItem.approved_for_outreach.is_(True),
        KnowledgeItem.confidential.is_(False))
    items = db.scalars(stmt.order_by(KnowledgeItem.updated_at.desc()).limit(200)).all()
    if service:
        items = [i for i in items if i.service in (None, "", "both", service)]
    return items[:limit]


def agency_context(db: Session, service: str | None = None, include_knowledge: bool = True) -> str:
    p = settings_service.get_section(db, "agency_profile")
    lines = ["AGENCY CONTEXT (trusted, provided by the agency owner):"]
    if p.get("agency_name"):
        lines.append(f"Agency: {p['agency_name']} ({p.get('website') or 'no website set'})")
    if p.get("description"):
        lines.append(f"About: {p['description']}")
    for s in p.get("services", []):
        if s.get("enabled", True) and (service is None or s.get("key") == service):
            lines.append(f"Service [{s['key']}]: {s.get('name')} — {s.get('description') or 'no description set'}")
    if p.get("ideal_client_profile"):
        lines.append(f"Ideal client profile: {p['ideal_client_profile']}")
    if p.get("target_industries"):
        lines.append("Target industries: " + ", ".join(p["target_industries"]))
    if p.get("target_geographies"):
        lines.append("Target geographies: " + ", ".join(p["target_geographies"]))
    if p.get("typical_budgets"):
        lines.append(f"Typical project budgets: {p['typical_budgets']}")
    if p.get("tone"):
        lines.append(f"Preferred writing tone: {p['tone']}")
    if include_knowledge:
        cs = [c for c in p.get("case_studies", []) if service is None or c.get("service") in (None, "", service, "both")]
        for c in cs[:6]:
            lines.append(f"Approved case study: {c.get('title')} — {c.get('summary', '')} {c.get('url', '')}".strip())
        for t in [t for t in p.get("testimonials", []) if t.get("approved")][:4]:
            lines.append(f"Approved testimonial: \"{t.get('quote')}\" — {t.get('author')}, {t.get('company')}")
        for link in p.get("portfolio_links", [])[:6]:
            lines.append(f"Portfolio: {link}")
        for k in approved_knowledge(db, service):
            lines.append(f"Approved {k.kind}: {k.title} — {k.content[:500]}")
    lines.append("Only the approved material above may be referenced in outreach. Never disclose anything "
                 "else about the agency's clients.")
    return "\n".join(lines)
