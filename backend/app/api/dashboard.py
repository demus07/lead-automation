from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.runtime import ai_status
from app.core.db import get_db
from app.core.deps import require_viewer
from app.discovery.providers import WEB_SEARCH_KEYS, get_provider
from app.models import (
    AutomationJob,
    BuyingSignal,
    Company,
    Contact,
    DraftStatus,
    EmailAccount,
    Interaction,
    JobStatus,
    LeadStatus,
    OutreachDraft,
    Task,
    User,
)
from app.services import settings_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def overview(db: Session = Depends(get_db), user: User = Depends(require_viewer)):
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    alive = Company.deleted_at.is_(None)
    count = lambda stmt: db.scalar(stmt) or 0  # noqa: E731
    by_status = {k.value: v for k, v in db.execute(select(Company.status, func.count()).where(alive)
                                                   .group_by(Company.status)).all()}
    pending = db.scalars(select(OutreachDraft).where(OutreachDraft.status == DraftStatus.PENDING_APPROVAL,
                                                     OutreachDraft.deleted_at.is_(None))
                         .order_by(OutreachDraft.quality_score.desc().nullslast()).limit(5)).all()
    top = db.scalars(select(Company).where(alive, Company.recommended_service.in_(["website", "company_brain"]))
                     .order_by(func.greatest(func.coalesce(Company.website_score, 0),
                                             func.coalesce(Company.brain_score, 0)).desc()).limit(6)).all()
    recent_signals = db.scalars(select(BuyingSignal).where(BuyingSignal.confidence >= 0.5)
                                .order_by(BuyingSignal.discovered_at.desc()).limit(6)).all()
    jobs = db.scalars(select(AutomationJob).order_by(AutomationJob.created_at.desc()).limit(8)).all()
    replies = db.scalars(select(Interaction).where(Interaction.direction == "inbound", Interaction.handled.is_(False))
                         .order_by(Interaction.occurred_at.desc()).limit(5)).all()
    dcfg = settings_service.get_section(db, "discovery")
    web = dcfg.get("web_search_provider", "none")
    profile = settings_service.get_section(db, "agency_profile")
    names = {c.id: c.name for c in db.scalars(select(Company).where(Company.id.in_(
        [d.company_id for d in pending] + [s.company_id for s in recent_signals] +
        [r.company_id for r in replies if r.company_id]))).all()}
    return {
        "onboarding_completed": bool(profile.get("onboarding_completed")),
        "kpis": {
            "companies": count(select(func.count()).select_from(Company).where(alive)),
            "discovered_today": count(select(func.count()).select_from(Company).where(alive, Company.created_at >= today)),
            "discovered_week": count(select(func.count()).select_from(Company).where(alive, Company.created_at >= week)),
            "qualified": by_status.get("QUALIFIED", 0),
            "pending_approval": count(select(func.count()).select_from(OutreachDraft).where(
                OutreachDraft.status == DraftStatus.PENDING_APPROVAL, OutreachDraft.deleted_at.is_(None))),
            "needs_review": count(select(func.count()).select_from(OutreachDraft).where(
                OutreachDraft.status == DraftStatus.NEEDS_REVIEW, OutreachDraft.deleted_at.is_(None))),
            "contacts_with_email": count(select(func.count()).select_from(Contact).where(
                Contact.deleted_at.is_(None), Contact.email_normalized.is_not(None))),
            "unhandled_replies": count(select(func.count()).select_from(Interaction).where(
                Interaction.direction == "inbound", Interaction.handled.is_(False))),
            "open_tasks": count(select(func.count()).select_from(Task).where(Task.status == "open",
                                                                            Task.deleted_at.is_(None))),
            "failed_jobs_week": count(select(func.count()).select_from(AutomationJob).where(
                AutomationJob.status == JobStatus.FAILED, AutomationJob.created_at >= week)),
        },
        "by_status": by_status,
        "pending_drafts": [{"id": d.id, "company_id": d.company_id, "company_name": names.get(d.company_id),
                            "subject": d.subject, "service": d.service, "quality_score": d.quality_score}
                           for d in pending],
        "top_opportunities": [{"id": c.id, "name": c.name, "domain": c.domain_normalized, "status": c.status.value,
                               "website_score": c.website_score, "brain_score": c.brain_score,
                               "recommended_service": c.recommended_service} for c in top],
        "recent_signals": [{"id": s.id, "company_id": s.company_id, "company_name": names.get(s.company_id),
                            "signal_type": s.signal_type, "description": s.description, "freshness": s.freshness,
                            "source_url": s.source_url, "published_at": s.published_at} for s in recent_signals],
        "recent_jobs": [{"id": j.id, "workflow": j.workflow, "status": j.status.value, "trigger": j.trigger,
                         "created_at": j.created_at, "stats": j.stats} for j in jobs],
        "recent_replies": [{"id": r.id, "company_name": names.get(r.company_id), "subject": r.subject,
                            "classification": r.classification, "occurred_at": r.occurred_at} for r in replies],
        "system": {
            "ai": ai_status(db),
            "web_search": {"provider": web, "configured": web != "none" and get_provider(web).is_configured(dcfg)
                           if web in WEB_SEARCH_KEYS else False},
            "email_accounts": count(select(func.count()).select_from(EmailAccount).where(
                EmailAccount.deleted_at.is_(None), EmailAccount.status == "connected")),
        },
    }
