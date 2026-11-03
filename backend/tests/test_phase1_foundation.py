from fastapi.testclient import TestClient

from app.core import crypto
from app.models import Role
from app.services import settings_service as ss
from tests.conftest import PASSWORD, make_user


def test_health(app):
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json()["database"] == "ok"


def test_login_sets_httponly_cookie_and_me(app, db):
    make_user(db, "a@test.io")
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"email": "A@test.io", "password": PASSWORD})
        assert r.status_code == 200
        assert "httponly" in r.headers["set-cookie"].lower()
        me = c.get("/api/auth/me")
        assert me.status_code == 200 and me.json()["user"]["email"] == "a@test.io"


def test_bad_password_and_lockout(app, db):
    make_user(db, "a@test.io")
    with TestClient(app) as c:
        for _ in range(5):
            assert c.post("/api/auth/login", json={"email": "a@test.io", "password": "wrong"}).status_code == 401
        r = c.post("/api/auth/login", json={"email": "a@test.io", "password": PASSWORD})
        assert r.status_code == 423


def test_unauthenticated_rejected(app):
    with TestClient(app) as c:
        assert c.get("/api/users").status_code == 401
        assert c.get("/api/settings").status_code == 401


def test_csrf_required_for_cookie_mutations(admin_client):
    token = admin_client.headers.pop("X-CSRF-Token")
    r = admin_client.post("/api/users", json={"email": "x@test.io", "password": "Abcdefgh12!x", "role": "viewer"})
    assert r.status_code == 403
    admin_client.headers["X-CSRF-Token"] = token
    r = admin_client.post("/api/users", json={"email": "x@test.io", "password": "Abcdefgh12!x", "role": "viewer"})
    assert r.status_code == 201, r.text


def test_rbac_viewer_cannot_admin(viewer_client):
    assert viewer_client.get("/api/users").status_code == 403
    assert viewer_client.put("/api/settings/llm", json={"model_fast": "x"}).status_code == 403
    assert viewer_client.get("/api/settings/llm").status_code == 200


def test_cannot_remove_last_admin(admin_client):
    me = admin_client.get("/api/auth/me").json()["user"]
    r = admin_client.patch(f"/api/users/{me['id']}", json={"role": "viewer"})
    assert r.status_code == 400


def test_role_change_revokes_sessions(app, admin_client, db):
    u = make_user(db, "op2@test.io", Role.OPERATOR)
    with TestClient(app) as other:
        r = other.post("/api/auth/login", json={"email": "op2@test.io", "password": PASSWORD})
        assert r.status_code == 200
        admin_client.patch(f"/api/users/{u.id}", json={"role": "viewer"})
        assert other.get("/api/auth/me").status_code == 401


def test_settings_secret_encrypted_and_masked(admin_client, db):
    r = admin_client.put("/api/settings/llm", json={"provider": "openai_compatible", "api_key": "sk-secret-123456"})
    assert r.status_code == 200
    body = r.json()
    assert body["api_key"] == "" and body["api_key_is_set"] is True and body["api_key_masked"].endswith("3456")
    from app.models import Setting

    row = db.query(Setting).filter_by(key="llm").one()
    assert row.value["api_key"].startswith("enc:") and "sk-secret" not in row.value["api_key"]
    assert ss.get_section(db, "llm")["api_key"] == "sk-secret-123456"
    # blank keeps existing secret
    admin_client.put("/api/settings/llm", json={"api_key": "", "model_fast": "m"})
    db.expire_all()
    assert ss.get_section(db, "llm")["api_key"] == "sk-secret-123456"


def test_settings_validation(admin_client):
    assert admin_client.put("/api/settings/llm", json={"provider": "evil"}).status_code == 422
    assert admin_client.put("/api/settings/quality", json={"threshold": 500}).status_code == 422


def test_crypto_roundtrip():
    assert crypto.decrypt(crypto.encrypt("hello")) == "hello"


def test_security_headers(app):
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
