"""Database migration tests: upgrade, downgrade, re-upgrade, and model/migration parity."""

import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.db import Base
from app.services.seed import BACKEND_DIR

ADMIN_URL = os.environ["TESSERA_DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
MIG_DB = "tessera_migration_test"


@pytest.fixture(scope="module")
def mig_url():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {MIG_DB}"))
        c.execute(text(f"CREATE DATABASE {MIG_DB}"))
    url = os.environ["TESSERA_DATABASE_URL"].rsplit("/", 1)[0] + f"/{MIG_DB}"
    eng = create_engine(url, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    eng.dispose()
    yield url
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {MIG_DB} WITH (FORCE)"))
    admin.dispose()


def _cfg(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["database_url"] = url
    return cfg


def test_upgrade_downgrade_upgrade(mig_url):
    cfg = _cfg(mig_url)
    command.upgrade(cfg, "head")
    eng = create_engine(mig_url)
    tables = set(inspect(eng).get_table_names())
    assert {"entities", "relationships", "events", "lineage_links", "audit_log", "investigations", "assertions", "signals", "alerts"} <= tables
    with eng.connect() as c:
        triggers = {r[0] for r in c.execute(text("SELECT tgname FROM pg_trigger WHERE tgrelid = 'audit_log'::regclass"))}
        assert {"audit_log_no_update", "audit_log_no_truncate"} <= triggers
        idx = {r[0] for r in c.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname='public'"))}
    for required in ("idx_entities_geom", "idx_events_geom", "ix_entities_type", "ix_rel_source_type", "ix_rel_target_type", "ix_events_timestamp",
                     "ix_relationships_type", "ix_entities_search_trgm", "ix_events_entity_ids", "ix_inv_items_inv_kind", "ix_rel_live_source",
                     "ix_entities_source_ids", "ix_rel_source_records"):
        assert required in idx, required
    command.downgrade(cfg, "base")
    assert "entities" not in set(inspect(create_engine(mig_url)).get_table_names())
    command.upgrade(cfg, "head")
    eng.dispose()


def test_models_match_migrations(mig_url):
    """Autogenerate against the migrated schema must produce no diff."""
    import app.models  # noqa: F401
    from tests.integration.migrations_env_filter import include_object

    eng = create_engine(mig_url)
    with eng.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"include_object": include_object, "compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    eng.dispose()
    assert diff == [], diff
