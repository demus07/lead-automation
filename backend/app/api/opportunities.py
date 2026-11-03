from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api._common import PageParams, get_or_404, paginate
from app.core.db import get_db
from app.core.deps import require_operator, require_viewer
from app.models import Company, LeadScore, LeadStatus, Opportunity, User

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

PIPELINE_COLUMNS = [
    ("Researched", [LeadStatus.RESEARCHED]),
    ("Qualified", [LeadStatus.QUALIFIED]),
    ("Drafting", [LeadStatus.DRAFT_GENERATED]),
    ("Awaiting approval", [LeadStatus.PENDING_APPROVAL]),
    ("Approved / draft in mailbox", [LeadStatus.APPROVED, LeadStatus.EMAIL_DRAFT_CREATED]),
    ("Contacted", [LeadStatus.CONTACTED]),
    ("Replied", [LeadStatus.REPLIED, LeadStatus.INTERESTED, LeadStatus.MEETING_REQUESTED]),
]


def opp_out(o: Opportunity) -> dict:
    return {"id": o.id, "company_id": o.company_id, "website_score": o.website_score,
            "website_confidence": o.website_confidence, "website_explanation": o.website_explanation,
            "brain_score": o.brain_score, "brain_confidence": o.brain_confidence,
            "brain_explanation": o.brain_explanation, "recommended_service": o.recommended_service,
            "recommendation_reason": o.recommendation_reason, "sales_angle": o.sales_angle, "evidence": o.evidence,
            "method": o.method, "stage": o.stage, "updated_at": o.updated_at}


@router.get("")
def list_opportunities(service: str | None = None, min_score: int | None = Query(None, ge=0, le=100),
                       sort: str = "best", pp: PageParams = Depends(), db: Session = Depends(get_db),
                       _: User = Depends(require_viewer)):
    stmt = select(Opportunity).join(Company, Company.id == Opportunity.company_id).where(Company.deleted_at.is_(None))
    if service:
        stmt = stmt.where(Opportunity.recommended_service == service)
    if min_score is not None:
        stmt = stmt.where((Opportunity.website_score >= min_score) | (Opportunity.brain_score >= min_score))
    from sqlalchemy import func

    best = func.greatest(func.coalesce(Opportunity.website_score, 0), func.coalesce(Opportunity.brain_score, 0))
    stmt = stmt.order_by(best.desc() if sort == "best" else Opportunity.updated_at.desc())

    def ser(o: Opportunity) -> dict:
        c = db.get(Company, o.company_id)
        return {**opp_out(o), "company": {"id": c.id, "name": c.name, "domain": c.domain_normalized,
                                          "industry": c.industry, "status": c.status.value}}

    return paginate(db, stmt, pp, ser)


@router.get("/pipeline")
def pipeline(campaign_id: uuid.UUID | None = None, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    cols = []
    for label, statuses in PIPELINE_COLUMNS:
        stmt = select(Company).where(Company.deleted_at.is_(None), Company.status.in_(statuses))
        if campaign_id:
            stmt = stmt.where(Company.campaign_id == campaign_id)
        rows = db.scalars(stmt.order_by(Company.updated_at.desc()).limit(50)).all()
        cols.append({"label": label, "statuses": [s.value for s in statuses], "items": [
            {"id": c.id, "name": c.name, "domain": c.domain_normalized, "status": c.status.value,
             "website_score": c.website_score, "brain_score": c.brain_score,
             "recommended_service": c.recommended_service, "updated_at": c.updated_at} for c in rows]})
    return {"columns": cols}


@router.get("/company/{company_id}")
def company_opportunity(company_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    get_or_404(db, Company, company_id)
    o = db.scalar(select(Opportunity).where(Opportunity.company_id == company_id))
    history = db.scalars(select(LeadScore).where(LeadScore.company_id == company_id)
                         .order_by(LeadScore.created_at.desc()).limit(20)).all()
    return {"opportunity": opp_out(o) if o else None,
            "scores": [{"id": s.id, "service": s.service, "score": s.score, "confidence": s.confidence,
                        "factors": s.factors, "explanation": s.explanation, "evidence": s.evidence,
                        "sales_angle": s.sales_angle, "method": s.method, "created_at": s.created_at}
                       for s in history]}


@router.post("/company/{company_id}/score")
def rescore(company_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    from app.workflows import load_workflows
    from app.workflows.engine import start_job

    load_workflows()
    c = get_or_404(db, Company, company_id)
    job, _ = start_job(db, "qualification", params={"company_ids": [str(c.id)]}, user=user, company_id=c.id)
    db.refresh(job)
    return {"job_id": str(job.id), "status": job.status.value}
