"""Investigation workspace: investigations, evidence board items, assertions, saved queries."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.deps import Principal
from app.config import DATA_DIR
from app.models import (
    Assertion,
    AssertionStatus,
    Entity,
    EpistemicStatus,
    Event,
    Investigation,
    InvestigationItem,
    Relationship,
    Role,
    SavedQuery,
    Signal,
    SourceRecord,
    new_id,
    utcnow,
)
from app.services.realtime import hub

ITEM_KINDS = {"entity", "relationship", "event", "note", "document", "source_record", "citation", "map", "chart", "timeline",
              "saved_query", "signal"}
REF_MODELS = {"entity": Entity, "relationship": Relationship, "event": Event, "source_record": SourceRecord, "signal": Signal}
UPLOAD_DIR = DATA_DIR / "uploads"
MAX_UPLOAD = 10 * 1024 * 1024
ALLOWED_MEDIA = {"application/pdf", "text/plain", "text/csv", "image/png", "image/jpeg", "application/json"}


class Conflict(Exception):
    pass


def can_write(user: Principal, inv: Investigation) -> bool:
    return user.role in (Role.ADMIN.value, Role.INVESTIGATOR.value) or inv.created_by == user.id or user.id in (inv.collaborators or [])


def inv_dict(inv: Investigation) -> dict[str, Any]:
    return {"id": inv.id, "name": inv.name, "description": inv.description, "status": inv.status, "scope": inv.scope,
            "collaborators": inv.collaborators, "created_by": inv.created_by, "created_at": inv.created_at.isoformat(),
            "updated_at": inv.updated_at.isoformat(), "version": inv.version}


def item_dict(it: InvestigationItem) -> dict[str, Any]:
    return {"id": it.id, "kind": it.kind, "ref_id": it.ref_id, "title": it.title, "content": it.content, "pinned": it.pinned,
            "epistemic_status": it.epistemic_status, "provenance": it.provenance, "created_by": it.created_by,
            "created_at": it.created_at.isoformat()}


def assertion_dict(a: Assertion) -> dict[str, Any]:
    return {"id": a.id, "investigation_id": a.investigation_id, "subject_ids": a.subject_ids, "statement": a.statement, "status": a.status,
            "analyst_confidence": a.analyst_confidence, "rationale": a.rationale, "evidence_refs": a.evidence_refs,
            "epistemic_status": a.epistemic_status, "label": "ANALYST ASSERTION — HYPOTHESIS" if a.status == "HYPOTHESIS" else f"ANALYST ASSERTION — {a.status}",
            "created_by": a.created_by, "created_at": a.created_at.isoformat(), "updated_at": a.updated_at.isoformat(), "history": a.history}


def _bump(inv: Investigation) -> None:
    inv.version += 1
    inv.updated_at = utcnow()


def create(db: Session, user: Principal, name: str, description: str = "", scope: dict | None = None, ip: str | None = None) -> Investigation:
    inv = Investigation(id=new_id("inv"), name=name, description=description, scope=scope or {}, created_by=user.id, collaborators=[])
    db.add(inv)
    db.flush()
    record(db, "investigation_create", user, "investigation", inv.id, new_value=inv_dict(inv), ip=ip)
    return inv


def update(db: Session, user: Principal, inv: Investigation, changes: dict[str, Any], expected_version: int | None, ip: str | None = None) -> Investigation:
    if expected_version is not None and expected_version != inv.version:
        raise Conflict(f"investigation was modified (version {inv.version}); reload and retry")
    before = inv_dict(inv)
    for k in ("name", "description", "status", "scope", "collaborators"):
        if k in changes and changes[k] is not None:
            setattr(inv, k, changes[k])
    _bump(inv)
    db.flush()
    record(db, "investigation_update", user, "investigation", inv.id, previous_value=before, new_value=inv_dict(inv), ip=ip)
    hub.publish(f"investigation:{inv.id}", "investigation.updated", {"id": inv.id, "version": inv.version, "by": user.username})
    return inv


def snapshot_provenance(db: Session, kind: str, ref_id: str) -> tuple[dict[str, Any], str]:
    model = REF_MODELS.get(kind)
    if model is None:
        return {}, EpistemicStatus.ANALYST_ASSERTION.value
    obj = db.get(model, ref_id)
    if obj is None:
        raise KeyError(f"{kind} {ref_id} not found")
    if kind == "entity":
        return {"source_ids": obj.source_ids[:50], "provenance": obj.provenance, "confidence": obj.confidence}, obj.epistemic_status
    if kind == "relationship":
        return {"source_records": obj.source_records, "provenance": obj.provenance, "confidence": obj.confidence,
                "analyst_modifications": obj.analyst_modifications}, obj.epistemic_status
    if kind == "event":
        return {"source": obj.source, "source_record_id": obj.source_record_id}, obj.epistemic_status
    if kind == "signal":
        return {"rule_id": obj.rule_id, "rule_version": obj.rule_version, "label": obj.label}, obj.epistemic_status
    return {"source_id": obj.source_id, "source_record_id": obj.source_record_id, "ingested_at": obj.ingested_at.isoformat(),
            "content_hash": obj.content_hash}, EpistemicStatus.RAW.value


def add_item(db: Session, user: Principal, inv: Investigation, kind: str, ref_id: str | None, title: str, content: dict[str, Any],
             ip: str | None = None) -> InvestigationItem:
    if kind not in ITEM_KINDS:
        raise ValueError(f"unknown item kind {kind}")
    prov, status = ({}, EpistemicStatus.ANALYST_ASSERTION.value)
    if kind in REF_MODELS:
        if not ref_id:
            raise ValueError(f"{kind} items require ref_id")
        prov, status = snapshot_provenance(db, kind, ref_id)
    elif kind == "citation":
        if not content.get("source_record_id") and not content.get("reference"):
            raise ValueError("citation requires source_record_id or reference")
        if content.get("source_record_id"):
            prov, _ = snapshot_provenance(db, "source_record", content["source_record_id"])
    elif kind == "saved_query":
        if not ref_id or db.get(SavedQuery, ref_id) is None:
            raise ValueError("saved_query item requires an existing saved query id")
    prov = {**prov, "pinned_by": user.username, "pinned_at": utcnow().isoformat()}
    it = InvestigationItem(id=new_id("itm"), investigation_id=inv.id, kind=kind, ref_id=ref_id, title=title[:300], content=content,
                           epistemic_status=status, provenance=prov, created_by=user.id)
    db.add(it)
    _bump(inv)
    db.flush()
    record(db, "investigation_update", user, "investigation", inv.id, new_value={"added_item": item_dict(it)}, ip=ip)
    hub.publish(f"investigation:{inv.id}", "item.added", {"investigation_id": inv.id, "item": item_dict(it), "by": user.username})
    return it


def remove_item(db: Session, user: Principal, inv: Investigation, item_id: str, ip: str | None = None) -> None:
    it = db.get(InvestigationItem, item_id)
    if it is None or it.investigation_id != inv.id:
        raise KeyError(item_id)
    before = item_dict(it)
    db.delete(it)
    _bump(inv)
    db.flush()
    record(db, "investigation_update", user, "investigation", inv.id, previous_value={"removed_item": before}, ip=ip)
    hub.publish(f"investigation:{inv.id}", "item.removed", {"investigation_id": inv.id, "item_id": item_id, "by": user.username})


def store_upload(data: bytes, filename: str, media_type: str) -> dict[str, Any]:
    if media_type not in ALLOWED_MEDIA:
        raise ValueError(f"media type {media_type} not allowed")
    if len(data) > MAX_UPLOAD:
        raise ValueError("file too large (10 MB max)")
    digest = hashlib.sha256(data).hexdigest()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / digest  # content-addressed; the client filename never touches the filesystem
    if not path.exists():
        path.write_bytes(data)
    return {"filename": Path(filename).name[:200], "sha256": digest, "size": len(data), "media_type": media_type}


def create_assertion(db: Session, user: Principal, statement: str, subject_ids: list[str], investigation_id: str | None, rationale: str,
                     evidence_refs: list[dict], analyst_confidence: str | None, ip: str | None = None) -> Assertion:
    for sid in subject_ids:
        if db.get(Entity, sid) is None and db.get(Relationship, sid) is None:
            raise KeyError(f"subject {sid} not found")
    a = Assertion(id=new_id("asr"), investigation_id=investigation_id, subject_ids=subject_ids, statement=statement,
                  status=AssertionStatus.HYPOTHESIS.value, analyst_confidence=analyst_confidence, rationale=rationale,
                  evidence_refs=evidence_refs, created_by=user.id,
                  history=[{"status": "HYPOTHESIS", "by": user.username, "at": utcnow().isoformat(), "note": "created"}])
    db.add(a)
    db.flush()
    record(db, "analyst_assertion", user, "assertion", a.id, new_value=assertion_dict(a), ip=ip)
    if investigation_id:
        inv = db.get(Investigation, investigation_id)
        if inv:
            _bump(inv)
        hub.publish(f"investigation:{investigation_id}", "assertion.created", {"assertion": assertion_dict(a), "by": user.username})
    return a


def update_assertion(db: Session, user: Principal, a: Assertion, status: str | None, note: str, rationale: str | None,
                     ip: str | None = None) -> Assertion:
    before = assertion_dict(a)
    if status:
        if status not in AssertionStatus.__members__:
            raise ValueError("invalid status")
        a.status = status
    if rationale is not None:
        a.rationale = rationale
    a.history = [*a.history, {"status": a.status, "by": user.username, "at": utcnow().isoformat(), "note": note}]
    db.flush()
    record(db, "analyst_assertion", user, "assertion", a.id, previous_value=before, new_value=assertion_dict(a), ip=ip)
    return a


def get_full(db: Session, inv: Investigation) -> dict[str, Any]:
    items = db.scalars(select(InvestigationItem).where(InvestigationItem.investigation_id == inv.id).order_by(InvestigationItem.created_at)).all()
    assertions = db.scalars(select(Assertion).where(Assertion.investigation_id == inv.id).order_by(Assertion.created_at)).all()
    queries = db.scalars(select(SavedQuery).where(SavedQuery.investigation_id == inv.id)).all()
    return {**inv_dict(inv), "items": [item_dict(i) for i in items], "assertions": [assertion_dict(a) for a in assertions],
            "saved_queries": [saved_query_dict(q) for q in queries],
            "counts": {k: sum(1 for i in items if i.kind == k) for k in sorted({i.kind for i in items})}}


def saved_query_dict(q: SavedQuery) -> dict[str, Any]:
    return {"id": q.id, "name": q.name, "description": q.description, "query_kind": q.query_kind, "query": q.query, "filters": q.filters,
            "parameters": q.parameters, "investigation_id": q.investigation_id, "created_by": q.created_by,
            "created_at": q.created_at.isoformat()}
