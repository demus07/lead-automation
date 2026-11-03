from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_viewer
from app.models import (
    AIRun,
    Approval,
    BuyingSignal,
    Campaign,
    Company,
    Contact,
    DraftStatus,
    EmailDraft,
    Interaction,
    LeadSource,
    LeadStatus,
    OutreachDraft,
    User,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

FUNNEL = [
    ("Discovered", None),
    ("Researched", [LeadStatus.RESEARCHED, LeadStatus.QUALIFIED, LeadStatus.DRAFT_GENERATED, LeadStatus.PENDING_APPROVAL,
                    LeadStatus.APPROVED, LeadStatus.EMAIL_DRAFT_CREATED, LeadStatus.CONTACTED, LeadStatus.REPLIED,
                    LeadStatus.INTERESTED, LeadStatus.MEETING_REQUESTED, LeadStatus.NOT_INTERESTED]),
    ("Qualified", [LeadStatus.QUALIFIED, LeadStatus.DRAFT_GENERATED, LeadStatus.PENDING_APPROVAL, LeadStatus.APPROVED,
                   LeadStatus.EMAIL_DRAFT_CREATED, LeadStatus.CONTACTED, LeadStatus.REPLIED, LeadStatus.INTERESTED,
                   LeadStatus.MEETING_REQUESTED, LeadStatus.NOT_INTERESTED]),
    ("Approved", [LeadStatus.APPROVED, LeadStatus.EMAIL_DRAFT_CREATED, LeadStatus.CONTACTED, LeadStatus.REPLIED,
                  LeadStatus.INTERESTED, LeadStatus.MEETING_REQUESTED, LeadStatus.NOT_INTERESTED]),
    ("Contacted", [LeadStatus.CONTACTED, LeadStatus.REPLIED, LeadStatus.INTERESTED, LeadStatus.MEETING_REQUESTED,
                   LeadStatus.NOT_INTERESTED]),
    ("Replied", [LeadStatus.REPLIED, LeadStatus.INTERESTED, LeadStatus.MEETING_REQUESTED, LeadStatus.NOT_INTERESTED]),
    ("Interested / meeting", [LeadStatus.INTERESTED, LeadStatus.MEETING_REQUESTED]),
]


def _since(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


@router.get("")
def analytics(days: int = Query(30, ge=1, le=730), campaign_id: str | None = None, db: Session = Depends(get_db),
              _: User = Depends(require_viewer)):
    since = _since(days)
    cq = select(Company).where(Company.deleted_at.is_(None), Company.created_at >= since)
    if campaign_id:
        cq = cq.where(Company.campaign_id == campaign_id)
    sub = cq.subquery()
    funnel = []
    for label, statuses in FUNNEL:
        q = select(func.count()).select_from(sub)
        if statuses:
            q = q.where(sub.c.status.in_([s.value for s in statuses]))
        funnel.append({"stage": label, "count": db.scalar(q) or 0})

    by_service = dict(db.execute(select(sub.c.recommended_service, func.count()).group_by(sub.c.recommended_service)).all())
    by_source = db.execute(select(LeadSource.provider, func.count(func.distinct(LeadSource.company_id)))
                           .where(LeadSource.created_at >= since).group_by(LeadSource.provider)).all()
    discovered_daily = db.execute(select(cast(sub.c.created_at, Date), func.count()).group_by(cast(sub.c.created_at, Date))
                                  .order_by(cast(sub.c.created_at, Date))).all()
    approvals = dict(db.execute(select(Approval.action, func.count()).where(Approval.created_at >= since)
                                .group_by(Approval.action)).all())
    drafts = dict(db.execute(select(OutreachDraft.status, func.count()).where(OutreachDraft.created_at >= since)
                             .group_by(OutreachDraft.status)).all())
    avg_quality = db.scalar(select(func.avg(OutreachDraft.quality_score)).where(OutreachDraft.created_at >= since))
    edited = db.scalar(select(func.count()).select_from(OutreachDraft).where(
        OutreachDraft.created_at >= since, OutreachDraft.edited_by_user.is_(True))) or 0
    replies = dict(db.execute(select(Interaction.classification, func.count()).where(
        Interaction.direction == "inbound", Interaction.occurred_at >= since).group_by(Interaction.classification)).all())
    sent = db.scalar(select(func.count()).select_from(EmailDraft).where(
        EmailDraft.sent_detected_at.is_not(None), EmailDraft.sent_detected_at >= since)) or 0
    inbound = sum(replies.values())
    camp_rows = []
    for c in db.scalars(select(Campaign).where(Campaign.deleted_at.is_(None))).all():
        st = dict(db.execute(select(Company.status, func.count()).where(Company.campaign_id == c.id,
                                                                        Company.deleted_at.is_(None))
                             .group_by(Company.status)).all())
        total = sum(st.values())
        contacted = sum(v for k, v in st.items() if k in FUNNEL[4][1])
        replied = sum(v for k, v in st.items() if k in FUNNEL[5][1])
        positive = sum(v for k, v in st.items() if k in FUNNEL[6][1])
        camp_rows.append({"id": c.id, "name": c.name, "companies": total,
                          "qualified": sum(v for k, v in st.items() if k in FUNNEL[2][1]), "contacted": contacted,
                          "replied": replied, "positive": positive,
                          "reply_rate": round(replied / contacted, 3) if contacted else None})
    signals = dict(db.execute(select(BuyingSignal.signal_type, func.count()).where(BuyingSignal.discovered_at >= since)
                              .group_by(BuyingSignal.signal_type)).all())
    ai_cost = float(db.scalar(select(func.coalesce(func.sum(AIRun.cost_usd), 0)).where(AIRun.created_at >= since)) or 0)
    approved_n = approvals.get("approve", 0)
    return {
        "days": days,
        "funnel": funnel,
        "by_service": {(k or "unscored"): v for k, v in by_service.items()},
        "by_source": [{"provider": p, "companies": n} for p, n in by_source],
        "discovered_daily": [{"date": d.isoformat(), "count": n} for d, n in discovered_daily],
        "approvals": approvals,
        "drafts": {k.value: v for k, v in drafts.items()},
        "avg_quality": round(float(avg_quality), 1) if avg_quality is not None else None,
        "edit_rate": round(edited / max(1, sum(drafts.values())), 3),
        "approval_rate": round(approved_n / max(1, approved_n + approvals.get("reject", 0)), 3) if approvals else None,
        "emails_sent_by_user": sent,
        "replies": replies,
        "reply_rate": round(inbound / sent, 3) if sent else None,
        "campaigns": camp_rows,
        "signals": signals,
        "ai_cost_usd": round(ai_cost, 4),
        "cost_per_approved_draft": round(ai_cost / approved_n, 4) if approved_n else None,
    }
