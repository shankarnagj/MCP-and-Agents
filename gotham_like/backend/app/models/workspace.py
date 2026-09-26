"""Users, sessions, audit, investigations, assertions, rules, signals, alerts, privacy."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import SIGNAL_LABEL, AlertStatus, AssertionStatus, EpistemicStatus, utcnow

TS = DateTime(timezone=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


class AuditLog(Base):
    """Append-only (enforced by a database trigger) and hash-chained."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_action_ts", "action", "ts"), Index("ix_audit_object", "object_type", "object_id"))

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    object_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    previous_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    scope: Mapped[dict] = mapped_column(JSONB, default=dict)  # questions, time window, area
    collaborators: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)  # user ids with write access
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)


class InvestigationItem(Base):
    """Anything placed on an investigation / its evidence board."""

    __tablename__ = "investigation_items"
    __table_args__ = (Index("ix_inv_items_inv_kind", "investigation_id", "kind"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    # entity|relationship|event|note|document|source_record|citation|map|chart|timeline|saved_query|signal
    kind: Mapped[str] = mapped_column(String(32))
    ref_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    pinned: Mapped[bool] = mapped_column(Boolean, default=True)
    epistemic_status: Mapped[str] = mapped_column(String(32), default=EpistemicStatus.DERIVED.value)
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Assertion(Base):
    """Analyst assertion. Kept strictly separate from source-derived facts."""

    __tablename__ = "assertions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True, index=True)
    subject_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    statement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default=AssertionStatus.HYPOTHESIS.value)
    analyst_confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)  # LOW|MEDIUM|HIGH (subjective)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_refs: Mapped[list] = mapped_column(JSONB, default=list)
    epistemic_status: Mapped[str] = mapped_column(String(32), default=EpistemicStatus.ANALYST_ASSERTION.value)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)
    history: Mapped[list] = mapped_column(JSONB, default=list)


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    query_kind: Mapped[str] = mapped_column(String(32))  # search|pattern|geo|timeline|graph
    query: Mapped[dict] = mapped_column(JSONB)
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(64))  # threshold|new_relationship|unusual_count|geofence|event|source_change
    definition: Mapped[dict] = mapped_column(JSONB)
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)


class Signal(Base):
    """An ANALYTICAL SIGNAL – never a verdict."""

    __tablename__ = "signals"
    __table_args__ = (Index("ix_signals_entity_ids", "entity_ids", postgresql_using="gin"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(64), default=SIGNAL_LABEL)
    rule_id: Mapped[str] = mapped_column(String(64), index=True)
    rule_version: Mapped[int] = mapped_column(Integer)
    entity_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    score: Mapped[float] = mapped_column(Float)
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    explanation: Mapped[dict] = mapped_column(JSONB, default=dict)
    window_start: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    epistemic_status: Mapped[str] = mapped_column(String(32), default=EpistemicStatus.SYSTEM_INFERENCE.value)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_entities", "entities", postgresql_using="gin"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rule: Mapped[str] = mapped_column(String(64), index=True)
    alert_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    timestamp: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
    entities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    signal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=AlertStatus.OPEN.value, index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)


class DeletionRequest(Base):
    """Privacy deletion workflow (e.g. right-to-erasure where legally required)."""

    __tablename__ = "deletion_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(Text)
    legal_basis: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING|APPROVED|REJECTED|COMPLETED
    requested_by: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
