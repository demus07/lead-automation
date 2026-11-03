from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api._common import PageParams, get_or_404, paginate
from app.core.db import get_db
from app.core.deps import require_operator, require_viewer
from app.discovery.engine import searches_today
from app.discovery.providers import WEB_SEARCH_KEYS, all_providers
from app.models import Campaign, SearchQuery, User
from app.schemas.common import ORM
from app.services import settings_service
from app.services.audit import audit
from app.services.csv_io import import_csv

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

MANUAL_CAMPAIGN = "Manual searches"


class SearchQueryOut(ORM):
    id: uuid.UUID
    campaign_id: uuid.UUID | None
    job_id: uuid.UUID | None
    provider: str
    query: str
    params: dict
    trigger: str
    status: str
    result_count: int
    new_companies: int
    error: str | None
    results: list
    created_at: datetime


@router.get("/providers")
def providers(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    cfg = settings_service.get_section(db, "discovery")
    active_web = cfg.get("web_search_provider", "none")
    out = []
    for p in all_providers():
        st = p.status(cfg).__dict__
        st["selected"] = p.key == active_web if p.key in WEB_SEARCH_KEYS else None
        out.append(st)
    web_ok = active_web != "none" and any(o["key"] == active_web and o["status"] in ("connected", "available")
                                          for o in out)
    return {
        "providers": out,
        "limited_mode": not web_ok,
        "limited_mode_reason": None if web_ok else
        "No web search provider configured: discovery uses public directories, hiring threads and RSS only.",
        "searches_today": searches_today(db, WEB_SEARCH_KEYS),
        "daily_search_quota": cfg.get("daily_search_quota"),
    }


@router.get("/history")
def history(campaign_id: uuid.UUID | None = None, provider: str | None = None, pp: PageParams = Depends(),
            db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    stmt = select(SearchQuery).order_by(SearchQuery.created_at.desc())
    if campaign_id:
        stmt = stmt.where(SearchQuery.campaign_id == campaign_id)
    if provider:
        stmt = stmt.where(SearchQuery.provider == provider)
    return paginate(db, stmt, pp, lambda r: SearchQueryOut.model_validate(r))


class ManualSearch(BaseModel):
    campaign_id: uuid.UUID | None = None
    query: str | None = Field(None, max_length=300)
    sources: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    company_sizes: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    limit: int = Field(10, ge=1, le=100)


def _manual_campaign(db: Session, user: User) -> Campaign:
    c = db.scalar(select(Campaign).where(Campaign.name == MANUAL_CAMPAIGN, Campaign.deleted_at.is_(None)))
    if not c:
        c = Campaign(name=MANUAL_CAMPAIGN, description="Ad-hoc searches run from the discovery page.",
                     auto_research=False, daily_company_limit=500, created_by_id=user.id)
        db.add(c)
        db.flush()
    return c


@router.post("/search")
def manual_search(body: ManualSearch, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    """Run a one-off search. Filters override the campaign's for this run only."""
    from app.workflows import load_workflows
    from app.workflows.engine import start_job

    load_workflows()
    if body.campaign_id:
        campaign = get_or_404(db, Campaign, body.campaign_id)
    else:
        campaign = _manual_campaign(db, user)
        # The manual campaign stores the latest ad-hoc filters (visible in history).
        campaign.industries = body.industries
        campaign.geographies = body.geographies
        campaign.company_sizes = body.company_sizes
        campaign.keywords = body.keywords
        db.flush()
    params = {"campaign_id": str(campaign.id), "limit": body.limit, "chain": bool(body.campaign_id)}
    if body.query:
        params["query"] = body.query
    if body.sources:
        params["sources"] = body.sources[:10]
    db.commit()
    job, _ = start_job(db, "discovery", params=params, user=user, campaign_id=campaign.id)
    db.refresh(job)
    return {"job_id": str(job.id), "status": job.status.value, "stats": job.stats, "errors": job.errors}


@router.post("/import")
async def import_companies_csv(
    file: UploadFile = File(...),
    campaign_id: uuid.UUID | None = Form(None),
    tags: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
):
    if file.content_type not in ("text/csv", "application/vnd.ms-excel", "application/octet-stream", "text/plain"):
        raise HTTPException(415, "Upload a .csv file")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "CSV larger than 10 MB")
    if campaign_id:
        get_or_404(db, Campaign, campaign_id)
    rep = import_csv(db, content, campaign_id=campaign_id, tags=[t.strip() for t in tags.split(",") if t.strip()])
    audit(db, "import.csv", actor=user, entity_type="campaign", entity_id=campaign_id,
          detail={k: v for k, v in rep.__dict__.items() if k != "company_ids"})
    db.commit()
    return rep.__dict__
