from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api._common import get_or_404
from app.core.db import get_db
from app.core.deps import require_operator, require_viewer
from app.discovery.engine import DEFAULT_TEMPLATES, build_queries
from app.discovery.normalize import normalize_url
from app.discovery.providers import get_provider
from app.models import Campaign, Company, LeadStatus, OutreachDraft, DraftStatus, User
from app.models.base import utcnow
from app.schemas.common import ORM, Msg
from app.services.audit import audit

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

_SIZES = {"1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001+"}


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=4000)
    is_active: bool = True
    target_service: str = Field("any", pattern="^(any|website|company_brain)$")
    industries: list[str] = Field(default_factory=list, max_length=50)
    geographies: list[str] = Field(default_factory=list, max_length=50)
    company_sizes: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list, max_length=50)
    keywords: list[str] = Field(default_factory=list, max_length=50)
    query_templates: list[str] = Field(default_factory=list, max_length=50)
    signal_focus: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    rss_feeds: list[str] = Field(default_factory=list, max_length=50)
    daily_company_limit: int = Field(25, ge=1, le=1000)
    daily_query_limit: int = Field(20, ge=1, le=500)
    auto_research: bool = True

    @field_validator("industries", "geographies", "target_roles", "keywords", "query_templates", "signal_focus")
    @classmethod
    def _clean_list(cls, v: list[str]) -> list[str]:
        return [x.strip()[:300] for x in v if x and x.strip()]

    @field_validator("company_sizes")
    @classmethod
    def _sizes(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if s not in _SIZES]
        if bad:
            raise ValueError(f"Unknown size ranges {bad}; use {sorted(_SIZES)}")
        return v

    @field_validator("sources")
    @classmethod
    def _sources(cls, v: list[str]) -> list[str]:
        for s in v:
            try:
                get_provider(s)
            except KeyError:
                raise ValueError(f"Unknown discovery source '{s}'") from None
        return v

    @field_validator("rss_feeds")
    @classmethod
    def _feeds(cls, v: list[str]) -> list[str]:
        out = []
        for f in v:
            u = normalize_url(f)
            if not u:
                raise ValueError(f"Invalid feed URL '{f}'")
            out.append(u)
        return out


class CampaignPatch(CampaignIn):
    name: str | None = Field(None, min_length=1, max_length=200)  # type: ignore[assignment]


class CampaignOut(ORM):
    id: uuid.UUID
    name: str
    description: str
    is_active: bool
    target_service: str
    industries: list[str]
    geographies: list[str]
    company_sizes: list[str]
    target_roles: list[str]
    keywords: list[str]
    query_templates: list[str]
    signal_focus: list[str]
    sources: list[str]
    rss_feeds: list[str]
    daily_company_limit: int
    daily_query_limit: int
    auto_research: bool
    created_at: datetime
    updated_at: datetime
    stats: dict = Field(default_factory=dict)


def _stats(db: Session, c: Campaign) -> dict:
    by_status = dict(db.execute(select(Company.status, func.count()).where(
        Company.campaign_id == c.id, Company.deleted_at.is_(None)).group_by(Company.status)).all())
    drafts = db.scalar(select(func.count()).select_from(OutreachDraft).where(
        OutreachDraft.campaign_id == c.id, OutreachDraft.status == DraftStatus.EMAIL_DRAFT_CREATED)) or 0
    total = sum(by_status.values())
    replied = sum(v for k, v in by_status.items() if k in (LeadStatus.REPLIED, LeadStatus.INTERESTED,
                                                           LeadStatus.MEETING_REQUESTED, LeadStatus.NOT_INTERESTED))
    return {"companies": total, "by_status": {k.value: v for k, v in by_status.items()},
            "qualified": sum(v for k, v in by_status.items() if k not in (LeadStatus.NEW, LeadStatus.RESEARCHING,
                                                                           LeadStatus.RESEARCHED, LeadStatus.DISQUALIFIED)),
            "email_drafts": drafts, "replied": replied}


def _out(db: Session, c: Campaign) -> CampaignOut:
    o = CampaignOut.model_validate(c)
    o.stats = _stats(db, c)
    return o


@router.get("", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    rows = db.scalars(select(Campaign).where(Campaign.deleted_at.is_(None)).order_by(Campaign.created_at.desc())).all()
    return [_out(db, c) for c in rows]


@router.get("/templates")
def default_templates(_: User = Depends(require_viewer)):
    return {"signal_templates": DEFAULT_TEMPLATES,
            "sizes": sorted(_SIZES, key=lambda s: int(s.split("-")[0].rstrip("+")))}


@router.post("", response_model=CampaignOut, status_code=201)
def create_campaign(body: CampaignIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    c = Campaign(**body.model_dump(), created_by_id=user.id)
    db.add(c)
    db.flush()
    audit(db, "campaign.created", actor=user, entity_type="campaign", entity_id=c.id, detail={"name": c.name})
    db.commit()
    return _out(db, c)


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return _out(db, get_or_404(db, Campaign, campaign_id))


@router.get("/{campaign_id}/preview-queries")
def preview_queries(campaign_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    c = get_or_404(db, Campaign, campaign_id)
    return {"queries": build_queries(c, c.daily_query_limit)}


@router.patch("/{campaign_id}", response_model=CampaignOut)
def update_campaign(campaign_id: uuid.UUID, body: CampaignPatch, db: Session = Depends(get_db),
                    user: User = Depends(require_operator)):
    c = get_or_404(db, Campaign, campaign_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name") is None:
        changes.pop("name", None)
    for k, v in changes.items():
        setattr(c, k, v)
    audit(db, "campaign.updated", actor=user, entity_type="campaign", entity_id=c.id, detail={"fields": list(changes)})
    db.commit()
    return _out(db, c)


@router.delete("/{campaign_id}", response_model=Msg)
def delete_campaign(campaign_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    c = get_or_404(db, Campaign, campaign_id)
    c.deleted_at = utcnow()
    c.is_active = False
    audit(db, "campaign.deleted", actor=user, entity_type="campaign", entity_id=c.id)
    db.commit()
    return Msg(message="Campaign archived")


@router.post("/{campaign_id}/run", response_model=dict)
def run_campaign(campaign_id: uuid.UUID, body: dict | None = None, db: Session = Depends(get_db),
                 user: User = Depends(require_operator)):
    from app.workflows import load_workflows
    from app.workflows.engine import start_job

    load_workflows()
    c = get_or_404(db, Campaign, campaign_id)
    if not c.is_active:
        raise HTTPException(400, "Campaign is paused")
    body = body or {}
    params = {"campaign_id": str(c.id)}
    if body.get("sources"):
        params["sources"] = [s for s in body["sources"] if isinstance(s, str)][:10]
    if body.get("query"):
        params["query"] = str(body["query"])[:300]
    job, _ = start_job(db, "discovery", params=params, user=user, campaign_id=c.id)
    return {"job_id": str(job.id), "status": job.status.value}
