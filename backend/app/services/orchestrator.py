"""Main Orchestrator: deterministic pipeline control + an optional AI-written brief for the approver.

The agent only *advises* a next action; deterministic code checks it against the lead state machine
and data preconditions before it is shown (it never triggers anything by itself)."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BuyingSignal, Company, Contact, LeadStatus, Opportunity
from app.models.base import utcnow
from app.research.service import latest_report

log = logging.getLogger(__name__)


def deterministic_next_action(db: Session, company: Company) -> tuple[str, str]:
    s = company.status
    if s in (LeadStatus.DO_NOT_CONTACT, LeadStatus.DISQUALIFIED):
        return "wait", "Lead is closed"
    if s in (LeadStatus.NEW, LeadStatus.RESEARCHING):
        return "research_more", "Not yet researched"
    has_email = db.scalar(select(Contact.id).where(Contact.company_id == company.id, Contact.deleted_at.is_(None),
                                                    Contact.email_normalized.is_not(None),
                                                    Contact.status == "active").limit(1))
    if s == LeadStatus.RESEARCHED:
        return ("qualify", "Researched, not yet scored") if company.last_scored_at is None else (
            "wait", "Scored: no opportunity above threshold")
    if s == LeadStatus.QUALIFIED:
        return ("draft", "Qualified with a contactable decision-maker") if has_email else (
            "find_contacts", "Qualified but no contact with a business email")
    return "wait", f"In {s.value}"


ALLOWED_FOR = {
    "research_more": {LeadStatus.NEW, LeadStatus.RESEARCHED, LeadStatus.QUALIFIED},
    "find_contacts": {LeadStatus.RESEARCHED, LeadStatus.QUALIFIED},
    "qualify": {LeadStatus.RESEARCHED},
    "draft": {LeadStatus.QUALIFIED},
    "disqualify": set(LeadStatus) - {LeadStatus.DO_NOT_CONTACT, LeadStatus.DISQUALIFIED},
    "wait": set(LeadStatus),
}


def write_brief(db: Session, company: Company, *, job_id=None) -> dict[str, Any]:
    from app.ai.agents.context import agency_context
    from app.ai.agents.schemas import OrchestratorOutput
    from app.ai.llm.providers import llm_available
    from app.ai.runtime import AgentFailed, AgentUnavailable, BudgetExceeded, load_prompt, run_agent
    from app.services import settings_service

    det_action, det_reason = deterministic_next_action(db, company)
    brief: dict[str, Any] = {"next_action": det_action, "reason": det_reason, "method": "deterministic",
                             "at": utcnow().isoformat()}
    report = latest_report(db, company.id)
    opp = db.scalar(select(Opportunity).where(Opportunity.company_id == company.id))
    if report:
        brief["lead_summary"] = report.summary
    if llm_available(settings_service.get_section(db, "llm")) and report:
        sigs = db.scalars(select(BuyingSignal).where(BuyingSignal.company_id == company.id,
                                                     BuyingSignal.confidence >= 0.5)).all()
        contacts = db.scalars(select(Contact).where(Contact.company_id == company.id, Contact.deleted_at.is_(None))
                              .order_by(Contact.seniority_rank).limit(5)).all()
        digest = (f"Company: {company.name} ({company.domain_normalized}), status {company.status.value}\n"
                  f"Research summary: {report.summary}\n"
                  f"Scores: website {opp.website_score if opp else '-'} (conf {opp.website_confidence if opp else '-'}), "
                  f"company brain {opp.brain_score if opp else '-'} (conf {opp.brain_confidence if opp else '-'}); "
                  f"recommended: {opp.recommended_service if opp else '-'} — {opp.recommendation_reason if opp else ''}\n"
                  f"Signals: " + "; ".join(f"{s.signal_type} ({s.freshness}): {s.description[:120]}" for s in sigs[:8]) +
                  "\nContacts: " + "; ".join(f"{c.full_name}, {c.job_title or '?'} (email: {c.email_status.value})"
                                             for c in contacts) +
                  f"\nDeterministic next action: {det_action} ({det_reason})")
        try:
            res = run_agent(db, agent="orchestrator",
                            system=load_prompt("orchestrator").replace("{agency_context}", agency_context(db, include_knowledge=False)),
                            user=digest, schema=OrchestratorOutput, tier="fast", company_id=company.id, job_id=job_id)
            o = res.output
            brief.update(lead_summary=o.lead_summary, open_questions=o.open_questions, method="llm",
                         ai_suggestion={"next_action": o.next_action, "reason": o.reason})
            if company.status in ALLOWED_FOR.get(o.next_action, set()):
                brief["next_action"], brief["reason"] = o.next_action, o.reason
        except (AgentUnavailable, AgentFailed, BudgetExceeded) as e:
            log.info("orchestrator brief skipped: %s", e)
    company.data = {**(company.data or {}), "brief": brief}
    db.flush()
    return brief
