"""Opportunity scoring: two independent 0–100 scores with deterministic aggregation.

The scoring agent (or the heuristic fallback) only supplies per-factor ratings (0–5) with evidence
ids. This module drops ratings without valid evidence, computes weighted scores and confidence,
and selects at most one recommended service — or none.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.sanitize import wrap_untrusted
from app.models import BuyingSignal, Campaign, Company, LeadScore, LeadStatus, Opportunity, ResearchReport
from app.models.base import utcnow
from app.research.evidence import EvidenceSet
from app.services import settings_service
from app.services.state_machine import try_transition

log = logging.getLogger(__name__)

WEBSITE_FACTORS = {
    "website_experience": 0.18, "brand_positioning": 0.14, "messaging": 0.12, "ux": 0.12, "conversion": 0.14,
    "product_presentation": 0.10, "growth_signals": 0.12, "agency_relevance": 0.08,
}
BRAIN_FACTORS = {
    "organisational_complexity": 0.18, "distributed_teams": 0.14, "knowledge_management_signals": 0.18,
    "collaboration_software": 0.14, "operational_complexity": 0.12, "information_retrieval": 0.12,
    "contextual_ai_use_cases": 0.12,
}
SERVICE_FACTORS = {"website": WEBSITE_FACTORS, "company_brain": BRAIN_FACTORS}


@dataclass
class ServiceScore:
    service: str
    score: int
    confidence: float
    factors: list[dict[str, Any]]
    explanation: str
    sales_angle: str | None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    method: str = "llm"


def aggregate(service: str, ratings: list[dict[str, Any]], ev: EvidenceSet, method: str) -> tuple[int, float, list[dict]]:
    weights = SERVICE_FACTORS[service]
    by_name = {r["factor"]: r for r in ratings if r.get("factor") in weights}
    total, covered, factors = 0.0, 0.0, []
    for name, w in weights.items():
        r = by_name.get(name, {"factor": name, "rating": None, "evidence_ids": [], "rationale": "not assessed"})
        ids = ev.valid_ids(r.get("evidence_ids") or [])
        rating = r.get("rating")
        note = None
        if rating is not None and not ids:
            note = "rating discarded: no valid evidence cited"
            rating = None
        if rating is not None:
            rating = max(0, min(5, int(rating)))
            total += w * rating / 5
            covered += w
        factors.append({"factor": name, "weight": w, "rating": rating, "evidence_ids": ids,
                        "rationale": (r.get("rationale") or "")[:400], **({"validation": note} if note else {})})
    score = round(100 * total / sum(weights.values()))
    quality = 1.0 if method == "llm" else 0.8
    confidence = round(min(1.0, covered / sum(weights.values())) * quality, 2)
    return score, confidence, factors


def recommend(website: ServiceScore, brain: ServiceScore, scfg: dict, target_service: str = "any") -> tuple[str, str]:
    th = int(scfg.get("qualification_threshold", 60))
    margin = int(scfg.get("service_margin", 10))
    min_conf = float(scfg.get("min_confidence", 0.35))
    cands = []
    for s in (website, brain):
        if target_service not in ("any", s.service):
            continue
        if s.score >= th and s.confidence >= min_conf:
            cands.append(s)
    if not cands:
        best = max((website, brain), key=lambda s: s.score)
        why = (f"No opportunity: best score {best.score} ({best.service}) below threshold {th}"
               if best.score < th else f"No opportunity: confidence {best.confidence} below {min_conf}")
        if target_service != "any":
            why += f" (campaign targets {target_service} only)"
        return "none", why
    if len(cands) == 1:
        s = cands[0]
        return s.service, f"{s.service} score {s.score} ≥ {th} with confidence {s.confidence}"
    a, b = sorted(cands, key=lambda s: (s.score, s.confidence), reverse=True)
    if a.score - b.score >= margin:
        return a.service, f"{a.service} ({a.score}) leads {b.service} ({b.score}) by ≥{margin}"
    # Both qualify and are close: pick the better-evidenced one, never both.
    pick = a if a.confidence >= b.confidence else b
    return pick.service, (f"Both services qualify ({a.service} {a.score}, {b.service} {b.score}); "
                          f"recommending {pick.service} as it is better evidenced (confidence {pick.confidence})")


def evidence_for(report: ResearchReport | None, signals: list[BuyingSignal], company: Company | None = None,
                 db: Session | None = None) -> EvidenceSet:
    ev = EvidenceSet()
    if company is not None and (company.size_range or company.location or company.industry):
        src_url = None
        if db is not None:
            from app.models import LeadSource

            src = db.scalar(select(LeadSource).where(LeadSource.company_id == company.id,
                                                     LeadSource.source_url.is_not(None)).limit(1))
            src_url = src.source_url if src else None
        ev.add("C1", "company_record", src_url,
               f"Company record (from discovery source): size {company.size_range or 'unknown'}; industry "
               f"{company.industry or 'unknown'}; location {company.location or 'unknown'}")
    if report:
        for p in report.pages:
            head = " | ".join(h["text"] for h in p.get("headings", [])[:12])
            ev.add(p["id"], "page", p["final_url"],
                   f"TITLE: {p.get('title')}\nMETA: {p.get('meta_description')}\nHEADINGS: {head}\n"
                   f"TOOLS MENTIONED: {', '.join(p.get('tools_mentioned', []))}\n\n{(p.get('text') or '')[:3500]}",
                   title=p.get("title"), page_kind=p.get("kind"))
        for c in report.audit.get("checks", []):
            ev.add(f"A:{c['id']}", "audit", c["evidence_url"],
                   f"{c['label']}: {'pass' if c['passed'] else 'fail' if c['passed'] is False else 'n/a'} "
                   f"(value: {str(c['value'])[:150]})")
    usable = [s for s in signals if s.confidence >= 0.5]
    for i, s in enumerate(usable, start=1):
        roles = ", ".join((s.data or {}).get("roles", [])[:15])
        ev.add(f"S{i}", "signal", s.source_url,
               f"[{s.signal_type}] {s.description} (published: {s.published_at.date() if s.published_at else 'unknown'}"
               f", freshness: {s.freshness}){' Roles: ' + roles if roles else ''}", signal_id=str(s.id),
               signal_type=s.signal_type, freshness=s.freshness)
    return ev


def _current(s: dict) -> bool:
    return s.get("freshness") in ("fresh", "recent")


def heuristic_ratings(company: Company, report: ResearchReport | None, ev: EvidenceSet, agency: dict) -> dict:
    checks = {c["id"]: c for c in (report.audit.get("checks", []) if report else [])}

    def fails(*ids):
        present = [i for i in ids if i in checks and checks[i]["passed"] is not None]
        failed = [i for i in present if checks[i]["passed"] is False]
        return present, failed

    def rate(ids, scale=5):
        present, failed = fails(*ids)
        if not present:
            return None, []
        return round(scale * len(failed) / len(present)), [f"A:{i}" for i in present]

    w: list[dict] = []
    for factor, ids in [("website_experience", ("img_alt", "html_weight", "script_count", "ttfb", "viewport", "https")),
                        ("brand_positioning", ("og_tags", "title", "structured_data")),
                        ("messaging", ("meta_description", "single_h1")),
                        ("ux", ("nav_size", "lang")),
                        ("conversion", ("primary_cta", "contact_path", "form_length", "social_proof")),
                        ("product_presentation", ("content_depth",))]:
        r, e = rate(ids)
        w.append({"factor": factor, "rating": r, "evidence_ids": e, "rationale": "Share of failed measurable checks"})
    sigs = [it for it in ev.items.values() if it["kind"] == "signal"]
    growth = [s for s in sigs if s.get("signal_type") in ("funding", "expansion", "product_launch", "rebrand", "growth")
              and _current(s)]
    w.append({"factor": "growth_signals", "rating": min(5, 2 + 2 * len(growth)) if growth else None,
              "evidence_ids": [s["id"] for s in growth][:4], "rationale": f"{len(growth)} current growth signals"})
    inds = [i.lower() for i in agency.get("target_industries", [])]
    rel = company.industry and inds and any(i in company.industry.lower() for i in inds)
    w.append({"factor": "agency_relevance", "rating": 3 if rel else None, "evidence_ids": ["P1"] if rel and "P1" in ev.items else [],
              "rationale": "Industry matches agency targets" if rel else "unknown"})

    b: list[dict] = []
    size_r = {"1-10": 0, "11-50": 1, "51-200": 3, "201-500": 4, "501-1000": 4, "1001-5000": 5, "5001+": 5}.get(
        company.size_range or "")
    size_ev = ["C1"] if "C1" in ev.items and company.size_range else []
    b.append({"factor": "organisational_complexity", "rating": size_r, "evidence_ids": size_ev if size_r is not None else [],
              "rationale": f"Company size {company.size_range or 'unknown'} (from source data)"})
    b.append({"factor": "operational_complexity", "rating": size_r, "evidence_ids": size_ev if size_r is not None else [],
              "rationale": "Proxy: company size"})
    hiring = [s for s in sigs if s.get("signal_type") == "hiring"]
    km = [s for s in hiring if any(k in s["text"].lower() for k in ("knowledge", "operations", "enablement", "chief of staff"))]
    b.append({"factor": "knowledge_management_signals", "rating": 4 if km else None,
              "evidence_ids": [s["id"] for s in km][:3], "rationale": "Hiring ops/knowledge roles" if km else "none found"})
    tools = sorted({t for p in (report.pages if report else []) for t in p.get("tools_mentioned", [])})
    tool_pages = [p["id"] for p in (report.pages if report else []) if p.get("tools_mentioned")]
    b.append({"factor": "collaboration_software", "rating": min(5, len(tools) + 1) if tools else None,
              "evidence_ids": tool_pages[:3], "rationale": f"Mentions: {', '.join(tools)}" if tools else "none found"})
    multi = [p["id"] for p in (report.pages if report else []) if any(
        k in (p.get("text") or "").lower() for k in ("offices in", "remote-first", "fully remote", "distributed team",
                                                     "across time zones"))]
    b.append({"factor": "distributed_teams", "rating": 3 if multi else None, "evidence_ids": multi[:2],
              "rationale": "Site mentions multiple offices / remote teams" if multi else "none found"})
    b.append({"factor": "information_retrieval", "rating": None, "evidence_ids": [], "rationale": "needs AI analysis"})
    b.append({"factor": "contextual_ai_use_cases", "rating": None, "evidence_ids": [], "rationale": "needs AI analysis"})
    return {"website": w, "company_brain": b}


def score_company(db: Session, company: Company, *, job_id=None) -> Opportunity:
    from app.ai.agents.context import agency_context
    from app.ai.agents.schemas import ScoringOutput
    from app.ai.llm.providers import llm_available
    from app.ai.runtime import AgentFailed, AgentUnavailable, BudgetExceeded, load_prompt, run_agent

    scfg = settings_service.get_section(db, "scoring")
    agency = settings_service.get_section(db, "agency_profile")
    report = db.scalar(select(ResearchReport).where(ResearchReport.company_id == company.id)
                       .order_by(ResearchReport.created_at.desc()).limit(1))
    signals = db.scalars(select(BuyingSignal).where(BuyingSignal.company_id == company.id)).all()
    ev = evidence_for(report, list(signals), company, db)
    method, ai_run_id = "heuristic", None
    ratings: dict[str, Any] = {}
    texts: dict[str, dict] = {"website": {}, "company_brain": {}}
    if llm_available(settings_service.get_section(db, "llm")) and report and report.pages:
        blocks = "\n\n".join(f"[{i}] ({it['kind']}) {it.get('url')}\n" + (
            wrap_untrusted(it["text"], source=it.get("url") or i, max_chars=3500) if it["kind"] == "page" else it["text"])
            for i, it in ev.items.items())
        observations = "\n".join(f"- ({o['category']}) {o['text']} {o.get('evidence_ids')}" for o in report.observations[:40])
        user = (f"Company: {company.name} ({company.domain_normalized}); industry: {company.industry or 'unknown'}; "
                f"size: {company.size_range or 'unknown'}; location: {company.location or 'unknown'}\n"
                f"Research summary: {report.summary}\n\nValidated observations:\n{observations}\n\nEVIDENCE:\n{blocks}")
        system = load_prompt("opportunity_scoring").replace("{agency_context}", agency_context(db))
        try:
            res = run_agent(db, agent="opportunity_scoring", system=system, user=user, schema=ScoringOutput,
                            tier="smart", company_id=company.id, job_id=job_id, max_tokens=2500)
            out = res.output
            ratings = {"website": [f.model_dump() for f in out.website.factors],
                       "company_brain": [f.model_dump() for f in out.company_brain.factors]}
            texts = {"website": {"explanation": out.website.explanation, "sales_angle": out.website.sales_angle},
                     "company_brain": {"explanation": out.company_brain.explanation,
                                       "sales_angle": out.company_brain.sales_angle}}
            method, ai_run_id = "llm", res.run_id
        except (AgentUnavailable, BudgetExceeded, AgentFailed) as e:
            log.info("scoring agent unavailable for %s: %s", company.name, e)
    if not ratings:
        ratings = heuristic_ratings(company, report, ev, agency)

    scores: dict[str, ServiceScore] = {}
    for svc in ("website", "company_brain"):
        sc, conf, factors = aggregate(svc, ratings[svc], ev, method)
        used = sorted({i for f in factors for i in f["evidence_ids"]})
        expl = texts[svc].get("explanation") or _heuristic_expl(svc, factors)
        scores[svc] = ServiceScore(svc, sc, conf, factors, expl, texts[svc].get("sales_angle"),
                                   [{"id": i, "url": ev.items[i].get("url"), "kind": ev.items[i]["kind"],
                                     "excerpt": ev.items[i]["text"][:300]} for i in used], method)
    target = "any"
    if company.campaign_id:
        camp = db.get(Campaign, company.campaign_id)
        target = camp.target_service if camp else "any"
    rec, reason = recommend(scores["website"], scores["company_brain"], scfg, target)

    for s in scores.values():
        db.add(LeadScore(company_id=company.id, service=s.service, score=s.score, confidence=s.confidence,
                         factors=s.factors, explanation=s.explanation, evidence=s.evidence,
                         sales_angle=s.sales_angle, method=s.method, ai_run_id=ai_run_id))
    opp = db.scalar(select(Opportunity).where(Opportunity.company_id == company.id))
    if opp is None:
        opp = Opportunity(company_id=company.id)
        db.add(opp)
    w, b = scores["website"], scores["company_brain"]
    opp.website_score, opp.website_confidence, opp.website_explanation = w.score, w.confidence, w.explanation
    opp.brain_score, opp.brain_confidence, opp.brain_explanation = b.score, b.confidence, b.explanation
    opp.recommended_service, opp.recommendation_reason = rec, reason
    opp.sales_angle = scores[rec].sales_angle if rec in scores else None
    opp.evidence = (scores[rec].evidence if rec in scores else w.evidence + b.evidence)[:30]
    opp.method = method
    opp.research_report_id = report.id if report else None
    company.website_score, company.brain_score, company.recommended_service = w.score, b.score, rec
    company.last_scored_at = utcnow()
    if rec != "none":
        try_transition(db, company, LeadStatus.QUALIFIED, reason=reason)
    db.flush()
    return opp


def _heuristic_expl(svc: str, factors: list[dict]) -> str:
    rated = [f for f in factors if f["rating"] is not None]
    if not rated:
        return "Insufficient evidence to assess this service."
    top = sorted(rated, key=lambda f: -f["rating"] * f["weight"])[:3]
    return "Heuristic assessment from measurable checks and signals: " + "; ".join(
        f"{f['factor'].replace('_', ' ')} {f['rating']}/5 ({f['rationale']})" for f in top)
