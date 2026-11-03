from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.api._common import PageParams, paginate
from app.ai.llm.providers import llm_available
from app.ai.runtime import ai_status
from app.core.db import get_db
from app.core.deps import require_admin, require_viewer
from app.models import AIRun, Company, User
from app.services import settings_service

router = APIRouter(prefix="/api/ai", tags=["ai"])

AGENTS = [
    {"name": "discovery", "label": "Discovery Agent", "tier": "fast",
     "responsibility": "Extract companies named in news/search results (company names must be quoted from the text).",
     "output": "DiscoveryOutput"},
    {"name": "contact_research", "label": "Contact Research Agent", "tier": "fast",
     "responsibility": "Extract people and titles from official team/about pages; names and quotes verified against the page.",
     "output": "ContactResearchOutput"},
    {"name": "website_research", "label": "Website Research Agent", "tier": "smart",
     "responsibility": "Analyse positioning, messaging, UX, conversion; every observation categorised and evidence-checked.",
     "output": "WebsiteResearchOutput"},
    {"name": "business_signal", "label": "Business Signal Agent", "tier": "fast",
     "responsibility": "Classify news items as signals and reject items about other companies.",
     "output": "BusinessSignalOutput"},
    {"name": "opportunity_scoring", "label": "Opportunity Scoring Agent", "tier": "smart",
     "responsibility": "Rate evidence-backed factors for each service; code computes scores and the recommendation.",
     "output": "ScoringOutput"},
    {"name": "outreach_generation", "label": "Outreach Generation Agent", "tier": "smart",
     "responsibility": "Write email + LinkedIn drafts for one service, declaring every factual claim with evidence ids.",
     "output": "OutreachOutput"},
    {"name": "outreach_quality", "label": "Outreach Quality Agent", "tier": "smart",
     "responsibility": "Review drafts for unsupported claims, tone, service fit and CTA (combined with deterministic checks).",
     "output": "QualityOutput"},
    {"name": "reply_classification", "label": "Reply Classification Agent", "tier": "fast",
     "responsibility": "Classify replies and suggest responses; opt-outs are also caught by deterministic rules.",
     "output": "ReplyOutput"},
    {"name": "orchestrator", "label": "Main Orchestrator Agent", "tier": "fast",
     "responsibility": "Write the approver brief and advise a next action, which code validates against the state machine.",
     "output": "OrchestratorOutput"},
]


@router.get("/status")
def status(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    cfg = settings_service.get_section(db, "llm")
    return {**ai_status(db), "model_fast": cfg["model_fast"], "model_smart": cfg["model_smart"],
            "max_calls_per_company": cfg["max_calls_per_company"], "agents": AGENTS,
            "mode": "full" if llm_available(cfg) else "limited",
            "limited_mode_effects": [] if llm_available(cfg) else [
                "Website analysis uses deterministic checks only", "Scoring uses the transparent heuristic scorer",
                "Outreach drafts cannot be generated", "Replies are classified by rules only"]}


@router.post("/test")
def test_llm(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from pydantic import BaseModel

    from app.ai.runtime import AgentFailed, AgentUnavailable, BudgetExceeded, run_agent

    class Ping(BaseModel):
        ok: bool
        message: str

    try:
        res = run_agent(db, agent="connection_test", system="You are a connectivity test.",
                        user='Reply with {"ok": true, "message": "pong"}.', schema=Ping, tier="fast", use_cache=False,
                        max_tokens=100)
        db.commit()
        return {"ok": True, "model": res.model, "message": res.output.message}
    except (AgentUnavailable, AgentFailed, BudgetExceeded) as e:
        db.commit()
        return {"ok": False, "message": str(e)}


@router.get("/usage")
def usage(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    since = datetime.now(UTC) - timedelta(days=days)
    base = select(AIRun).where(AIRun.created_at >= since).subquery()
    totals = db.execute(select(func.count(), func.coalesce(func.sum(base.c.input_tokens), 0),
                               func.coalesce(func.sum(base.c.output_tokens), 0),
                               func.coalesce(func.sum(base.c.cached_tokens), 0),
                               func.coalesce(func.sum(base.c.cost_usd), 0),
                               func.coalesce(func.avg(base.c.latency_ms), 0))).one()
    by_agent = db.execute(select(base.c.agent, func.count(), func.sum(base.c.input_tokens), func.sum(base.c.output_tokens),
                                 func.sum(base.c.cost_usd), func.avg(base.c.latency_ms))
                          .group_by(base.c.agent).order_by(func.sum(base.c.cost_usd).desc())).all()
    by_model = db.execute(select(base.c.provider, base.c.model, func.count(), func.sum(base.c.cost_usd))
                          .group_by(base.c.provider, base.c.model)).all()
    by_status = db.execute(select(base.c.status, func.count()).group_by(base.c.status)).all()
    daily = db.execute(select(cast(base.c.created_at, Date), func.count(), func.sum(base.c.cost_usd))
                       .group_by(cast(base.c.created_at, Date)).order_by(cast(base.c.created_at, Date))).all()
    top_companies = db.execute(select(base.c.company_id, func.count(), func.sum(base.c.cost_usd))
                               .where(base.c.company_id.is_not(None)).group_by(base.c.company_id)
                               .order_by(func.sum(base.c.cost_usd).desc()).limit(10)).all()
    names = {c.id: c.name for c in db.scalars(select(Company).where(Company.id.in_([r[0] for r in top_companies]))).all()}
    return {
        "days": days,
        "totals": {"calls": totals[0], "input_tokens": int(totals[1]), "output_tokens": int(totals[2]),
                   "cached_tokens": int(totals[3]), "cost_usd": float(totals[4]), "avg_latency_ms": float(totals[5])},
        "by_agent": [{"agent": a, "calls": n, "input_tokens": int(i or 0), "output_tokens": int(o or 0),
                      "cost_usd": float(c or 0), "avg_latency_ms": float(lat or 0)} for a, n, i, o, c, lat in by_agent],
        "by_model": [{"provider": p, "model": m, "calls": n, "cost_usd": float(c or 0)} for p, m, n, c in by_model],
        "by_status": {s: n for s, n in by_status},
        "daily": [{"date": d.isoformat(), "calls": n, "cost_usd": float(c or 0)} for d, n, c in daily],
        "top_companies": [{"company_id": cid, "company_name": names.get(cid), "calls": n, "cost_usd": float(c or 0)}
                          for cid, n, c in top_companies],
        "status": ai_status(db),
    }


@router.get("/runs")
def runs(agent: str | None = None, status: str | None = None, pp: PageParams = Depends(),
         db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    stmt = select(AIRun).order_by(AIRun.created_at.desc())
    if agent:
        stmt = stmt.where(AIRun.agent == agent)
    if status:
        stmt = stmt.where(AIRun.status == status)
    return paginate(db, stmt, pp, lambda r: {
        "id": r.id, "agent": r.agent, "provider": r.provider, "model": r.model, "status": r.status,
        "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "cached_tokens": r.cached_tokens,
        "cost_usd": float(r.cost_usd or 0), "latency_ms": r.latency_ms, "attempts": r.attempts,
        "company_id": r.company_id, "job_id": r.job_id, "error": r.error, "created_at": r.created_at})
