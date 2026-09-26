"""Serialisation of ORM rows into API payloads, applying field-level masking."""

from __future__ import annotations

from typing import Any

from app.models import Entity, Event, Relationship
from app.ontology import Ontology
from app.privacy.masking import mask_label, mask_properties


def entity_dict(e: Entity, ontology: Ontology, role: str, full: bool = True) -> dict[str, Any]:
    props, masked = mask_properties(ontology, e.type, e.properties or {}, role)
    d: dict[str, Any] = {
        "id": e.id,
        "type": e.type,
        "label": mask_label(ontology, e.type, e.label, role),
        "confidence": e.confidence,
        "epistemic_status": e.epistemic_status,
        "lat": e.lat,
        "lon": e.lon,
        "observed_at": e.observed_at.isoformat() if e.observed_at else None,
    }
    if full:
        d.update(
            properties=props,
            masked_fields=masked,
            source_ids=e.source_ids,
            provenance=e.provenance,
            classification=e.classification,
            created_at=e.created_at.isoformat() if e.created_at else None,
            updated_at=e.updated_at.isoformat() if e.updated_at else None,
            merged_into=e.merged_into,
        )
    return d


def relationship_dict(r: Relationship) -> dict[str, Any]:
    return {
        "id": r.id,
        "source": r.source_id,
        "target": r.target_id,
        "relationship_type": r.type,
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "start_time": r.start_time.isoformat() if r.start_time else None,
        "end_time": r.end_time.isoformat() if r.end_time else None,
        "confidence": r.confidence,
        "epistemic_status": r.epistemic_status,
        "properties": r.properties,
        "source_records": r.source_records,
        "provenance": r.provenance,
        "analyst_modifications": r.analyst_modifications,
    }


def edge_row_dict(row: Any) -> dict[str, Any]:
    """Same shape as relationship_dict for Core rows."""
    m = row._mapping if hasattr(row, "_mapping") else row
    return {
        "id": m["id"],
        "source": m["source_id"],
        "target": m["target_id"],
        "relationship_type": m["type"],
        "timestamp": m["timestamp"].isoformat() if m["timestamp"] else None,
        "confidence": m["confidence"],
        "epistemic_status": m["epistemic_status"],
        "properties": m["properties"],
        "source_records": m["source_records"],
        "provenance": m["provenance"],
    }


def event_dict(ev: Event) -> dict[str, Any]:
    return {
        "id": ev.id,
        "event_type": ev.event_type,
        "timestamp": ev.timestamp.isoformat(),
        "start_time": ev.start_time.isoformat() if ev.start_time else None,
        "end_time": ev.end_time.isoformat() if ev.end_time else None,
        "entity_ids": ev.entity_ids,
        "location_id": ev.location_id,
        "lat": ev.lat,
        "lon": ev.lon,
        "source": ev.source,
        "source_record_id": ev.source_record_id,
        "properties": ev.properties,
        "confidence": ev.confidence,
        "epistemic_status": ev.epistemic_status,
    }
