"""Exports (CSV, JSON, GraphML, GeoJSON). Every export embeds provenance metadata."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph.store import edges_among
from app.models import SYNTHETIC_LABEL, Entity, Event, SourceRecord, utcnow
from app.ontology import Ontology
from app.services.serialize import edge_row_dict, entity_dict, event_dict

FORMATS = {"csv", "json", "graphml", "geojson"}
MAX_EXPORT_ENTITIES = 20000


def collect(db: Session, ontology: Ontology, role: str, entity_ids: list[str], include_events: bool = True) -> dict[str, Any]:
    if len(entity_ids) > MAX_EXPORT_ENTITIES:
        raise ValueError(f"export limited to {MAX_EXPORT_ENTITIES} entities")
    ents = db.scalars(select(Entity).where(Entity.id.in_(entity_ids))).all() if entity_ids else []
    rels = [edge_row_dict(r) for r in edges_among(db, entity_ids, limit=100000)]
    evs = [event_dict(e) for e in db.scalars(select(Event).where(Event.entity_ids.overlap(entity_ids)).limit(20000))] if include_events and entity_ids else []
    rec_ids = {r for e in ents for r in e.source_ids} | {r for x in rels for r in (x["source_records"] or [])}
    srcs = db.execute(select(SourceRecord.source_id, SourceRecord.transformation_version).where(SourceRecord.id.in_(list(rec_ids)[:50000]))).all() if rec_ids else []
    sources = sorted({s for s, _ in srcs})
    versions = sorted({v for _, v in srcs})
    ent_dicts = [entity_dict(e, ontology, role) for e in ents]
    meta = {
        "exported_at": utcnow().isoformat(),
        "platform": "Tessera Investigative Workbench",
        "data_label": SYNTHETIC_LABEL if any(s.startswith("synthetic") for s in sources) else "UNCLASSIFIED",
        "role_applied": role,
        "masked_fields": sum(len(d["masked_fields"]) for d in ent_dicts),
        "sources": sources,
        "transformation_versions": versions,
        "counts": {"entities": len(ents), "relationships": len(rels), "events": len(evs)},
        "provenance_note": "Each row carries epistemic_status, confidence and source record ids; trace them with GET /api/provenance/{id}.",
    }
    return {"metadata": meta, "entities": ent_dicts, "relationships": rels, "events": evs}


def to_json(data: dict[str, Any]) -> str:
    return json.dumps(data, default=str, indent=1)


def to_csv(data: dict[str, Any], what: str = "entities") -> str:
    buf = io.StringIO()
    for k, v in data["metadata"].items():
        buf.write(f"# {k}: {json.dumps(v, default=str)}\n")
    w = csv.writer(buf)
    if what == "entities":
        props = sorted({p for e in data["entities"] for p in e["properties"] if not p.startswith("_")})
        w.writerow(["id", "type", "label", "confidence", "epistemic_status", "source_ids", "transformation", "transformation_version", *props])
        for e in data["entities"]:
            prov = e.get("provenance") or {}
            w.writerow([e["id"], e["type"], e["label"], e["confidence"], e["epistemic_status"], ";".join(e["source_ids"]),
                        prov.get("transformation", ""), prov.get("transformation_version", ""), *[e["properties"].get(p, "") for p in props]])
    elif what == "relationships":
        w.writerow(["id", "source", "target", "relationship_type", "timestamp", "confidence", "epistemic_status", "source_records",
                    "provenance_source", "transformation_version"])
        for r in data["relationships"]:
            prov = r.get("provenance") or {}
            w.writerow([r["id"], r["source"], r["target"], r["relationship_type"], r["timestamp"] or "", r["confidence"], r["epistemic_status"],
                        ";".join(r["source_records"] or []), prov.get("source", ""), prov.get("transformation_version", "")])
    elif what == "events":
        w.writerow(["id", "event_type", "timestamp", "entity_ids", "lat", "lon", "source", "source_record_id", "epistemic_status"])
        for e in data["events"]:
            w.writerow([e["id"], e["event_type"], e["timestamp"], ";".join(e["entity_ids"]), e["lat"] or "", e["lon"] or "", e["source"],
                        e["source_record_id"] or "", e["epistemic_status"]])
    else:
        raise ValueError("what must be entities|relationships|events")
    return buf.getvalue()


def to_graphml(data: dict[str, Any]) -> str:
    g = nx.MultiDiGraph()
    for k, v in data["metadata"].items():
        g.graph[k] = json.dumps(v, default=str) if not isinstance(v, str) else v
    for e in data["entities"]:
        g.add_node(e["id"], type=e["type"], label=e["label"], confidence=float(e["confidence"]), epistemic_status=e["epistemic_status"],
                   source_ids=";".join(e["source_ids"]), lat=e["lat"] if e["lat"] is not None else "", lon=e["lon"] if e["lon"] is not None else "",
                   properties=json.dumps(e["properties"], default=str))
    for r in data["relationships"]:
        g.add_edge(r["source"], r["target"], key=r["id"], id=r["id"], relationship_type=r["relationship_type"], timestamp=r["timestamp"] or "",
                   confidence=float(r["confidence"]), epistemic_status=r["epistemic_status"], source_records=";".join(r["source_records"] or []),
                   provenance=json.dumps(r["provenance"], default=str))
    buf = io.BytesIO()
    nx.write_graphml(g, buf)
    return buf.getvalue().decode()


def to_geojson(data: dict[str, Any]) -> str:
    feats = []
    for e in data["entities"]:
        if e["lat"] is not None:
            feats.append({"type": "Feature", "id": e["id"], "geometry": {"type": "Point", "coordinates": [e["lon"], e["lat"]]},
                          "properties": {"kind": "entity", "type": e["type"], "label": e["label"], "confidence": e["confidence"],
                                         "epistemic_status": e["epistemic_status"], "source_ids": e["source_ids"]}})
    for ev in data["events"]:
        if ev["lat"] is not None:
            feats.append({"type": "Feature", "id": ev["id"], "geometry": {"type": "Point", "coordinates": [ev["lon"], ev["lat"]]},
                          "properties": {"kind": "event", "event_type": ev["event_type"], "timestamp": ev["timestamp"], "source": ev["source"],
                                         "source_record_id": ev["source_record_id"], "epistemic_status": ev["epistemic_status"]}})
    return json.dumps({"type": "FeatureCollection", "metadata": data["metadata"], "features": feats}, default=str)
