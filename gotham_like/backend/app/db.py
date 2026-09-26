"""Database engine / session management (PostgreSQL + PostGIS)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _instrument(engine: Engine) -> None:
    """Record per-statement timing for the /metrics endpoint."""
    from app.observability import DB_QUERY_SECONDS, SLOW_QUERY_LOGGER

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        conn.info.setdefault("query_start", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        elapsed = time.perf_counter() - conn.info["query_start"].pop()
        op = statement.lstrip().split(" ", 1)[0].upper()[:10]
        DB_QUERY_SECONDS.labels(operation=op).observe(elapsed)
        if elapsed > 0.5:
            SLOW_QUERY_LOGGER.warning("slow_query", extra={"elapsed_ms": round(elapsed * 1000, 1), "sql": statement[:300]})


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20, future=True)
        _instrument(_engine)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def reset_engine() -> None:
    """Dispose the engine (used by tests after changing TESSERA_DATABASE_URL)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def SessionLocal() -> Session:  # noqa: N802 - factory mimics sessionmaker
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
