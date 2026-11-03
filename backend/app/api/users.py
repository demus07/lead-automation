from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import client_ip, require_admin
from app.core.security import hash_password, validate_password_strength
from app.models import Role, User
from app.models.base import utcnow
from app.schemas.common import Msg, UserCreate, UserOut, UserUpdate
from app.services.audit import audit

router = APIRouter(prefix="/api/users", tags=["users"])


def _get(db: Session, user_id: uuid.UUID) -> User:
    u = db.get(User, user_id)
    if not u or u.deleted_at:
        raise HTTPException(404, "User not found")
    return u


def _admins_remaining(db: Session, excluding: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(User).where(
            User.role == Role.ADMIN, User.is_active.is_(True), User.deleted_at.is_(None), User.id != excluding
        )
    )


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.created_at)).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        validate_password_strength(body.password)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    exists = db.scalar(select(User).where(func.lower(User.email) == body.email.lower(), User.deleted_at.is_(None)))
    if exists:
        raise HTTPException(409, "A user with this email already exists")
    u = User(email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password),
             role=Role(body.role))
    db.add(u)
    db.flush()
    audit(db, "user.created", actor=admin, entity_type="user", entity_id=u.id, detail={"role": body.role},
          ip=client_ip(request))
    db.commit()
    return u


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    u = _get(db, user_id)
    changes = body.model_dump(exclude_unset=True)
    demoting = ("role" in changes and changes["role"] != "admin") or changes.get("is_active") is False
    if u.role == Role.ADMIN and demoting and _admins_remaining(db, u.id) == 0:
        raise HTTPException(400, "Cannot remove the last active admin")
    if "full_name" in changes:
        u.full_name = changes["full_name"]
    if "role" in changes:
        u.role = Role(changes["role"])
        u.token_version += 1
    if "is_active" in changes:
        u.is_active = changes["is_active"]
        u.token_version += 1
    if changes.get("password"):
        try:
            validate_password_strength(changes["password"])
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        u.password_hash = hash_password(changes["password"])
        u.token_version += 1
    changes.pop("password", None)
    audit(db, "user.updated", actor=admin, entity_type="user", entity_id=u.id, detail=changes, ip=client_ip(request))
    db.commit()
    return u


@router.post("/{user_id}/revoke-sessions", response_model=Msg)
def revoke_sessions(user_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = _get(db, user_id)
    u.token_version += 1
    audit(db, "user.sessions_revoked", actor=admin, entity_type="user", entity_id=u.id)
    db.commit()
    return Msg(message="Sessions revoked")


@router.delete("/{user_id}", response_model=Msg)
def delete_user(user_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = _get(db, user_id)
    if u.id == admin.id:
        raise HTTPException(400, "You cannot delete your own account")
    if u.role == Role.ADMIN and _admins_remaining(db, u.id) == 0:
        raise HTTPException(400, "Cannot delete the last admin")
    u.deleted_at = utcnow()
    u.is_active = False
    u.token_version += 1
    audit(db, "user.deleted", actor=admin, entity_type="user", entity_id=u.id)
    db.commit()
    return Msg(message="User deleted")
