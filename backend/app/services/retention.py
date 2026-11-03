"""Data retention. Suppression records and audit logs within their window are never deleted."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import AIRun, AuditLog, Company, Contact, DraftStatus, Interaction, LeadStatus, OutreachDraft, PageCache
from app.models.base import utcnow
from app.services import settings_service
from app.services.audit import audit


def run_retention(db: Session) -> dict[str, Any]:
    r = settings_service.get_section(db, "retention")
    now = utcnow()
    out: dict[str, Any] = {}
    out["page_cache"] = db.execute(delete(PageCache).where(
        PageCache.fetched_at < now - timedelta(days=int(r["page_cache_days"])))).rowcount
    out["ai_runs"] = db.execute(update(AIRun).where(
        AIRun.created_at < now - timedelta(days=int(r["ai_runs_days"]))).values(output={}, request_summary={})).rowcount
    out["audit_logs"] = db.execute(delete(AuditLog).where(
        AuditLog.created_at < now - timedelta(days=int(r["audit_log_days"])))).rowcount
    out["rejected_drafts"] = db.execute(update(OutreachDraft).where(
        OutreachDraft.status.in_([DraftStatus.REJECTED, DraftStatus.SUPERSEDED]), OutreachDraft.deleted_at.is_(None),
        OutreachDraft.updated_at < now - timedelta(days=int(r["rejected_drafts_days"]))).values(deleted_at=now)).rowcount
    old = db.scalars(select(Company).where(
        Company.status == LeadStatus.DISQUALIFIED, Company.deleted_at.is_(None),
        Company.updated_at < now - timedelta(days=int(r["disqualified_companies_days"])))).all()
    for c in old:
        c.deleted_at = now
        db.execute(update(Contact).where(Contact.company_id == c.id).values(deleted_at=now))
    out["disqualified_companies"] = len(old)
    out["interactions"] = db.execute(update(Interaction).where(
        Interaction.occurred_at < now - timedelta(days=int(r["interactions_days"]))).values(snippet=None)).rowcount
    audit(db, "retention.run", actor_type="system", detail=out)
    db.flush()
    return out
