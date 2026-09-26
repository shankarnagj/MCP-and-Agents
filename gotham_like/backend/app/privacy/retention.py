"""Retention policies and deletion (erasure) workflow."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DataSource, Entity, EntityIdentifier, LineageLink, SourceRecord, utcnow

ERASED = {"_erased": True, "note": "Content erased under an approved deletion / retention workflow."}


def execute_deletion(db: Session, entity_id: str) -> dict[str, Any]:
    """Erase personal data for an entity (and duplicates merged into it).

    * entity properties, label, search text, coordinates and identifiers are removed
    * source records for which the entity was the primary subject are redacted
    * relationships and events are kept as tombstoned structure (they may concern other parties)
    * the audit trail is retained (legal accountability) — it stores ids, not payloads
    """
    ids = [entity_id] + list(db.scalars(select(Entity.id).where(Entity.merged_into == entity_id)))
    primary_records = set(db.scalars(select(LineageLink.parent_id).where(
        LineageLink.child_kind == "entity", LineageLink.child_id.in_(ids), LineageLink.parent_kind == "source_record")))
    now = utcnow()
    db.execute(update(Entity).where(Entity.id.in_(ids)).values(
        properties={}, label="[ERASED]", search_text="", geom=None, lat=None, lon=None, deleted_at=now,
        provenance={"erased_at": now.isoformat()}))
    n_ident = db.execute(delete(EntityIdentifier).where(EntityIdentifier.entity_id.in_(ids))).rowcount
    n_rec = 0
    if primary_records:
        n_rec = db.execute(update(SourceRecord).where(SourceRecord.id.in_(primary_records)).values(payload=ERASED, deleted_at=now)).rowcount
    db.flush()
    return {"entities_erased": len(ids), "identifiers_removed": n_ident, "source_records_redacted": n_rec, "completed_at": now.isoformat()}


def retention_report(db: Session) -> dict[str, Any]:
    s = get_settings()
    now = utcnow()
    out = []
    for src in db.scalars(select(DataSource)):
        days = src.retention_days or s.retention_days_raw_records
        cutoff = now - timedelta(days=days)
        expired = db.scalar(select(func.count()).where(SourceRecord.source_id == src.id, SourceRecord.ingested_at < cutoff,
                                                       SourceRecord.deleted_at.is_(None)))
        out.append({"source_id": src.id, "retention_days": days, "expired_records": expired})
    return {"raw_records": out, "audit_retention_days": s.retention_days_audit,
            "note": "Run scripts/apply_retention.py to redact expired raw payloads. Derived entities keep lineage ids only."}


def apply_retention(db: Session) -> dict[str, int]:
    s = get_settings()
    now = utcnow()
    total = {}
    for src in db.scalars(select(DataSource)):
        cutoff = now - timedelta(days=src.retention_days or s.retention_days_raw_records)
        total[src.id] = db.execute(update(SourceRecord).where(SourceRecord.source_id == src.id, SourceRecord.ingested_at < cutoff,
                                                              SourceRecord.deleted_at.is_(None)).values(payload=ERASED, deleted_at=now)).rowcount
    db.flush()
    return total
