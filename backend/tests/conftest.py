from __future__ import annotations

import os

# Must be set before app modules are imported.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://agency:agency@localhost:5434/agency_test")
os.environ["ENVIRONMENT"] = "test"
os.environ["CELERY_EAGER"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6380/15")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Base, Role, User  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "Test-Password-123!"


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def make_user(db, email="admin@test.io", role=Role.ADMIN) -> User:
    u = User(email=email, full_name=email.split("@")[0], password_hash=hash_password(PASSWORD), role=role)
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def app():
    from app.main import app as fastapi_app

    return fastapi_app


def login(client: TestClient, email: str) -> TestClient:
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return client


@pytest.fixture
def admin_client(app, db):
    make_user(db, "admin@test.io", Role.ADMIN)
    with TestClient(app) as c:
        yield login(c, "admin@test.io")


@pytest.fixture
def operator_client(app, db):
    make_user(db, "op@test.io", Role.OPERATOR)
    with TestClient(app) as c:
        yield login(c, "op@test.io")


@pytest.fixture
def viewer_client(app, db):
    make_user(db, "viewer@test.io", Role.VIEWER)
    with TestClient(app) as c:
        yield login(c, "viewer@test.io")
