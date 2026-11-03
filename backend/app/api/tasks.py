from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api._common import PageParams, get_or_404, paginate
from app.core.db import get_db
from app.core.deps import require_operator, require_viewer
from app.models import Company, Task, User
from app.models.base import utcnow
from app.schemas.common import Msg
from app.schemas.crm import TaskIn, TaskOut, TaskPatch
from app.services.audit import audit

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _out(db: Session):
    def f(t: Task) -> dict:
        o = TaskOut.model_validate(t)
        if t.company_id:
            c = db.get(Company, t.company_id)
            o.company_name = c.name if c else None
        return o.model_dump()

    return f


@router.get("")
def list_tasks(status: str | None = "open", company_id: uuid.UUID | None = None, mine: bool = False,
               overdue: bool = False, pp: PageParams = Depends(), db: Session = Depends(get_db),
               user: User = Depends(require_viewer)):
    stmt = select(Task).where(Task.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Task.status == status)
    if company_id:
        stmt = stmt.where(Task.company_id == company_id)
    if mine:
        stmt = stmt.where(Task.assignee_id == user.id)
    if overdue:
        stmt = stmt.where(Task.due_at < utcnow())
    stmt = stmt.order_by(Task.due_at.asc().nullslast(), Task.created_at)
    return paginate(db, stmt, pp, _out(db))


@router.post("", status_code=201)
def create_task(body: TaskIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    t = Task(**body.model_dump())
    if not t.assignee_id:
        t.assignee_id = user.id
    db.add(t)
    db.flush()
    audit(db, "task.created", actor=user, entity_type="task", entity_id=t.id)
    db.commit()
    return _out(db)(t)


@router.patch("/{task_id}")
def update_task(task_id: uuid.UUID, body: TaskPatch, db: Session = Depends(get_db),
                user: User = Depends(require_operator)):
    t = get_or_404(db, Task, task_id)
    ch = body.model_dump(exclude_unset=True)
    for k, v in ch.items():
        setattr(t, k, v)
    if ch.get("status") == "done":
        t.completed_at = utcnow()
    db.commit()
    return _out(db)(t)


@router.delete("/{task_id}", response_model=Msg)
def delete_task(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    t = get_or_404(db, Task, task_id)
    t.deleted_at = utcnow()
    db.commit()
    return Msg(message="Task deleted")
