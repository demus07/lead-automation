from __future__ import annotations

import importlib
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging
from app.core.ratelimit import limiter
from app.services.state_machine import InvalidTransition

configure_logging()
log = logging.getLogger("app")

ROUTERS = [
    "auth", "users", "settings", "campaigns", "discovery", "companies", "contacts", "research",
    "opportunities", "drafts", "approvals", "email", "conversations", "tasks", "suppression",
    "workflows", "ai_usage", "analytics", "integrations", "knowledge", "audit", "dashboard",
]


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Agency Growth Engine API",
        version="1.0.0",
        description="Lead discovery, research, qualification and outreach drafting. "
        "No endpoint sends email: approved messages become unsent drafts in the connected mailbox.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"],
    )

    @app.middleware("http")
    async def security_and_rate_limit(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        if request.url.path.startswith("/api/") and request.url.path != "/api/health":
            ident = request.cookies.get("age_session", "")[-24:] or (request.client.host if request.client else "anon")
            allowed, remaining = limiter.hit(f"api:{ident}", s.rate_limit_per_minute)
            if not allowed:
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429,
                                    headers={"Retry-After": "60", "X-Request-ID": rid})
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not request.url.path.startswith("/api/docs") and not request.url.path.startswith("/api/redoc"):
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if s.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        log.info("%s %s %s %.0fms rid=%s", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - start) * 1000, rid)
        return response

    @app.exception_handler(InvalidTransition)
    async def _invalid_transition(_: Request, exc: InvalidTransition):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError):
        log.warning("integrity error: %s", exc.orig)
        return JSONResponse({"detail": "Conflict: a record with these unique values already exists"}, status_code=409)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return JSONResponse({"detail": "Validation error", "errors": errors}, status_code=422)

    @app.get("/api/health", tags=["system"])
    def health():
        status = {"status": "ok", "database": "ok", "redis": "ok"}
        try:
            with SessionLocal() as db:
                db.execute(text("select 1"))
        except Exception as e:  # pragma: no cover
            status.update(status="degraded", database=f"error: {type(e).__name__}")
        try:
            import redis

            redis.Redis.from_url(s.redis_url, socket_timeout=1, socket_connect_timeout=1).ping()
        except Exception as e:
            status.update(status="degraded", redis=f"error: {type(e).__name__}")
        code = 200 if status["database"] == "ok" else 503
        return JSONResponse(status, status_code=code)

    for name in ROUTERS:
        try:
            mod = importlib.import_module(f"app.api.{name}")
        except ModuleNotFoundError as e:
            if e.name == f"app.api.{name}":
                continue
            raise
        app.include_router(mod.router)
    return app


app = create_app()
