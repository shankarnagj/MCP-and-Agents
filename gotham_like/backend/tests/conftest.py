"""Test configuration.

Integration tests run against a dedicated PostgreSQL/PostGIS database
(TESSERA_TEST_DATABASE_URL, default tessera_test) and Redis DB 15. The schema is
rebuilt through the real Alembic migrations and the full synthetic dataset is
loaded once per session through the real ingestion pipeline.
"""

from __future__ import annotations

import os

import pytest

TEST_DB = os.environ.get("TESSERA_TEST_DATABASE_URL", "postgresql+psycopg://tessera:tessera@localhost:5432/tessera_test")
os.environ["TESSERA_DATABASE_URL"] = TEST_DB
os.environ.setdefault("TESSERA_REDIS_URL", "redis://localhost:6379/15")
os.environ["TESSERA_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["TESSERA_LOGIN_RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["TESSERA_LOG_LEVEL"] = "WARNING"
os.environ.setdefault("TESSERA_DEMO_PASSWORD", "Test-Passw0rd!")

from sqlalchemy import create_engine, text  # noqa: E402

PASSWORD = os.environ["TESSERA_DEMO_PASSWORD"]


def _reset_schema() -> None:
    eng = create_engine(TEST_DB, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
        c.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    eng.dispose()


def _flush_redis() -> None:
    try:
        import redis

        redis.Redis.from_url(os.environ["TESSERA_REDIS_URL"]).flushdb()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture(scope="session")
def seeded():
    """Migrated + seeded test database (shared by all integration tests)."""
    from app.config import get_settings
    from app.db import SessionLocal, reset_engine
    from app.services.demo_loader import load_demo
    from app.services.seed import migrate, seed_geofence, seed_rules_and_signals, seed_users

    get_settings.cache_clear()
    reset_engine()
    _flush_redis()
    _reset_schema()
    migrate(TEST_DB)
    with SessionLocal() as db:
        seed_users(db, rounds=4)
        seed_geofence(db)
        db.commit()
        report = load_demo(db)
        results = report.pop("results")
        rules = seed_rules_and_signals(db, results)
        db.commit()
    return {"report": report, "rules": rules}


@pytest.fixture(scope="session")
def client(seeded):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


_tokens: dict[str, str] = {}


def login(client, username: str, password: str = PASSWORD) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def tokens(client):
    return {role: login(client, role) for role in ("admin", "investigator", "analyst", "viewer")}


@pytest.fixture(scope="session")
def H(tokens):
    """Auth headers per role: H['analyst']"""
    return {role: {"Authorization": f"Bearer {tok}"} for role, tok in tokens.items()}


@pytest.fixture()
def db(seeded):
    from app.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(scope="session")
def ids(client, H):
    """Well-known ids from the planted synthetic scenarios."""
    from app.ingestion.mapping import entity_id

    return {
        "shared_device": entity_id("Device", "DV-7F3A-SHARED"),
        "suspicious_ip": entity_id("IPAddress", "203.0.113.66"),
        "merchant_org": entity_id("Organization", "ORG-0000"),
        "merchant_account": entity_id("Account", "ACC-9000001"),
        "aml_account": entity_id("Account", "ACC-9000002"),
        "aml_person": entity_id("Person", "P-00007"),
        "layer1": entity_id("Organization", "ORG-0001"),
        "layer2": entity_id("Organization", "ORG-0002"),
        "harbor": entity_id("Location", "LOC-0001"),
        "shipment": entity_id("Shipment", "SHP-000042"),
        "supplier": entity_id("Organization", "ORG-0003"),
        "customer": entity_id("Organization", "ORG-0004"),
        "domain": entity_id("Domain", "update-portal.example"),
    }
