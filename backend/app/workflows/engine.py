"""Internal workflow engine.

* Every run is an ``automation_jobs`` row (execution history, params, stats, errors, log).
* Idempotency: a job may carry an ``idempotency_key``; starting a job with a key that already has a
  queued/running/succeeded job returns the existing job instead of starting a duplicate.
* Retries: transient failures are retried with exponential backoff up to ``max_attempts``.
* Pause/resume: per-workflow ``workflow_schedules.paused`` and a global pause flag. Paused workflows
  don't start scheduled runs; running jobs stop between items (``JobContext.check``).
* Manual and scheduled triggers share the same code path.
"""
from __future__ import annotations

import logging
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.http import TransientHTTPError
from app.models import AutomationJob, JobStatus, User, WorkflowSchedule
from app.models.base import utcnow
from app.services.audit import audit

log = logging.getLogger(__name__)

WorkflowFn = Callable[["JobContext"], dict[str, Any]]
REGISTRY: dict[str, WorkflowFn] = {}
DESCRIPTIONS: dict[str, str] = {}


def workflow(name: str, description: str = ""):
    def deco(fn: WorkflowFn) -> WorkflowFn:
        REGISTRY[name] = fn
        DESCRIPTIONS[name] = description
        return fn

    return deco


class JobCancelled(Exception):
    pass


class RetryableError(Exception):
    """Raise from a workflow to request a retry with backoff."""


@dataclass
class JobContext:
    db: Session
    job: AutomationJob

    @property
    def params(self) -> dict[str, Any]:
        return self.job.params or {}

    def log(self, message: str, **data: Any) -> None:
        entry = {"at": utcnow().isoformat(), "msg": message[:500], **({"data": data} if data else {})}
        self.job.log = [*(self.job.log or [])[-199:], entry]
        log.info("[job %s %s] %s", self.job.workflow, self.job.id, message)

    def error(self, message: str, **data: Any) -> None:
        self.job.errors = [*(self.job.errors or [])[-99:], {"at": utcnow().isoformat(), "error": message[:1000], **data}]

    def check(self) -> None:
        """Call between items: commits progress and stops if cancelled or paused."""
        self.db.commit()
        self.db.refresh(self.job, attribute_names=["status"])
        if self.job.status == JobStatus.CANCELLED:
            raise JobCancelled()
        if is_paused(self.db, self.job.workflow) and self.job.trigger == "scheduled":
            raise JobCancelled("paused")


def is_paused(db: Session, workflow_name: str) -> bool:
    from app.services import settings_service  # noqa: F401  (kept for future global flags)

    sched = db.scalar(select(WorkflowSchedule).where(WorkflowSchedule.workflow.in_([workflow_name, "__global__"])
                                                     , WorkflowSchedule.paused.is_(True)))
    return sched is not None


def start_job(
    db: Session,
    workflow_name: str,
    *,
    params: dict[str, Any] | None = None,
    trigger: str = "manual",
    idempotency_key: str | None = None,
    user: User | None = None,
    company_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
    max_attempts: int = 3,
    dispatch: bool = True,
) -> tuple[AutomationJob, bool]:
    """Create and dispatch a job. Returns (job, created)."""
    if workflow_name not in REGISTRY:
        raise KeyError(f"Unknown workflow {workflow_name}")
    if idempotency_key:
        existing = db.scalar(select(AutomationJob).where(AutomationJob.idempotency_key == idempotency_key))
        if existing:
            if existing.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                existing.idempotency_key = f"{idempotency_key}#superseded:{existing.id}"
                db.flush()
            else:
                return existing, False
    job = AutomationJob(
        workflow=workflow_name, trigger=trigger, params=params or {}, idempotency_key=idempotency_key,
        status=JobStatus.QUEUED, created_by_id=user.id if user else None, company_id=company_id,
        campaign_id=campaign_id, parent_id=parent_id, max_attempts=max_attempts,
    )
    db.add(job)
    try:
        db.flush()
    except IntegrityError:  # concurrent duplicate start
        db.rollback()
        existing = db.scalar(select(AutomationJob).where(AutomationJob.idempotency_key == idempotency_key))
        return existing, False
    audit(db, "workflow.started", actor=user, actor_type=None if user else "system", entity_type="automation_job",
          entity_id=job.id, detail={"workflow": workflow_name, "trigger": trigger})
    db.commit()
    if dispatch:
        dispatch_job(job.id)
    return job, True


def dispatch_job(job_id: uuid.UUID, countdown: int = 0) -> None:
    from app.core.config import get_settings

    if get_settings().celery_eager:
        execute_job(job_id)
        return
    from app.worker import run_job_task

    queue = "default"
    task_id = str(uuid.uuid4())
    # Record the task id BEFORE publishing so the worker never races with this write.
    with SessionLocal() as db:
        job = db.get(AutomationJob, job_id)
        if job:
            if job.workflow in ("research", "contacts"):
                queue = "research"
            elif job.workflow in ("qualification", "drafting"):
                queue = "ai"
            elif job.workflow in ("approval", "replies"):
                queue = "email"
            job.celery_task_id = task_id
            db.commit()
    run_job_task.apply_async(args=[str(job_id)], countdown=countdown, queue=queue, task_id=task_id)


def execute_job(job_id: uuid.UUID | str) -> JobStatus | None:
    """Run a job to completion in the current process. Safe to call more than once (no-op if done)."""
    job_id = uuid.UUID(str(job_id))
    db = SessionLocal()
    try:
        # Blocking row lock: a duplicate delivery waits, then sees the job is no longer QUEUED and exits.
        job = db.scalar(select(AutomationJob).where(AutomationJob.id == job_id).with_for_update())
        if job is None:
            return None
        if job.status not in (JobStatus.QUEUED,):
            return job.status
        if job.trigger == "scheduled" and is_paused(db, job.workflow):
            job.status = JobStatus.SKIPPED
            job.finished_at = utcnow()
            job.log = [*(job.log or []), {"at": utcnow().isoformat(), "msg": "Skipped: workflow paused"}]
            db.commit()
            return job.status
        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = job.started_at or utcnow()
        db.commit()
        errors_before = len(job.errors or [])
        ctx = JobContext(db, job)
        fn = REGISTRY[job.workflow]
        try:
            stats = fn(ctx) or {}
            job.stats = {**(job.stats or {}), **stats}
            # PARTIAL only if *this* attempt recorded item-level errors (earlier failed attempts don't count)
            job.status = JobStatus.PARTIAL if len(job.errors or []) > errors_before else JobStatus.SUCCEEDED
            job.finished_at = utcnow()
            db.commit()
        except JobCancelled as e:
            db.rollback()
            job = db.get(AutomationJob, job_id)
            job.status = JobStatus.CANCELLED
            job.finished_at = utcnow()
            job.log = [*(job.log or []), {"at": utcnow().isoformat(), "msg": f"Stopped: {e or 'cancelled'}"}]
            db.commit()
        except (RetryableError, TransientHTTPError, OSError) as e:
            db.rollback()
            job = db.get(AutomationJob, job_id)
            _record_failure(job, e)
            if job.attempts < job.max_attempts:
                delay = 30 * (2 ** (job.attempts - 1))
                job.status = JobStatus.QUEUED
                job.next_retry_at = utcnow() + timedelta(seconds=delay)
                db.commit()
                _schedule_retry(job.id, delay)
            else:
                job.status = JobStatus.FAILED
                job.finished_at = utcnow()
                db.commit()
        except Exception as e:  # noqa: BLE001 - permanent failure: record and stop
            db.rollback()
            job = db.get(AutomationJob, job_id)
            _record_failure(job, e)
            job.status = JobStatus.FAILED
            job.finished_at = utcnow()
            db.commit()
            log.exception("job %s failed", job_id)
        return job.status
    finally:
        db.close()


def _record_failure(job: AutomationJob, e: Exception) -> None:
    job.errors = [*(job.errors or []), {
        "at": utcnow().isoformat(), "attempt": job.attempts, "error": f"{type(e).__name__}: {e}"[:1000],
        "trace": traceback.format_exc()[-2000:],
    }]


def _schedule_retry(job_id: uuid.UUID, delay: int) -> None:
    from app.core.config import get_settings

    if get_settings().celery_eager:
        return  # tests drive retries explicitly via execute_job
    dispatch_job(job_id, countdown=delay)


def retry_job(db: Session, job: AutomationJob, user: User | None = None) -> AutomationJob:
    """Manual retry: creates a new job with the same params, linked to the original."""
    new, _ = start_job(db, job.workflow, params=job.params, trigger="manual", user=user, company_id=job.company_id,
                       campaign_id=job.campaign_id, parent_id=job.id)
    return new


def cancel_job(db: Session, job: AutomationJob, user: User | None = None) -> None:
    if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        job.status = JobStatus.CANCELLED
        job.finished_at = utcnow()
        audit(db, "workflow.cancelled", actor=user, entity_type="automation_job", entity_id=job.id)
        db.commit()
