"""Bootstrap: migrations, demo users, synthetic data, geofence, rules and signals."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.config import get_settings
from app.ingestion.pipeline import IngestionResult
from app.models import Geofence, Role, User, new_id
from app.rules import engine
from app.services import geo
from app.services.cache import get_cache

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Development/demo credentials. Override with TESSERA_DEMO_PASSWORD; never use in production.
DEMO_USERS = [
    ("admin", "Demo Administrator", Role.ADMIN),
    ("investigator", "Demo Investigator", Role.INVESTIGATOR),
    ("analyst", "Demo Analyst", Role.ANALYST),
    ("viewer", "Demo Viewer", Role.VIEWER),
]


def demo_password() -> str:
    return os.environ.get("TESSERA_DEMO_PASSWORD", "Demo-Passw0rd!")


def migrate(database_url: str | None = None) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    if database_url:
        cfg.attributes["database_url"] = database_url
    command.upgrade(cfg, "head")


def seed_users(db: Session, rounds: int | None = None) -> list[str]:
    created = []
    pw = hash_password(demo_password(), rounds=rounds)
    for username, name, role in DEMO_USERS:
        if db.scalar(select(User).where(User.username == username)) is None:
            db.add(User(id=new_id("usr"), username=username, display_name=name, password_hash=pw, role=role.value))
            created.append(username)
    db.flush()
    return created


def seed_geofence(db: Session) -> None:
    if db.scalar(select(Geofence).where(Geofence.name == "Harbor Plaza perimeter")) is None:
        d = 0.006
        lat, lon = 51.45, 3.60
        ring = [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]
        geo.create_geofence(db, "Harbor Plaza perimeter", {"type": "Polygon", "coordinates": [ring]}, "system",
                            {"note": "Synthetic demonstration geofence"})


def seed_rules_and_signals(db: Session, ingestion: list[IngestionResult] | None = None, baseline: bool = True) -> dict:
    """baseline=True: the initial load establishes the baseline, so change-driven rules
    (new relationship / source change) are not evaluated against it."""
    engine.load_rules(db, get_settings().rules_path)
    results = engine.evaluate_all(db)
    if ingestion and not baseline:
        ctx = {"new_relationship_ids": [r for res in ingestion for r in res.new_relationship_ids],
               "changed_record_ids": [r for res in ingestion for r in res.changed_record_ids]}
        results += engine.evaluate_all(db, ctx=ctx, kinds={"new_relationship", "source_change"})
    db.flush()
    get_cache().bump()
    return {r["rule"]: {"candidates": r["drafts"], "new_signals": len(r["new_signals"]), "new_alerts": len(r["new_alerts"])} for r in results}
