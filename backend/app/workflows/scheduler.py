"""DB-driven scheduler. Celery beat calls ``tick()`` every minute; schedules are editable in the UI."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WorkflowSchedule
from app.models.base import utcnow
from app.workflows.engine import REGISTRY, start_job

log = logging.getLogger(__name__)

DEFAULT_SCHEDULES = {
    "discovery": ("0 6 * * *", 25),  # daily 06:00 UTC
    "research": ("*/30 * * * *", 10),
    "contacts": ("15,45 * * * *", 10),
    "qualification": ("*/30 * * * *", 10),
    "drafting": ("0 * * * *", 10),
    "approval": ("*/5 * * * *", 20),  # retries pending mailbox-draft creation for approved drafts only
    "replies": ("*/15 * * * *", 50),
    "maintenance": ("30 3 * * *", 0),
}


def next_run(cron: str, after: datetime | None = None) -> datetime:
    base = after or datetime.now(UTC)
    return croniter(cron, base).get_next(datetime)


def ensure_default_schedules(db: Session) -> None:
    from app.workflows import load_workflows

    load_workflows()
    for wf, (cron, batch) in DEFAULT_SCHEDULES.items():
        if not db.scalar(select(WorkflowSchedule).where(WorkflowSchedule.workflow == wf)):
            # Scheduled automation starts paused-off (enabled) except discovery which needs a campaign anyway.
            db.add(WorkflowSchedule(workflow=wf, cron=cron, batch_size=batch, enabled=True, paused=False,
                                    next_run_at=next_run(cron)))
    db.flush()


def tick(db: Session) -> list[str]:
    """Start due scheduled workflows. Idempotent per scheduled slot."""
    from app.workflows import load_workflows

    load_workflows()
    db.expire_all()  # always read current pause/schedule state
    now = utcnow()
    started: list[str] = []
    global_pause = db.scalar(select(WorkflowSchedule).where(WorkflowSchedule.workflow == "__global__",
                                                            WorkflowSchedule.paused.is_(True)))
    schedules = db.scalars(select(WorkflowSchedule).where(WorkflowSchedule.enabled.is_(True),
                                                          WorkflowSchedule.workflow != "__global__")).all()
    for s in schedules:
        if s.workflow not in REGISTRY:
            continue
        if s.next_run_at is None:
            s.next_run_at = next_run(s.cron, now)
            continue
        if s.next_run_at > now:
            continue
        slot = s.next_run_at
        s.last_run_at = now
        s.next_run_at = next_run(s.cron, now)
        db.commit()
        if s.paused or global_pause:
            continue
        key = f"sched:{s.workflow}:{slot.strftime('%Y%m%dT%H%M')}"
        try:
            start_job(db, s.workflow, params={**(s.params or {}), "batch_size": s.batch_size}, trigger="scheduled",
                      idempotency_key=key)
            started.append(s.workflow)
        except Exception:  # noqa: BLE001
            log.exception("failed to start scheduled %s", s.workflow)
            db.rollback()
    return started
