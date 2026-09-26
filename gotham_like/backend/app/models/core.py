"""Core data model: sources, raw records, entities, relationships, events, lineage."""

from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import EpistemicStatus, utcnow

TS = DateTime(timezone=True)


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))  # csv|json|jsonl|parquet|postgres|api
    description: Mapped[str] = mapped_column(Text, default="")
    classification: Mapped[str] = mapped_column(String(64), default="UNCLASSIFIED")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)  # non-secret settings only
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)  # Fernet token
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    transformation_version: Mapped[str] = mapped_column(String(32))
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)


class SourceRecord(Base):
    """An unmodified record as received from a source (epistemic status RAW)."""

    __tablename__ = "source_records"
    __table_args__ = (UniqueConstraint("source_id", "source_record_id", name="uq_source_record"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"), index=True)
    source_record_id: Mapped[str] = mapped_column(String(200))
    record_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    ingestion_run_id: Mapped[str] = mapped_column(String(64), index=True)
    ingested_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    transformation_version: Mapped[str] = mapped_column(String(32))
    deleted_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (
        Index("ix_entities_type_label", "type", "label"),
        Index("ix_entities_search_trgm", "search_text", postgresql_using="gin", postgresql_ops={"search_text": "gin_trgm_ops"}),
        Index("ix_entities_source_ids", "source_ids", postgresql_using="gin"),
        Index("ix_entities_properties", "properties", postgresql_using="gin", postgresql_ops={"properties": "jsonb_path_ops"}),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(300), default="")
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)  # source_record ids
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    epistemic_status: Mapped[str] = mapped_column(String(32), default=EpistemicStatus.DERIVED.value)
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
    classification: Mapped[str] = mapped_column(String(64), default="UNCLASSIFIED")
    geom = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=True), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(TS, nullable=True, index=True)
    search_text: Mapped[str] = mapped_column(Text, default="")
    merged_into: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class EntityIdentifier(Base):
    """Normalised strong identifiers (email, phone, account no, IP ...) for exact lookup & ER blocking."""

    __tablename__ = "entity_identifiers"
    __table_args__ = (
        Index("ix_identifiers_kind_value", "kind", "value"),
        UniqueConstraint("entity_id", "kind", "value", name="uq_identifier"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(300))


class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        Index("ix_rel_source_type", "source_id", "type"),
        Index("ix_rel_target_type", "target_id", "type"),
        Index("ix_rel_source_records", "source_records", postgresql_using="gin"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    target_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime | None] = mapped_column(TS, nullable=True, index=True)
    start_time: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    epistemic_status: Mapped[str] = mapped_column(String(32), default=EpistemicStatus.DERIVED.value)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_records: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
    analyst_modifications: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_entity_ids", "entity_ids", postgresql_using="gin"),
        Index("ix_events_type_ts", "event_type", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(TS, index=True)
    start_time: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    entity_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    location_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    geom = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=True), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(64), index=True)  # data_sources.id
    source_record_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    epistemic_status: Mapped[str] = mapped_column(String(32), default=EpistemicStatus.DERIVED.value)
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class LineageLink(Base):
    """child was produced from parent by `transformation` (version-pinned)."""

    __tablename__ = "lineage_links"
    __table_args__ = (
        Index("ix_lineage_child", "child_kind", "child_id"),
        Index("ix_lineage_parent", "parent_kind", "parent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_kind: Mapped[str] = mapped_column(String(32))  # entity|relationship|event|signal
    child_id: Mapped[str] = mapped_column(String(64))
    parent_kind: Mapped[str] = mapped_column(String(32))  # source_record|entity|relationship|event
    parent_id: Mapped[str] = mapped_column(String(64))
    transformation: Mapped[str] = mapped_column(String(128))
    transformation_version: Mapped[str] = mapped_column(String(32))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class ResolutionCandidate(Base):
    """Entity-resolution outcome between two entities, with its evidence."""

    __tablename__ = "resolution_candidates"
    __table_args__ = (UniqueConstraint("entity_a", "entity_b", name="uq_resolution_pair"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_a: Mapped[str] = mapped_column(String(64), index=True)
    entity_b: Mapped[str] = mapped_column(String(64), index=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[float] = mapped_column(Float)
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    review_status: Mapped[str] = mapped_column(String(32), default="UNREVIEWED")  # UNREVIEWED|CONFIRMED|REJECTED
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolver_version: Mapped[str] = mapped_column(String(32))
    merged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Geofence(Base):
    __tablename__ = "geofences"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    geom = mapped_column(Geography(geometry_type="POLYGON", srid=4326, spatial_index=True))
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
