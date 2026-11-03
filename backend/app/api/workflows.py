from __future__ import annotations

import uuid
from datetime import datetime

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api._common import PageParams, get_or_404, paginate
from app.core.db import get_db
from app.core.deps import require_admin, require_operator, require_viewer
from app.models import AutomationJob, JobStatus, User, WorkflowSchedule
from app.schemas.common import ORM
from app.services.audit import audit
from app.workflows import load_workflows
from app.workflows.engine import DESCRIPTIONS, REGISTRY, cancel_job, retry_job, start_job
from app.workflows.scheduler import ensure_default_schedules, next_run

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

LABELS = {
    "discovery": "1 · Discovery", "research": "2 · Research", "contacts": "3 · Contacts",
    "qualification": "4 · Qualification", "drafting": "5 · Draft generation", "approval": "6 · Mailbox drafts",
    "replies": "7 · Reply monitoring", "maintenance": "Maintenance & retention",
}


class JobOut(ORM):
    id: uuid.UUID
    workflow: str
    trigger: str
    status: str
    params: dict
    stats: dict
    errors: list
    log: list
    attempts: int
    max_attempts: int
    started_at: datetime | None
    finished_at: datetime | None
    next_retry_at: datetime | None
    company_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    created_at: datetime


class ScheduleOut(ORM):
    workflow: str
    cron: str
    enabled: bool
    paused: bool
    batch_size: int
    params: dict
    last_run_at: datetime | None
    next_run_at: datetime | None


class SchedulePatch(BaseModel):
    cron: str | None = Field(None, max_length=100)
    enabled: bool | None = None
    paused: bool | None = None
    batch_size: int | None = Field(None, ge=0, le=500)


class RunIn(BaseModel):
    params: dict = Field(default_factory=dict)


@router.get("")
def list_workflows(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    load_workflows()
    ensure_default_schedules(db)
    db.commit()
    scheds = {s.workflow: s for s in db.scalars(select(WorkflowSchedule)).all()}
    out = []
    for name in REGISTRY:
        last = db.scalar(select(AutomationJob).where(AutomationJob.workflow == name)
                         .order_by(AutomationJob.created_at.desc()).limit(1))
        counts = dict(db.execute(select(AutomationJob.status, func.count()).where(
            AutomationJob.workflow == name).group_by(AutomationJob.status)).all())
        out.append({
            "workflow": name, "label": LABELS.get(name, name), "description": DESCRIPTIONS.get(name, ""),
            "schedule": ScheduleOut.model_validate(scheds[name]).model_dump() if name in scheds else None,
            "last_job": JobOut.model_validate(last).model_dump() if last else None,
            "counts": {k.value: v for k, v in counts.items()},
        })
    g = scheds.get("__global__")
    return {"workflows": out, "global_paused": bool(g and g.paused)}


@router.post("/pause-all")
def pause_all(paused: bool = True, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    g = db.scalar(select(WorkflowSchedule).where(WorkflowSchedule.workflow == "__global__"))
    if not g:
        g = WorkflowSchedule(workflow="__global__", cron="* * * * *", enabled=False, paused=paused)
        db.add(g)
    g.paused = paused
    audit(db, "workflow.global_pause" if paused else "workflow.global_resume", actor=user)
    db.commit()
    return {"global_paused": paused}


@router.patch("/{name}/schedule")
def update_schedule(name: str, body: SchedulePatch, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    load_workflows()
    if name not in REGISTRY:
        raise HTTPException(404, "Unknown workflow")
    ensure_default_schedules(db)
    s = db.scalar(select(WorkflowSchedule).where(WorkflowSchedule.workflow == name))
    ch = body.model_dump(exclude_unset=True)
    if "cron" in ch:
        if not croniter.is_valid(ch["cron"]):
            raise HTTPException(422, "Invalid cron expression")
        s.cron = ch["cron"]
        s.next_run_at = next_run(s.cron)
    for k in ("enabled", "paused", "batch_size"):
        if k in ch:
            setattr(s, k, ch[k])
    audit(db, "workflow.schedule_updated", actor=user, entity_type="workflow", entity_id=None,
          detail={"workflow": name, **ch})
    db.commit()
    return ScheduleOut.model_validate(s)


@router.post("/{name}/run")
def run_workflow(name: str, body: RunIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    load_workflows()
    if name not in REGISTRY:
        raise HTTPException(404, "Unknown workflow")
    if name == "maintenance" and user.role.value != "admin":
        raise HTTPException(403, "Admin only")
    allowed = {"campaign_id", "company_ids", "sources", "query", "limit", "batch_size", "force", "chain"}
    params = {k: v for k, v in body.params.items() if k in allowed}
    job, _ = start_job(db, name, params=params, user=user)
    db.refresh(job)
    return JobOut.model_validate(job)


@router.get("/jobs")
def list_jobs(workflow: str | None = None, status: str | None = None, company_id: uuid.UUID | None = None,
              campaign_id: uuid.UUID | None = None,
              pp: PageParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    stmt = select(AutomationJob).order_by(AutomationJob.created_at.desc())
    if workflow:
        stmt = stmt.where(AutomationJob.workflow == workflow)
    if status:
        stmt = stmt.where(AutomationJob.status == JobStatus(status))
    if company_id:
        stmt = stmt.where(AutomationJob.company_id == company_id)
    if campaign_id:
        stmt = stmt.where(AutomationJob.campaign_id == campaign_id)
    return paginate(db, stmt, pp, lambda j: JobOut.model_validate(j))


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return get_or_404(db, AutomationJob, job_id)


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry(job_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    load_workflows()
    job = get_or_404(db, AutomationJob, job_id)
    if job.status not in (JobStatus.FAILED, JobStatus.PARTIAL, JobStatus.CANCELLED, JobStatus.SKIPPED):
        raise HTTPException(409, "Only finished jobs can be retried")
    new = retry_job(db, job, user)
    db.refresh(new)
    return new


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel(job_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    job = get_or_404(db, AutomationJob, job_id)
    cancel_job(db, job, user)
    return job
