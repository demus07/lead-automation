"""Request dependencies: authentication, CSRF and role-based access control."""
from __future__ import annotations

import hmac
import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CSRF_HEADER, SESSION_COOKIE, csrf_for_session, decode_session_token
from app.models import Role, User

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ROLE_RANK = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token: str | None = None
    via_cookie = False
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    else:
        token = request.cookies.get(SESSION_COOKIE)
        via_cookie = token is not None
    if not token:
        raise _unauthorized()
    try:
        payload = decode_session_token(token)
    except jwt.PyJWTError:
        raise _unauthorized("Session expired or invalid") from None

    # CSRF: cookie-authenticated, state-changing requests must carry a matching header.
    if via_cookie and request.method not in SAFE_METHODS:
        header = request.headers.get(CSRF_HEADER, "")
        if not header or not hmac.compare_digest(header, csrf_for_session(payload.get("sid", ""))):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")

    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (KeyError, ValueError):
        raise _unauthorized() from None
    if not user or not user.is_active or user.deleted_at is not None:
        raise _unauthorized("Account disabled")
    if user.token_version != payload.get("ver"):
        raise _unauthorized("Session revoked")
    request.state.user = user
    return user


def require_role(minimum: Role) -> Callable[..., User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK[user.role] < ROLE_RANK[minimum]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return checker


require_viewer = require_role(Role.VIEWER)
require_operator = require_role(Role.OPERATOR)
require_admin = require_role(Role.ADMIN)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
