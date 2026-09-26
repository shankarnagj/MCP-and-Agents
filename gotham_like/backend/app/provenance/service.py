"""Provenance & lineage: "Why does this exist, and which data supports it?"

Any object id (entity, relationship, event, source record, signal, assertion)
can be traced upstream to the original source records and downstream to what was
derived from it.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.rbac import P_PII, has_permission
from app.models import (
    Assertion,
    DataSource,
    Entity,
    Event,
    IngestionRun,
    LineageLink,
    Relationship,
    Signal,
    SourceRecord,
)
from app.ontology import Ontology
from app.services.serialize import entity_dict, event_dict, relationship_dict

MAX_LINEAGE_NODES = 500


def _kind_of(db: Session, obj_id: str) -> tuple[str, Any] | None:
    for kind, model in (("entity", Entity), ("relationship", Relationship), ("event", Event), ("source_record", SourceRecord),
                        ("signal", Signal), ("assertion", Assertion)):
        obj = db.get(model, obj_id)
        if obj is not None:
            return kind, obj
    return None


def source_record_view(db: Session, rec: SourceRecord, role: str) -> dict[str, Any]:
    src = db.get(DataSource, rec.source_id)
    run = db.get(IngestionRun, rec.ingestion_run_id)
    return {
        "id": rec.id,
        "source": {"id": rec.source_id, "name": src.name if src else None, "kind": src.kind if src else None,
                   "classification": src.classification if src else None},
        "source_record_id": rec.source_record_id,
        "record_type": rec.record_type,
        "ingestion_timestamp": rec.ingested_at.isoformat(),
        "ingestion_run": rec.ingestion_run_id,
        "ingestion_run_status": run.status if run else None,
        "transformation_version": rec.transformation_version,
        "content_hash": rec.content_hash,
        # raw payloads may contain personal data – only for roles cleared for PII
        "payload": rec.payload if has_permission(role, P_PII) else "[withheld: requires pii:view]",
        "deleted": rec.deleted_at is not None,
        "epistemic_status": "RAW",
    }


def lineage_graph(db: Session, kind: str, obj_id: str, direction: str = "up", max_nodes: int = MAX_LINEAGE_NODES) -> dict[str, Any]:
    """BFS over lineage_links. up = towards sources, down = towards derived data."""
    nodes = {(kind, obj_id)}
    edges = []
    queue = deque([(kind, obj_id)])
    truncated = False
    while queue:
        k, i = queue.popleft()
        if direction == "up":
            links = db.scalars(select(LineageLink).where(LineageLink.child_kind == k, LineageLink.child_id == i).limit(200)).all()
            nxt = [(lk.parent_kind, lk.parent_id, lk) for lk in links]
        else:
            links = db.scalars(select(LineageLink).where(LineageLink.parent_kind == k, LineageLink.parent_id == i).limit(200)).all()
            nxt = [(lk.child_kind, lk.child_id, lk) for lk in links]
        for nk, ni, link in nxt:
            edges.append({"from": f"{link.parent_kind}:{link.parent_id}", "to": f"{link.child_kind}:{link.child_id}",
                          "transformation": link.transformation, "transformation_version": link.transformation_version,
                          "at": link.created_at.isoformat(), "details": {k2: v for k2, v in (link.details or {}).items()
                                                                         if k2 in ("run", "by", "match")}})
            if (nk, ni) not in nodes:
                if len(nodes) >= max_nodes:
                    truncated = True
                    break
                nodes.add((nk, ni))
                queue.append((nk, ni))
    return {"direction": direction, "nodes": [f"{k}:{i}" for k, i in sorted(nodes)], "edges": edges, "truncated": truncated}


def provenance(db: Session, ontology: Ontology, obj_id: str, role: str) -> dict[str, Any]:
    found = _kind_of(db, obj_id)
    if found is None:
        raise KeyError(obj_id)
    kind, obj = found
    out: dict[str, Any] = {"id": obj_id, "kind": kind}
    record_ids: list[str] = []
    if kind == "entity":
        out["object"] = entity_dict(obj, ontology, role)
        record_ids = list(obj.source_ids)
        out["entity_resolution"] = obj.provenance.get("resolution", [])
        if obj.merged_into:
            out["merged_into"] = obj.merged_into
        out["why"] = (
            f"Entity {obj.type} '{out['object']['label']}' was derived from {len(record_ids)} source record(s) "
            f"by declarative mappings" + (f" and merged with {len(out['entity_resolution'])} duplicate(s) by deterministic entity resolution"
                                         if out["entity_resolution"] else "") + "."
        )
    elif kind == "relationship":
        out["object"] = relationship_dict(obj)
        record_ids = list(obj.source_records)
        out["analyst_modifications"] = obj.analyst_modifications
        prov = obj.provenance or {}
        out["why"] = (
            f"{obj.type} exists because source record(s) {', '.join(record_ids[:3])}{'…' if len(record_ids) > 3 else ''} "
            f"from source '{prov.get('source', 'unknown')}' were mapped by '{prov.get('transformation', 'unknown')}' "
            f"(version {prov.get('transformation_version', '?')}). Status: {obj.epistemic_status}; confidence {obj.confidence:.2f}."
        )
    elif kind == "event":
        out["object"] = event_dict(obj)
        record_ids = [obj.source_record_id] if obj.source_record_id else []
        out["why"] = f"Event '{obj.event_type}' was recorded in source '{obj.source}' at {obj.timestamp.isoformat()}."
    elif kind == "source_record":
        out["object"] = source_record_view(db, obj, role)
        out["why"] = "This is an unmodified record as received from the source system (RAW)."
    elif kind == "signal":
        out["object"] = {"id": obj.id, "label": obj.label, "rule_id": obj.rule_id, "rule_version": obj.rule_version, "score": obj.score,
                         "entity_ids": obj.entity_ids, "evidence": obj.evidence, "explanation": obj.explanation,
                         "epistemic_status": obj.epistemic_status}
        out["why"] = f"Produced by deterministic rule {obj.rule_id} v{obj.rule_version}. It is an ANALYTICAL SIGNAL, not a finding."
    elif kind == "assertion":
        out["object"] = {"id": obj.id, "statement": obj.statement, "status": obj.status, "created_by": obj.created_by,
                         "created_at": obj.created_at.isoformat(), "evidence_refs": obj.evidence_refs, "history": obj.history,
                         "epistemic_status": obj.epistemic_status}
        out["why"] = "Created by an analyst. Analyst assertions are hypotheses and are never merged with source-derived facts."
    records = db.scalars(select(SourceRecord).where(SourceRecord.id.in_(record_ids[:200]))).all() if record_ids else []
    out["source_records"] = [source_record_view(db, r, role) for r in records]
    out["source_records_total"] = len(record_ids)
    out["lineage_upstream"] = lineage_graph(db, kind, obj_id, "up")
    out["lineage_downstream"] = lineage_graph(db, kind, obj_id, "down", max_nodes=100)
    out["epistemic_status"] = out.get("object", {}).get("epistemic_status")
    return out


def objects_derived_from_record(db: Session, record_id: str) -> dict[str, list[str]]:
    rels = db.scalars(select(Relationship.id).where(Relationship.source_records.contains([record_id]))).all()
    ents = db.scalars(select(Entity.id).where(Entity.source_ids.contains([record_id]))).all()
    evs = db.scalars(select(Event.id).where(Event.source_record_id == record_id)).all()
    return {"entities": list(ents), "relationships": list(rels), "events": list(evs)}


def explain_entity_link(db: Session, a: str, b: str) -> list[dict[str, Any]]:
    """All direct relationships between two entities with their provenance."""
    r = Relationship
    rows = db.scalars(
        select(r).where(or_((r.source_id == a) & (r.target_id == b), (r.source_id == b) & (r.target_id == a)), r.deleted_at.is_(None))
    ).all()
    return [relationship_dict(x) for x in rows]
