"""Celery application. Start with:

    celery -A app.worker worker -Q default,research,ai,email
    celery -A app.worker beat
"""
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
_s = get_settings()

celery_app = Celery("agency_growth_engine", broker=_s.redis_url, backend=_s.redis_url)
celery_app.conf.update(
    task_acks_late=True,  # a crashed worker's task is redelivered
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_time_limit=60 * 60,
    task_soft_time_limit=55 * 60,
    broker_connection_retry_on_startup=True,
    result_expires=24 * 3600,
    timezone="UTC",
    beat_schedule={
        "scheduler-tick": {"task": "app.worker.scheduler_tick", "schedule": 60.0},
        "recover-stale-jobs": {"task": "app.worker.recover_stale_jobs", "schedule": 300.0},
    },
    task_always_eager=_s.celery_eager,
)
app = celery_app


@celery_app.task(name="app.worker.run_job_task", bind=True, max_retries=0)
def run_job_task(self, job_id: str) -> str | None:
    from app.workflows import load_workflows
    from app.workflows.engine import execute_job

    load_workflows()
    status = execute_job(job_id)
    return status.value if status else None


@celery_app.task(name="app.worker.scheduler_tick")
def scheduler_tick() -> list[str]:
    from app.core.db import SessionLocal
    from app.workflows.scheduler import tick

    with SessionLocal() as db:
        return tick(db)


@celery_app.task(name="app.worker.recover_stale_jobs")
def recover_stale_jobs() -> int:
    """Re-queue jobs stuck in RUNNING (worker crash) or QUEUED with a missed retry."""
    from app.core.db import SessionLocal
    from app.workflows.recovery import recover

    with SessionLocal() as db:
        return recover(db)
