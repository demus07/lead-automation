from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import client_ip, get_current_user
from app.core.ratelimit import limiter
from app.core.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    create_session_token,
    csrf_for_session,
    decode_session_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.models import User
from app.models.base import utcnow
from app.schemas.common import LoginIn, Msg, PasswordChange, SessionOut, UserOut
from app.services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_FAILED = 5
LOCK_MINUTES = 15


def _set_session_cookies(response: Response, token: str, csrf: str) -> None:
    s = get_settings()
    max_age = s.access_token_minutes * 60
    response.set_cookie(
        SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=s.cookie_secure, samesite="lax",
        domain=s.cookie_domain, path="/",
    )
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=s.cookie_secure, samesite="lax",
        domain=s.cookie_domain, path="/",
    )


@router.post("/login", response_model=SessionOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    ip = client_ip(request) or "unknown"
    allowed, _ = limiter.hit(f"login:{ip}", s.login_rate_limit_per_minute)
    if not allowed:
        raise HTTPException(429, "Too many login attempts. Try again in a minute.")
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower(), User.deleted_at.is_(None)))
    now = utcnow()
    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(423, "Account temporarily locked after repeated failed logins.")
    if not user or not verify_password(body.password, user.password_hash) or not user.is_active:
        if user:
            user.failed_logins += 1
            if user.failed_logins >= MAX_FAILED:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_logins = 0
            audit(db, "auth.login_failed", entity_type="user", entity_id=user.id, ip=ip)
            db.commit()
        raise HTTPException(401, "Invalid email or password")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    token, sid = create_session_token(user.id, user.token_version)
    csrf = csrf_for_session(sid)
    _set_session_cookies(response, token, csrf)
    audit(db, "auth.login", actor=user, entity_type="user", entity_id=user.id, ip=ip)
    db.commit()
    return SessionOut(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/logout", response_model=Msg)
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    response.delete_cookie(SESSION_COOKIE, path="/", domain=get_settings().cookie_domain)
    response.delete_cookie(CSRF_COOKIE, path="/", domain=get_settings().cookie_domain)
    return Msg(message="Logged out")


@router.get("/me", response_model=SessionOut)
def me(request: Request, user: User = Depends(get_current_user)):
    token = request.cookies.get(SESSION_COOKIE)
    csrf = ""
    if token:
        csrf = csrf_for_session(decode_session_token(token).get("sid", ""))
    return SessionOut(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/change-password", response_model=Msg)
def change_password(
    body: PasswordChange,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    try:
        validate_password_strength(body.new_password)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # revoke other sessions
    token, sid = create_session_token(user.id, user.token_version)
    _set_session_cookies(response, token, csrf_for_session(sid))
    audit(db, "auth.password_changed", actor=user, entity_type="user", entity_id=user.id, ip=client_ip(request))
    db.commit()
    return Msg(message="Password changed. Other sessions have been signed out.")
