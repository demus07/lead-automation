"""Outreach draft generation → quality gate → approval queue. Never sends anything."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.sanitize import wrap_untrusted
from app.models import (
    BuyingSignal,
    Company,
    Contact,
    DraftStatus,
    EmailStatus,
    LeadStatus,
    Opportunity,
    OutreachDraft,
    User,
)
from app.research.evidence import EvidenceSet
from app.research.service import latest_report
from app.services import settings_service
from app.services.audit import audit
from app.services.quality import evaluate
from app.services.scoring import evidence_for
from app.services.state_machine import OUTREACH_BLOCKED, try_transition
from app.services.suppression import contact_suppressed

log = logging.getLogger(__name__)
ACTIVE_DRAFT_STATES = [DraftStatus.GENERATING, DraftStatus.NEEDS_REVIEW, DraftStatus.PENDING_APPROVAL,
                       DraftStatus.SAVED_FOR_LATER, DraftStatus.APPROVED]
SENDABLE_EMAIL = [EmailStatus.VERIFIED, EmailStatus.PUBLISHED, EmailStatus.DOMAIN_VALID, EmailStatus.UNVERIFIED]


class OutreachBlocked(Exception):
    """A deterministic precondition prevents drafting (suppression, no contact, no opportunity…)."""


def pick_contact(db: Session, company: Company) -> Contact | None:
    rows = db.scalars(select(Contact).where(
        Contact.company_id == company.id, Contact.deleted_at.is_(None), Contact.status == "active",
        Contact.email_normalized.is_not(None), Contact.email_status.in_(SENDABLE_EMAIL))).all()
    order = {EmailStatus.VERIFIED: 0, EmailStatus.PUBLISHED: 1, EmailStatus.DOMAIN_VALID: 2, EmailStatus.UNVERIFIED: 3}
    rows = sorted(rows, key=lambda c: (not c.is_primary, c.seniority_rank, order.get(c.email_status, 9), -c.confidence))
    for c in rows:
        if not contact_suppressed(db, c, company):
            return c
    return None


def build_evidence(db: Session, company: Company) -> EvidenceSet:
    report = latest_report(db, company.id)
    signals = db.scalars(select(BuyingSignal).where(BuyingSignal.company_id == company.id)).all()
    return evidence_for(report, list(signals), company, db)


def generate_draft(db: Session, company: Company, *, contact: Contact | None = None, user: User | None = None,
                   regeneration_notes: str | None = None, previous: OutreachDraft | None = None,
                   job_id=None) -> OutreachDraft:
    from app.ai.agents.context import agency_context
    from app.ai.agents.schemas import OutreachOutput
    from app.ai.runtime import load_prompt, run_agent

    if company.status in OUTREACH_BLOCKED:
        raise OutreachBlocked(f"Company status {company.status.value} does not allow outreach")
    opp = db.scalar(select(Opportunity).where(Opportunity.company_id == company.id))
    if not opp or opp.recommended_service in (None, "none"):
        raise OutreachBlocked("No recommended service for this company")
    contact = contact or pick_contact(db, company)
    if contact is None:
        raise OutreachBlocked("No contactable decision-maker with a business email")
    sup = contact_suppressed(db, contact, company)
    if sup is not None:
        raise OutreachBlocked(f"Recipient is suppressed ({sup.reason})")
    if previous is None:
        existing = db.scalar(select(OutreachDraft).where(
            OutreachDraft.company_id == company.id, OutreachDraft.deleted_at.is_(None),
            OutreachDraft.status.in_(ACTIVE_DRAFT_STATES)))
        if existing:
            raise OutreachBlocked("An active draft already exists for this company")

    profile = settings_service.get_section(db, "agency_profile")
    qcfg = settings_service.get_section(db, "quality")
    service = opp.recommended_service
    ev = build_evidence(db, company)
    report = latest_report(db, company.id)
    used_ids = [e["id"] for e in (opp.evidence or [])]
    ev_lines = []
    for i, it in ev.items.items():
        txt = it["text"][:1800] if it["kind"] == "page" else it["text"][:400]
        ev_lines.append(f"[{i}] ({it['kind']}) {it.get('url') or ''}\n" +
                        (wrap_untrusted(txt, source=it.get("url") or i) if it["kind"] == "page" else txt))
    sender = profile.get("sender_name") or "the agency founder"
    user_msg = (
        f"Write outreach for service: {service}\n"
        f"Recipient: {contact.full_name} — {contact.job_title or 'role unknown'} at {company.name}\n"
        f"Sender: {sender}, {profile.get('sender_title') or ''} at {profile.get('agency_name') or 'the agency'}\n"
        f"Signature block to end with:\n{profile.get('signature') or sender}\n"
        f"Preferred call to action: {profile.get('call_to_action')}\n"
        + (f"Opt-out line to include verbatim before the signature: {profile.get('opt_out_line')}\n"
           if profile.get("include_opt_out_line") else "")
        + f"\nWhy this service was recommended: {opp.recommendation_reason}\n"
        f"Suggested sales angle (evidence-backed): {opp.sales_angle or 'none'}\n"
        f"Most relevant evidence ids: {', '.join(used_ids[:12]) or 'see below'}\n"
        f"Research summary: {report.summary if report else ''}\n"
        + (f"\nREVISION REQUEST from reviewer (trusted): {regeneration_notes}\n" if regeneration_notes else "")
        + "\nEVIDENCE (cite ids in claims):\n" + "\n\n".join(ev_lines)
    )
    system = load_prompt("outreach_generation").replace("{agency_context}", agency_context(db, service))
    res = run_agent(db, agent="outreach_generation", system=system, user=user_msg, schema=OutreachOutput,
                    tier="smart", company_id=company.id, job_id=job_id, use_cache=False, max_tokens=2000)
    o = res.output
    draft = OutreachDraft(
        company_id=company.id, contact_id=contact.id, campaign_id=company.campaign_id, service=service,
        status=DraftStatus.GENERATING, version=(previous.version + 1) if previous else 1,
        subject=o.subject.strip(), body=o.body.strip(), opening_line=o.opening_line,
        linkedin_connection_note=o.linkedin_connection_note, linkedin_message=o.linkedin_message,
        recommended_offer=o.recommended_offer, personalisation_explanation=o.personalisation_explanation,
        evidence=[{"text": c.text, "evidence_ids": ev.valid_ids(c.evidence_ids),
                   "declared_ids": c.evidence_ids,
                   "sources": [{"id": i, "url": ev.items[i].get("url"), "excerpt": ev.items[i]["text"][:240]}
                               for i in ev.valid_ids(c.evidence_ids)]} for c in o.claims],
        confidence=o.confidence, regeneration_count=(previous.regeneration_count + 1) if previous else 0,
        regeneration_notes=regeneration_notes, ai_run_ids=[str(res.run_id)],
    )
    draft.original = {k: getattr(draft, k) for k in ("subject", "body", "linkedin_connection_note", "linkedin_message")}
    db.add(draft)
    db.flush()
    score, qreport = evaluate(db, draft, company, contact, ev, [c.model_dump() for c in o.claims], job_id=job_id)
    draft.quality_score, draft.quality_report = score, qreport
    if previous is not None:
        previous.status = DraftStatus.SUPERSEDED
    if qreport["passed"]:
        draft.status = DraftStatus.PENDING_APPROVAL
        try_transition(db, company, LeadStatus.DRAFT_GENERATED, reason="draft generated")
        try_transition(db, company, LeadStatus.PENDING_APPROVAL, reason="draft passed quality")
    elif draft.regeneration_count < int(qcfg["max_regenerations"]):
        db.flush()
        notes = "Fix these quality issues: " + "; ".join(i["text"] for i in qreport["issues"]
                                                          if i["severity"] in ("high", "medium"))[:1500]
        return generate_draft(db, company, contact=contact, user=user, regeneration_notes=notes, previous=draft,
                              job_id=job_id)
    else:
        draft.status = DraftStatus.NEEDS_REVIEW  # manual research / editing required
        try_transition(db, company, LeadStatus.DRAFT_GENERATED, reason="draft needs review")
    audit(db, "draft.generated", actor=user, actor_type=None if user else "agent", entity_type="outreach_draft",
          entity_id=draft.id, detail={"quality": score, "status": draft.status.value, "version": draft.version})
    db.flush()
    return draft


def recheck_quality(db: Session, draft: OutreachDraft) -> tuple[int, dict[str, Any]]:
    """Re-run deterministic checks after a human edit (no AI call)."""
    company = db.get(Company, draft.company_id)
    contact = db.get(Contact, draft.contact_id) if draft.contact_id else None
    ev = build_evidence(db, company)
    score, rep = evaluate(db, draft, company, contact, ev, draft.evidence, use_ai=False)
    rep["after_human_edit"] = True
    return score, rep
