"""Ingestion pipeline: raw records → normalised entities / relationships / events, with lineage.

    source record (RAW)  ──mapping vX──▶  entity / relationship / event (DERIVED)
                          lineage_links rows record every hop.

Idempotent: re-ingesting an unchanged record is a no-op; a changed record is
re-mapped and reported as a `source_change`.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import islice
from typing import Any

from geoalchemy2 import WKTElement
from sqlalchemy import func, literal_column, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ingestion.base import Connector, RawRecord
from app.ingestion.mapping import NormalizedOutput, RecordMapping, apply_mapping
from app.models import (
    DataSource,
    Entity,
    EntityIdentifier,
    Event,
    IngestionRun,
    LineageLink,
    Relationship,
    SourceRecord,
    new_id,
    utcnow,
)
from app.ontology import Ontology

log = logging.getLogger("tessera.ingestion")


@dataclass
class IngestionResult:
    run_id: str
    source_id: str
    transformation_version: str
    records_seen: int = 0
    records_new: int = 0
    records_changed: int = 0
    records_unchanged: int = 0
    entities: Counter = field(default_factory=Counter)
    relationships: Counter = field(default_factory=Counter)
    events: Counter = field(default_factory=Counter)
    new_relationship_ids: list[str] = field(default_factory=list)
    changed_record_ids: list[str] = field(default_factory=list)
    new_event_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_id": self.source_id,
            "transformation_version": self.transformation_version,
            "records_seen": self.records_seen,
            "records_new": self.records_new,
            "records_changed": self.records_changed,
            "records_unchanged": self.records_unchanged,
            "entity_upserts": dict(self.entities),
            "relationship_upserts": dict(self.relationships),
            "event_upserts": dict(self.events),
            "new_relationships": len(self.new_relationship_ids),
            "errors": self.errors[:50],
            "error_count": len(self.errors),
        }


def source_record_pk(source_id: str, source_record_id: str) -> str:
    return "src_" + hashlib.sha1(f"{source_id}|{source_record_id}".encode(), usedforsecurity=False).hexdigest()[:20]


def ensure_source(db: Session, source_id: str, name: str, kind: str, description: str = "", classification: str = "UNCLASSIFIED", config: dict | None = None) -> DataSource:
    src = db.get(DataSource, source_id)
    if src is None:
        src = DataSource(id=source_id, name=name, kind=kind, description=description, classification=classification, config=config or {})
        db.add(src)
        db.flush()
    return src


def _batches(it: Iterable[RawRecord], size: int) -> Iterable[list[RawRecord]]:
    it = iter(it)
    while chunk := list(islice(it, size)):
        yield chunk


def _point(lat: float | None, lon: float | None) -> WKTElement | None:
    if lat is None or lon is None:
        return None
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def run_ingestion(
    db: Session,
    ontology: Ontology,
    source: DataSource,
    connector: Connector,
    mapping: RecordMapping,
    batch_size: int = 1000,
) -> IngestionResult:
    version = mapping.version()
    run = IngestionRun(id=new_id("run"), source_id=source.id, transformation_version=version, stats={"connector": connector.describe()})
    db.add(run)
    db.flush()
    result = IngestionResult(run_id=run.id, source_id=source.id, transformation_version=version)
    try:
        for batch in _batches(connector.iter_records(), batch_size):
            _process_batch(db, ontology, source, mapping, run, batch, result)
        run.status = "COMPLETED"
    except Exception as exc:
        run.status = "FAILED"
        result.errors.append(f"fatal: {exc!r}")
        raise
    finally:
        run.finished_at = utcnow()
        run.stats = {**run.stats, **result.summary()}
        db.flush()
    log.info("ingestion_complete", extra={"summary": result.summary()})
    return result


def _process_batch(
    db: Session, ontology: Ontology, source: DataSource, mapping: RecordMapping, run: IngestionRun, batch: list[RawRecord], result: IngestionResult
) -> None:
    now = utcnow()
    version = run.transformation_version
    result.records_seen += len(batch)
    # de-duplicate within batch (last wins)
    by_key = {r.source_record_id: r for r in batch}
    pks = {k: source_record_pk(source.id, k) for k in by_key}
    existing = dict(db.execute(select(SourceRecord.id, SourceRecord.content_hash).where(SourceRecord.id.in_(list(pks.values())))).all())

    to_process: list[tuple[str, RawRecord]] = []
    rows = []
    for key, rec in by_key.items():
        pk = pks[key]
        h = rec.content_hash
        if pk in existing:
            if existing[pk] == h:
                result.records_unchanged += 1
                continue
            result.records_changed += 1
            result.changed_record_ids.append(pk)
        else:
            result.records_new += 1
        to_process.append((pk, rec))
        rows.append(
            dict(
                id=pk, source_id=source.id, source_record_id=key, record_type=rec.record_type, payload=rec.payload,
                content_hash=h, ingestion_run_id=run.id, ingested_at=now, transformation_version=version,
            )
        )
    if not rows:
        return
    # executemany with a cached statement (insertmanyvalues) — far cheaper than one giant VALUES list
    stmt = pg_insert(SourceRecord.__table__)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "payload": stmt.excluded.payload,
            "content_hash": stmt.excluded.content_hash,
            "ingestion_run_id": stmt.excluded.ingestion_run_id,
            "ingested_at": stmt.excluded.ingested_at,
            "transformation_version": stmt.excluded.transformation_version,
        },
    )
    db.execute(stmt, rows)

    entities: dict[str, dict[str, Any]] = {}
    identifiers: set[tuple[str, str, str]] = set()
    relationships: dict[str, dict[str, Any]] = {}
    events: dict[str, dict[str, Any]] = {}
    lineage: list[dict[str, Any]] = []

    outputs: list[tuple[str, NormalizedOutput]] = []
    for pk, rec in to_process:
        out = apply_mapping(ontology, mapping, pk, rec.payload)
        result.errors.extend(f"{rec.source_record_id}: {e}" for e in out.errors)
        outputs.append((pk, out))

    # Redirect references to entities that entity resolution has merged away.
    all_ids = {e.id for _, o in outputs for e in o.entities}
    redirects = dict(db.execute(select(Entity.id, Entity.merged_into).where(Entity.id.in_(all_ids), Entity.merged_into.is_not(None))).all()) if all_ids else {}

    def canon(eid: str) -> str:
        return redirects.get(eid, eid)

    prov_base = {"source": source.id, "ingestion_run": run.id, "transformation": f"mapping:{mapping.record_type}", "transformation_version": version}
    for pk, out in outputs:
        for e in out.entities:
            eid = canon(e.id)
            cur = entities.get(eid)
            row = dict(
                id=eid, type=e.type, label=e.label, properties=e.properties, source_ids=[pk], confidence=e.confidence,
                epistemic_status="DERIVED", provenance={**prov_base, **({"stub": True} if e.stub else {})},
                classification=source.classification, geom=_point(e.lat, e.lon), lat=e.lat, lon=e.lon,
                observed_at=e.observed_at, search_text=e.search_text, created_at=now, updated_at=now,
            )
            if cur is None:
                entities[eid] = row
            else:
                # merge within batch: full records win over stubs, props union, sources union
                if cur["provenance"].get("stub") and not e.stub:
                    row["properties"] = {**cur["properties"], **row["properties"]}
                    row["source_ids"] = sorted(set(cur["source_ids"]) | {pk})
                    entities[eid] = row
                else:
                    cur["properties"] = {**row["properties"], **cur["properties"]} if e.stub else {**cur["properties"], **row["properties"]}
                    cur["source_ids"] = sorted(set(cur["source_ids"]) | {pk})
                    for k in ("lat", "lon", "geom", "observed_at"):
                        if cur[k] is None and row[k] is not None:
                            cur[k] = row[k]
            identifiers.update((eid, k, v) for k, v in e.identifiers)
            if not e.stub:
                lineage.append(dict(child_kind="entity", child_id=eid, parent_kind="source_record", parent_id=pk,
                                    transformation=f"mapping:{mapping.record_type}", transformation_version=version,
                                    details={"run": run.id}, created_at=now))
        for r in out.relationships:
            relationships[r.id] = dict(
                id=r.id, source_id=canon(r.source_id), target_id=canon(r.target_id), type=r.type, timestamp=r.timestamp,
                start_time=r.start_time, end_time=r.end_time, confidence=r.confidence, epistemic_status="DERIVED",
                properties=r.properties, source_records=[pk], provenance=prov_base, analyst_modifications=[],
                created_at=now, updated_at=now,
            )
            lineage.append(dict(child_kind="relationship", child_id=r.id, parent_kind="source_record", parent_id=pk,
                                transformation=f"mapping:{mapping.record_type}", transformation_version=version,
                                details={"run": run.id}, created_at=now))
        for ev in out.events:
            events[ev.id] = dict(
                id=ev.id, event_type=ev.event_type, timestamp=ev.timestamp, start_time=ev.start_time, end_time=ev.end_time,
                entity_ids=[canon(x) for x in ev.entity_ids], location_id=ev.location_id, geom=_point(ev.lat, ev.lon),
                lat=ev.lat, lon=ev.lon, source=source.id, source_record_id=pk, properties=ev.properties, confidence=1.0,
                epistemic_status="DERIVED", provenance=prov_base, created_at=now,
            )
            lineage.append(dict(child_kind="event", child_id=ev.id, parent_kind="source_record", parent_id=pk,
                                transformation=f"mapping:{mapping.record_type}", transformation_version=version,
                                details={"run": run.id}, created_at=now))

    if entities:
        stmt = pg_insert(Entity.__table__)
        ex = stmt.excluded
        t = Entity.__table__.c
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                # stubs never overwrite properties; full records win over existing values
                "properties": literal_column(
                    "CASE WHEN excluded.provenance ? 'stub' THEN excluded.properties || entities.properties "
                    "ELSE entities.properties || excluded.properties END"
                ),
                "label": literal_column("CASE WHEN excluded.provenance ? 'stub' THEN entities.label ELSE excluded.label END"),
                "source_ids": literal_column("ARRAY(SELECT DISTINCT unnest(entities.source_ids || excluded.source_ids))"),
                "provenance": literal_column("CASE WHEN excluded.provenance ? 'stub' THEN entities.provenance ELSE (entities.provenance - 'stub') || excluded.provenance END"),
                "search_text": literal_column("CASE WHEN excluded.provenance ? 'stub' AND entities.search_text <> '' THEN entities.search_text ELSE excluded.search_text END"),
                "geom": func.coalesce(ex.geom, t.geom),
                "lat": func.coalesce(ex.lat, t.lat),
                "lon": func.coalesce(ex.lon, t.lon),
                "observed_at": func.coalesce(ex.observed_at, t.observed_at),
                "updated_at": ex.updated_at,
            },
        )
        db.execute(stmt, list(entities.values()))
        for e in entities.values():
            result.entities[e["type"]] += 1
    if identifiers:
        db.execute(
            pg_insert(EntityIdentifier.__table__).on_conflict_do_nothing(constraint="uq_identifier"),
            [dict(entity_id=e, kind=k, value=v[:300]) for e, k, v in identifiers],
        )
    if relationships:
        stmt = pg_insert(Relationship.__table__)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "properties": stmt.excluded.properties,
                "timestamp": stmt.excluded.timestamp,
                "source_records": literal_column("ARRAY(SELECT DISTINCT unnest(relationships.source_records || excluded.source_records))"),
                "updated_at": stmt.excluded.updated_at,
            },
        ).returning(stmt.table.c.id, stmt.table.c.type, literal_column("(xmax = 0)").label("inserted"))
        for rid, rtype, inserted in db.execute(stmt, list(relationships.values())).all():
            result.relationships[rtype] += 1
            if inserted:
                result.new_relationship_ids.append(rid)
    if events:
        stmt = pg_insert(Event.__table__)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"properties": stmt.excluded.properties, "timestamp": stmt.excluded.timestamp, "entity_ids": stmt.excluded.entity_ids},
        ).returning(stmt.table.c.id, stmt.table.c.event_type, literal_column("(xmax = 0)").label("inserted"))
        for eid, etype, inserted in db.execute(stmt, list(events.values())).all():
            result.events[etype] += 1
            if inserted:
                result.new_event_ids.append(eid)
    if lineage:
        db.execute(pg_insert(LineageLink.__table__), lineage)
    db.flush()


def refresh_statistics(db: Session) -> None:
    db.execute(text("ANALYZE entities; ANALYZE relationships; ANALYZE events;"))
