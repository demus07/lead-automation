from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api._common import PageParams, get_or_404, paginate
from app.core.db import get_db
from app.core.deps import require_operator, require_viewer
from app.models import BuyingSignal, Company, ResearchReport, User
from app.schemas.crm import SignalOut

router = APIRouter(prefix="/api/research", tags=["research"])


def report_summary(r: ResearchReport, full: bool = False) -> dict:
    d = {
        "id": r.id, "company_id": r.company_id, "version": r.version, "status": r.status, "summary": r.summary,
        "researched_at": r.researched_at, "created_at": r.created_at,
        "pages": [{k: p.get(k) for k in ("id", "kind", "final_url", "title", "meta_description", "word_count",
                                          "headings", "nav_items", "ctas", "tools_mentioned", "tech", "rendered")}
                  for p in r.pages],
        "audit": r.audit, "analysis": {k: v for k, v in (r.analysis or {}).items() if k != "rejected_observations"},
        "observations": r.observations, "evidence": r.evidence, "business_info": r.business_info,
        "robots": r.robots, "injection_flags": r.injection_flags, "errors": r.errors,
    }
    if full:
        d["rejected_observations"] = (r.analysis or {}).get("rejected_observations", [])
    return d


@router.get("")
def list_reports(q: str | None = Query(None, max_length=200), status: str | None = None, pp: PageParams = Depends(),
                 db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    stmt = select(ResearchReport).join(Company, Company.id == ResearchReport.company_id).where(Company.deleted_at.is_(None))
    if q:
        stmt = stmt.where(Company.name.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(ResearchReport.status == status)
    stmt = stmt.order_by(ResearchReport.created_at.desc())

    def ser(r: ResearchReport) -> dict:
        c = db.get(Company, r.company_id)
        checks = (r.audit or {}).get("summary", {})
        return {"id": r.id, "company_id": r.company_id, "company_name": c.name if c else None,
                "domain": c.domain_normalized if c else None, "version": r.version, "status": r.status,
                "summary": r.summary, "pages": len(r.pages), "audit_score": checks.get("score"),
                "observations": len(r.observations), "method": (r.analysis or {}).get("method"),
                "injection_flags": len(r.injection_flags or []), "created_at": r.created_at}

    return paginate(db, stmt, pp, ser)


@router.get("/signals")
def list_signals(signal_type: str | None = None, freshness: str | None = None, min_confidence: float = 0.0,
                 pp: PageParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    stmt = select(BuyingSignal).where(BuyingSignal.confidence >= min_confidence)
    if signal_type:
        stmt = stmt.where(BuyingSignal.signal_type == signal_type)
    if freshness:
        stmt = stmt.where(BuyingSignal.freshness == freshness)
    stmt = stmt.order_by(BuyingSignal.published_at.desc().nullslast(), BuyingSignal.discovered_at.desc())

    def ser(s: BuyingSignal) -> dict:
        c = db.get(Company, s.company_id)
        return {**SignalOut.model_validate(s).model_dump(), "company_name": c.name if c else None}

    return paginate(db, stmt, pp, ser)


@router.get("/{report_id}")
def get_report(report_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    r = get_or_404(db, ResearchReport, report_id)
    c = db.get(Company, r.company_id)
    return {**report_summary(r, full=True), "company": {"id": c.id, "name": c.name, "domain": c.domain_normalized,
                                                         "website": c.website, "status": c.status.value}}


@router.post("/company/{company_id}/run")
def run_research(company_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    from app.workflows import load_workflows
    from app.workflows.engine import start_job

    load_workflows()
    c = get_or_404(db, Company, company_id)
    job, _ = start_job(db, "research", params={"company_ids": [str(c.id)], "force": True}, user=user, company_id=c.id)
    db.refresh(job)
    return {"job_id": str(job.id), "status": job.status.value}
