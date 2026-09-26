"""Append-only, hash-chained audit logging.

The database trigger (migration 0002) rejects UPDATE/DELETE/TRUNCATE; the hash
chain additionally makes any out-of-band tampering detectable via `verify_chain`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditLog, utcnow
from app.observability import request_id_var

AUDIT_ACTIONS = {
    "login", "login_failed", "logout", "search", "query", "entity_view", "graph_operation", "data_export",
    "investigation_create", "investigation_update", "analyst_assertion", "provenance_view", "timeline_query",
    "geo_query", "relationship_verify", "er_review", "rule_change", "alert_update", "ingestion", "user_admin",
    "deletion_request", "deletion_approve", "ontology_change", "access_denied", "pii_access",
}

_LOCK_KEY = 72_311_901  # advisory lock id serialising the hash chain


def _digest(prev_hash: str, row: dict[str, Any]) -> str:
    canonical = json.dumps(row, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


def _row_material(entry: AuditLog) -> dict[str, Any]:
    return {
        "ts": entry.ts.astimezone(UTC).isoformat(), "user_id": entry.user_id, "username": entry.username, "action": entry.action,
        "object_type": entry.object_type, "object_id": entry.object_id, "previous_value": entry.previous_value,
        "new_value": entry.new_value, "details": entry.details, "request_id": entry.request_id, "ip": entry.ip,
    }


def record(
    db: Session,
    action: str,
    user: Any | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    previous_value: dict | None = None,
    new_value: dict | None = None,
    details: dict | None = None,
    ip: str | None = None,
) -> AuditLog:
    if action not in AUDIT_ACTIONS:
        raise ValueError(f"unknown audit action {action}")
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    prev = db.scalar(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)) or "0" * 64
    entry = AuditLog(
        ts=utcnow(), user_id=getattr(user, "id", None), username=getattr(user, "username", None), action=action,
        object_type=object_type, object_id=None if object_id is None else str(object_id)[:200],
        previous_value=previous_value, new_value=new_value, details=details or {}, request_id=request_id_var.get(), ip=ip,
        prev_hash=prev,
    )
    entry.hash = _digest(prev, _row_material(entry))
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session, limit: int | None = None) -> dict[str, Any]:
    prev = "0" * 64
    checked = 0
    q = select(AuditLog).order_by(AuditLog.id)
    if limit:
        q = q.limit(limit)
    for entry in db.scalars(q).yield_per(1000):
        if entry.prev_hash != prev or _digest(prev, _row_material(entry)) != entry.hash:
            return {"valid": False, "broken_at": entry.id, "checked": checked}
        prev = entry.hash
        checked += 1
    return {"valid": True, "checked": checked, "head": prev}
