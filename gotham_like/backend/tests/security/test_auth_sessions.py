"""Authentication, session management, token handling."""

import time

import jwt
import pytest

from app.config import get_settings
from tests.conftest import PASSWORD, login


def test_login_success_and_failure(client):
    ok = client.post("/api/auth/login", json={"username": "analyst", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "ANALYST"
    bad = client.post("/api/auth/login", json={"username": "analyst", "password": "wrong"})
    unknown = client.post("/api/auth/login", json={"username": "ghost", "password": "wrong"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()  # no user enumeration


def test_lockout_after_repeated_failures(client, db):
    from app.auth.security import hash_password
    from app.models import User, new_id

    db.add(User(id=new_id("usr"), username="lockme", password_hash=hash_password(PASSWORD, rounds=4), role="VIEWER"))
    db.commit()
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "lockme", "password": "nope"})
    assert client.post("/api/auth/login", json={"username": "lockme", "password": PASSWORD}).status_code == 401  # locked even with right password


def test_requests_without_or_with_bad_tokens(client):
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/stats", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/stats", headers={"Authorization": "Basic abc"}).status_code == 401
    forged = jwt.encode({"sub": "x", "sid": "y", "exp": int(time.time()) + 60, "iss": "tessera", "role": "ADMIN"}, "wrong-secret-wrong-secret-wrong-secret", "HS256")
    assert client.get("/api/stats", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_logout_revokes_session(client):
    tok = login(client, "analyst")
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/auth/me", headers=h).status_code == 200
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_token_for_valid_session_but_escalated_role_claim_is_ignored(client):
    """Role is read from the database; a (validly signed) token claiming ADMIN grants nothing extra."""
    tok = login(client, "viewer")
    claims = jwt.decode(tok, options={"verify_signature": False})
    claims["role"] = "ADMIN"
    escalated = jwt.encode(claims, get_settings().secret_key, "HS256")
    r = client.get("/api/audit", headers={"Authorization": f"Bearer {escalated}"})
    assert r.status_code == 403


def test_idle_session_expires(client, db):
    from datetime import timedelta

    from app.models import UserSession, utcnow

    tok = login(client, "analyst")
    sid = jwt.decode(tok, options={"verify_signature": False})["sid"]
    s = db.get(UserSession, sid)
    s.last_seen_at = utcnow() - timedelta(minutes=get_settings().session_idle_minutes + 1)
    db.commit()
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_disabled_user_sessions_revoked(client, H, db):
    from app.models import User
    from sqlalchemy import select

    r = client.post("/api/users", json={"username": "tempuser", "password": "Temp-Passw0rd-1", "role": "ANALYST"}, headers=H["admin"])
    assert r.status_code == 201
    tok = login(client, "tempuser", "Temp-Passw0rd-1")
    uid = db.scalar(select(User.id).where(User.username == "tempuser"))
    client.patch(f"/api/users/{uid}", json={"is_active": False}, headers=H["admin"])
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


@pytest.mark.parametrize("pw", ["short", "alllowercase-letters", "NoDigitsOrSymbolsHere"])
def test_weak_passwords_rejected(client, H, pw):
    r = client.post("/api/users", json={"username": "weakling", "password": pw, "role": "VIEWER"}, headers=H["admin"])
    assert r.status_code == 422


def test_admin_cannot_demote_self(client, H):
    me = client.get("/api/auth/me", headers=H["admin"]).json()
    assert client.patch(f"/api/users/{me['id']}", json={"role": "VIEWER"}, headers=H["admin"]).status_code == 400
