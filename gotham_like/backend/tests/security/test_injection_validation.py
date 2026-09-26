"""SQL injection, input validation and request hardening."""

import pytest
from sqlalchemy import func, select, text

PAYLOADS = [
    "' OR '1'='1", "'; DROP TABLE entities; --", "\" OR 1=1 --", "1); DELETE FROM audit_log; --", "%' AND pg_sleep(5) --",
    "\\'; SELECT pg_read_file('/etc/passwd'); --", "admin'--", "$$; DROP TABLE users; $$", "\x00", "a' UNION SELECT password_hash FROM users --",
]


def _counts(db):
    from app.models import AuditLog, Entity, User

    return (db.scalar(select(func.count()).select_from(Entity)), db.scalar(select(func.count()).select_from(User)),
            db.scalar(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")))


@pytest.mark.parametrize("p", PAYLOADS)
def test_search_injection(client, H, db, p):
    before = _counts(db)
    for q in (p, f"account:{p}", f"company:{p}", f"jurisdiction:{p}", f'"{p}"', f"{p}*"):
        r = client.post("/api/search", json={"query": q}, headers=H["analyst"])
        assert r.status_code in (200, 422), (q, r.status_code)
        if r.status_code == 200:
            assert all("password" not in str(x).lower() for x in r.json()["results"])
    assert _counts(db) == before


@pytest.mark.parametrize("p", PAYLOADS)
def test_path_param_and_query_param_injection(client, H, db, p):
    before = _counts(db)
    from urllib.parse import quote

    assert client.get(f"/api/entities/{quote(p, safe='')}", headers=H["analyst"]).status_code in (404, 422)
    ok = (200, 422) if "\x00" in p else (200,)  # NUL bytes are rejected up-front with 422
    assert client.get("/api/timeline", params={"entity_id": p, "event_type": p}, headers=H["analyst"]).status_code in ok
    assert client.get("/api/entities", params={"sort": p}, headers=H["analyst"]).status_code == 422
    assert client.get("/api/audit", params={"action": p, "username": p}, headers=H["admin"]).status_code in ok
    assert _counts(db) == before


@pytest.mark.parametrize("p", PAYLOADS)
def test_query_builder_injection(client, H, db, p):
    before = _counts(db)
    for pattern in (
        {"nodes": [{"var": "a", "type": "Account", "filters": [{"property": "status", "op": "=", "value": p}]}]},
        {"nodes": [{"var": "a", "type": "Account", "filters": [{"property": p, "op": "=", "value": "x"}]}]},
        {"nodes": [{"var": "a", "type": p}]},
        {"nodes": [{"var": "a", "type": "Account", "filters": [{"property": "status", "op": p, "value": "x"}]}]},
        {"nodes": [{"var": "a", "type": "Account", "ids": [p]}]},
    ):
        r = client.post("/api/query", json={"pattern": pattern}, headers=H["analyst"])
        assert r.status_code in (200, 422), r.text
    assert _counts(db) == before


def test_graph_and_geo_injection(client, H, db):
    before = _counts(db)
    for p in PAYLOADS:
        ok = (200, 422) if "\x00" in p else (200,)
        assert client.post("/api/graph/subgraph", json={"seeds": [p], "depth": 1, "filters": {"epistemic_statuses": [p]}}, headers=H["analyst"]).status_code in ok
        assert client.post("/api/graph/path", json={"source": p, "target": p}, headers=H["analyst"]).status_code in ok
        r = client.post("/api/geo/query", json={"geometry": {"type": "Polygon", "coordinates": p}}, headers=H["analyst"])
        assert r.status_code in (422, 500) and "Traceback" not in r.text
    assert _counts(db) == before


def test_errors_do_not_leak_internals(client, H):
    r = client.post("/api/geo/query", json={"geometry": {"type": "Polygon", "coordinates": [[["x"]]]}}, headers=H["analyst"])
    assert r.status_code in (422, 500)
    body = r.text.lower()
    assert "select" not in body and "psycopg" not in body and "traceback" not in body


@pytest.mark.parametrize("path,body", [
    ("/api/graph/subgraph", {"seeds": [], "depth": 1}),
    ("/api/graph/subgraph", {"seeds": ["a"] * 1000}),
    ("/api/graph/subgraph", {"seeds": ["a"], "depth": -1}),
    ("/api/graph/path", {"source": "a", "target": "b", "max_depth": 50}),
    ("/api/graph/path", {"source": "a", "target": "b", "mode": "telepathy"}),
    ("/api/search", {"query": "x" * 2000}),
    ("/api/search", {"query": "a", "limit": 100000}),
    ("/api/investigations", {"name": ""}),
    ("/api/investigations", {"name": "x" * 1000}),
    ("/api/export", {"format": "exe", "entity_ids": ["a"]}),
    ("/api/sources", {"id": "Bad Id!", "name": "x", "kind": "csv"}),
])
def test_input_validation(client, H, path, body):
    assert client.post(path, json=body, headers=H["admin"]).status_code == 422


def test_secret_like_config_rejected_and_secrets_encrypted(client, H, db):
    r = client.post("/api/sources", json={"id": "ext_pg", "name": "x", "kind": "postgres", "config": {"password": "hunter2"}}, headers=H["admin"])
    assert r.status_code == 422
    r = client.post("/api/sources", json={"id": "ext_pg2", "name": "x", "kind": "postgres", "config": {"table": "people"},
                                          "secret": "postgresql://u:hunter2@db/x"}, headers=H["admin"])
    assert r.status_code == 201 and r.json()["has_secret"] is True and "hunter2" not in r.text
    from app.models import DataSource

    stored = db.get(DataSource, "ext_pg2").secret_encrypted
    assert "hunter2" not in stored


def test_oversized_body_rejected(client, H):
    r = client.post("/api/search", content=b"{" + b" " * (13 * 1024 * 1024) + b"}", headers={**H["analyst"], "Content-Type": "application/json"})
    assert r.status_code == 413


def test_security_headers(client, H):
    r = client.get("/api/stats", headers=H["viewer"])
    for h in ("x-content-type-options", "x-frame-options", "content-security-policy", "referrer-policy", "cache-control"):
        assert h in r.headers
    assert r.headers["x-frame-options"] == "DENY"


def test_rate_limiting(client, H):
    from app.auth.ratelimit import RateLimiter

    rl = RateLimiter()
    results = [rl.hit("unit-test-key", 5)[0] for _ in range(7)]
    assert results == [True] * 5 + [False] * 2
    rl.reset()


def test_login_rate_limit(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "login_rate_limit_per_minute", 3)
    codes = [client.post("/api/auth/login", json={"username": "rl-user", "password": "x"}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and 429 in codes[3:]
