from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import AutomationJob, JobStatus
from app.models.base import utcnow
from app.workflows.engine import dispatch_job

STALE_RUNNING = timedelta(minutes=70)  # > task_time_limit
STALE_QUEUED = timedelta(minutes=10)


def recover(db: Session) -> int:
    now = utcnow()
    n = 0
    stuck = db.scalars(select(AutomationJob).where(
        AutomationJob.status == JobStatus.RUNNING, AutomationJob.started_at < now - STALE_RUNNING)).all()
    requeue = []
    for job in stuck:
        job.errors = [*(job.errors or []), {"at": now.isoformat(), "error": "Worker lost; job recovered"}]
        if job.attempts < job.max_attempts:
            job.status = JobStatus.QUEUED
            requeue.append(job.id)
            n += 1
        else:
            job.status = JobStatus.FAILED
            job.finished_at = now
    db.commit()
    for jid in requeue:
        dispatch_job(jid)
    queued = db.scalars(select(AutomationJob).where(
        AutomationJob.status == JobStatus.QUEUED,
        or_(AutomationJob.next_retry_at.is_(None), AutomationJob.next_retry_at < now - STALE_QUEUED),
        AutomationJob.updated_at < now - STALE_QUEUED)).all()
    for job in queued:
        dispatch_job(job.id)
        n += 1
    return n
