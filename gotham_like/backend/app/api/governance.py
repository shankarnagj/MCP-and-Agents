"""Provenance, entity resolution review, rules/signals/alerts, ontology, sources, audit, privacy."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.common import ip_of, onto
from app.audit.service import record, verify_chain
from app.auth.deps import Principal, require
from app.auth.rbac import (
    P_ALERTS,
    P_AUDIT,
    P_DELETE_APPROVE,
    P_DELETE_REQUEST,
    P_ER_REVIEW,
    P_INGEST,
    P_ONTOLOGY,
    P_PROVENANCE,
    P_READ,
    P_RULES_RUN,
    P_RULES_WRITE,
)
from app.auth.security import encrypt_secret
from app.config import get_settings
from app.db import get_db
from app.entity_resolution.resolver import compare
from app.entity_resolution.service import merge_entities, unmerge
from app.models import (
    Alert,
    AlertStatus,
    AuditLog,
    DataSource,
    DeletionRequest,
    Entity,
    IngestionRun,
    ResolutionCandidate,
    Rule,
    Signal,
    new_id,
    utcnow,
)
from app.ontology import Ontology, OntologyError, set_ontology
from app.privacy.retention import execute_deletion, retention_report
from app.provenance.service import lineage_graph, provenance
from app.rules import engine
from app.services.cache import get_cache
from app.services.realtime import hub
from app.services.serialize import entity_dict

router = APIRouter(prefix="/api", tags=["governance"])


# ---------------------------------------------------------------- provenance
@router.get("/provenance/{obj_id}")
def get_provenance(obj_id: str, request: Request, user: Principal = Depends(require(P_PROVENANCE)), db: Session = Depends(get_db),
                   ontology: Ontology = Depends(onto)) -> dict:
    try:
        out = provenance(db, ontology, obj_id, user.role)
    except KeyError as exc:
        raise HTTPException(404, "object not found") from exc
    record(db, "provenance_view", user, out["kind"], obj_id, ip=ip_of(request))
    db.commit()
    return out


@router.get("/provenance/{obj_id}/lineage")
def get_lineage(obj_id: str, kind: str = Query(..., pattern="^(entity|relationship|event|source_record|signal)$"),
                direction: Literal["up", "down"] = "up", user: Principal = Depends(require(P_PROVENANCE)), db: Session = Depends(get_db)) -> dict:
    return lineage_graph(db, kind, obj_id, direction)


# ---------------------------------------------------------------- entity resolution
@router.get("/resolution/candidates")
def list_candidates(decision: Literal["MATCH", "POSSIBLE_MATCH"] | None = None, review_status: str | None = None, limit: int = Query(100, le=500),
                    offset: int = 0, user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db), ontology: Ontology = Depends(onto)) -> dict:
    q = select(ResolutionCandidate)
    if decision:
        q = q.where(ResolutionCandidate.decision == decision)
    if review_status:
        q = q.where(ResolutionCandidate.review_status == review_status)
    rows = db.scalars(q.order_by(ResolutionCandidate.score.desc()).limit(limit).offset(offset)).all()
    ids = {x for c in rows for x in (c.entity_a, c.entity_b)}
    ents = {e.id: entity_dict(e, ontology, user.role, full=False) for e in db.scalars(select(Entity).where(Entity.id.in_(ids)))}
    return {"items": [{"id": c.id, "entity_type": c.entity_type, "a": ents.get(c.entity_a), "b": ents.get(c.entity_b), "decision": c.decision,
                       "score": c.score, "evidence": c.evidence, "review_status": c.review_status, "merged": c.merged,
                       "resolver_version": c.resolver_version} for c in rows]}


class CompareBody(BaseModel):
    entity_a: str
    entity_b: str


@router.post("/resolution/compare")
def compare_entities(body: CompareBody, user: Principal = Depends(require(P_ER_REVIEW)), db: Session = Depends(get_db),
                     ontology: Ontology = Depends(onto)) -> dict:
    a, b = db.get(Entity, body.entity_a), db.get(Entity, body.entity_b)
    if a is None or b is None:
        raise HTTPException(404, "entity not found")
    if a.type != b.type:
        raise HTTPException(422, "entities must have the same type")
    res = compare(ontology, a.type, a.properties, b.properties)
    return {**res.to_dict(), "explanation": res.explain()}


class ReviewBody(BaseModel):
    decision: Literal["CONFIRM", "REJECT"]
    note: str = Field(default="", max_length=2000)


@router.post("/resolution/candidates/{cand_id}/review")
def review_candidate(cand_id: str, body: ReviewBody, request: Request, user: Principal = Depends(require(P_ER_REVIEW)), db: Session = Depends(get_db),
                     ontology: Ontology = Depends(onto)) -> dict:
    c = db.get(ResolutionCandidate, cand_id)
    if c is None:
        raise HTTPException(404, "candidate not found")
    before = {"review_status": c.review_status, "merged": c.merged}
    result: dict[str, Any] = {}
    if body.decision == "CONFIRM" and not c.merged:
        a, b = db.get(Entity, c.entity_a), db.get(Entity, c.entity_b)
        if a.merged_into or b.merged_into:
            raise HTTPException(409, "one of the entities is already merged")
        canon, dup = (a, b) if len(a.source_ids) >= len(b.source_ids) else (b, a)
        match = compare(ontology, a.type, a.properties, b.properties)
        result = merge_entities(db, canon, dup, match, actor=user.username)
    elif body.decision == "REJECT" and c.merged:
        dup = c.entity_a if db.get(Entity, c.entity_a).merged_into else c.entity_b
        result = unmerge(db, dup, user.username)
    c.review_status = "CONFIRMED" if body.decision == "CONFIRM" else "REJECTED"
    c.reviewed_by = user.username
    record(db, "er_review", user, "resolution_candidate", c.id, previous_value=before,
           new_value={"review_status": c.review_status, "merged": c.merged, "note": body.note, **result}, ip=ip_of(request))
    db.commit()
    get_cache().bump()
    return {"id": c.id, "review_status": c.review_status, "merged": c.merged, **result}


# ---------------------------------------------------------------- rules, signals, alerts
def _rule_dict(r: Rule) -> dict:
    return {"id": r.id, "name": r.name, "description": r.description, "kind": r.kind, "definition": r.definition, "severity": r.severity,
            "enabled": r.enabled, "version": r.version, "created_by": r.created_by, "updated_at": r.updated_at.isoformat()}


def _alert_dict(a: Alert) -> dict:
    return {"id": a.id, "rule": a.rule, "alert_type": a.alert_type, "severity": a.severity, "timestamp": a.timestamp.isoformat(),
            "entities": a.entities, "evidence": a.evidence, "summary": a.summary, "signal_id": a.signal_id, "status": a.status,
            "assigned_to": a.assigned_to, "updated_at": a.updated_at.isoformat()}


def _signal_dict(s: Signal) -> dict:
    return {"id": s.id, "label": s.label, "rule_id": s.rule_id, "rule_version": s.rule_version, "entity_ids": s.entity_ids, "score": s.score,
            "evidence": s.evidence, "explanation": s.explanation, "window_start": s.window_start.isoformat() if s.window_start else None,
            "window_end": s.window_end.isoformat() if s.window_end else None, "epistemic_status": s.epistemic_status,
            "created_at": s.created_at.isoformat()}


@router.get("/rules")
def list_rules(user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db)) -> list[dict]:
    return [_rule_dict(r) for r in db.scalars(select(Rule).order_by(Rule.id))]


class RuleBody(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    name: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=2000)
    kind: str
    definition: dict[str, Any]
    severity: Literal["INFO", "LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    enabled: bool = True


@router.put("/rules/{rule_id}")
def upsert_rule(rule_id: str, body: RuleBody, request: Request, user: Principal = Depends(require(P_RULES_WRITE)), db: Session = Depends(get_db)) -> dict:
    if body.id != rule_id:
        raise HTTPException(422, "id mismatch")
    try:
        engine.validate_rule_definition(body.kind, body.name, body.description, body.definition)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    r = db.get(Rule, rule_id)
    before = _rule_dict(r) if r else None
    if r is None:
        r = Rule(id=rule_id, created_by=user.username, version=1, name=body.name, kind=body.kind, definition=body.definition)
        db.add(r)
    else:
        r.version += 1
    r.name, r.description, r.kind, r.definition, r.severity, r.enabled = body.name, body.description, body.kind, body.definition, body.severity, body.enabled
    db.flush()
    record(db, "rule_change", user, "rule", rule_id, previous_value=before, new_value=_rule_dict(r), ip=ip_of(request))
    db.commit()
    return _rule_dict(r)


@router.post("/rules/{rule_id}/evaluate")
def evaluate_rule(rule_id: str, request: Request, user: Principal = Depends(require(P_RULES_RUN)), db: Session = Depends(get_db)) -> dict:
    r = db.get(Rule, rule_id)
    if r is None:
        raise HTTPException(404, "rule not found")
    hub.publish("progress", "rule.started", {"rule": rule_id, "by": user.username})
    res = engine.evaluate(db, r)
    for a in res["new_alerts"]:
        hub.publish("alerts", "alert.created", _alert_dict(a))
    record(db, "query", user, "rule", rule_id, details={"op": "evaluate", "new_signals": len(res["new_signals"])}, ip=ip_of(request))
    db.commit()
    hub.publish("progress", "rule.finished", {"rule": rule_id, "new_signals": len(res["new_signals"])})
    return {"rule": rule_id, "candidates": res["drafts"], "new_signals": res["new_signals"], "new_alerts": [a.id for a in res["new_alerts"]]}


@router.get("/signals")
def list_signals(rule_id: str | None = None, entity_id: str | None = None, limit: int = Query(100, le=500), offset: int = 0,
                 user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db)) -> dict:
    q = select(Signal)
    if rule_id:
        q = q.where(Signal.rule_id == rule_id)
    if entity_id:
        q = q.where(Signal.entity_ids.contains([entity_id]))
    rows = db.scalars(q.order_by(Signal.created_at.desc(), Signal.id).limit(limit).offset(offset)).all()
    return {"label": "ANALYTICAL SIGNALS — not findings", "items": [_signal_dict(s) for s in rows]}


@router.get("/signals/{signal_id}")
def get_signal(signal_id: str, user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db)) -> dict:
    s = db.get(Signal, signal_id)
    if s is None:
        raise HTTPException(404, "signal not found")
    return _signal_dict(s)


@router.get("/alerts")
def list_alerts(status: str | None = None, rule: str | None = None, limit: int = Query(100, le=500), offset: int = 0,
                user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db)) -> dict:
    q = select(Alert)
    if status:
        q = q.where(Alert.status == status)
    if rule:
        q = q.where(Alert.rule == rule)
    rows = db.scalars(q.order_by(Alert.timestamp.desc(), Alert.id).limit(limit).offset(offset)).all()
    counts = dict(db.execute(select(Alert.status, func.count()).group_by(Alert.status)).all())
    return {"items": [_alert_dict(a) for a in rows], "counts": counts}


class AlertPatch(BaseModel):
    status: AlertStatus
    note: str = Field(default="", max_length=2000)
    assigned_to: str | None = None


@router.patch("/alerts/{alert_id}")
def patch_alert(alert_id: str, body: AlertPatch, request: Request, user: Principal = Depends(require(P_ALERTS)), db: Session = Depends(get_db)) -> dict:
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "alert not found")
    before = _alert_dict(a)
    a.status = body.status.value
    if body.assigned_to is not None:
        a.assigned_to = body.assigned_to
    record(db, "alert_update", user, "alert", a.id, previous_value={"status": before["status"]}, new_value={"status": a.status, "note": body.note},
           ip=ip_of(request))
    db.commit()
    hub.publish("alerts", "alert.updated", _alert_dict(a))
    return _alert_dict(a)


# ---------------------------------------------------------------- ontology
@router.get("/ontology")
def get_ontology_api(ontology: Ontology = Depends(onto), user: Principal = Depends(require(P_READ))) -> dict:
    return ontology.model_dump()


@router.put("/ontology")
def put_ontology(body: dict[str, Any], request: Request, user: Principal = Depends(require(P_ONTOLOGY)), db: Session = Depends(get_db),
                 ontology: Ontology = Depends(onto)) -> dict:
    try:
        new = Ontology.model_validate(body)
    except (ValueError, OntologyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    removed = set(ontology.entity_types) - set(new.entity_types)
    in_use = [t for t in removed if db.scalar(select(func.count()).where(Entity.type == t, Entity.deleted_at.is_(None)))]
    if in_use:
        raise HTTPException(409, f"cannot remove entity types still in use: {in_use}")
    set_ontology(new)
    get_settings().ontology_path.write_text(json.dumps(new.model_dump(), indent=2))
    record(db, "ontology_change", user, "ontology", new.version, previous_value={"version": ontology.version}, new_value={"version": new.version},
           ip=ip_of(request))
    db.commit()
    return {"version": new.version, "entity_types": len(new.entity_types), "relationship_types": len(new.relationship_types)}


# ---------------------------------------------------------------- sources / ingestion
class SourceBody(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    name: str = Field(max_length=200)
    kind: Literal["csv", "json", "jsonl", "parquet", "postgres", "api"]
    description: str = ""
    classification: str = "UNCLASSIFIED"
    config: dict[str, Any] = Field(default_factory=dict)
    secret: str | None = Field(default=None, description="DSN / API token. Stored encrypted; never returned.")
    retention_days: int | None = Field(default=None, ge=1)


def _source_dict(s: DataSource) -> dict:
    return {"id": s.id, "name": s.name, "kind": s.kind, "description": s.description, "classification": s.classification, "config": s.config,
            "has_secret": bool(s.secret_encrypted), "retention_days": s.retention_days, "created_at": s.created_at.isoformat()}


@router.get("/sources")
def list_sources(user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for s in db.scalars(select(DataSource).order_by(DataSource.id)):
        d = _source_dict(s)
        last = db.scalars(select(IngestionRun).where(IngestionRun.source_id == s.id).order_by(IngestionRun.started_at.desc()).limit(1)).first()
        d["last_run"] = {"id": last.id, "status": last.status, "started_at": last.started_at.isoformat(), "transformation_version":
                         last.transformation_version, "records_seen": last.stats.get("records_seen")} if last else None
        out.append(d)
    return out


@router.post("/sources", status_code=201)
def create_source(body: SourceBody, request: Request, user: Principal = Depends(require(P_INGEST)), db: Session = Depends(get_db)) -> dict:
    if db.get(DataSource, body.id):
        raise HTTPException(409, "source exists")
    for k in body.config:
        if any(w in k.lower() for w in ("password", "secret", "token", "dsn", "key")):
            raise HTTPException(422, f"config key '{k}' looks secret: pass it via 'secret' so it is encrypted")
    s = DataSource(id=body.id, name=body.name, kind=body.kind, description=body.description, classification=body.classification,
                   config=body.config, secret_encrypted=encrypt_secret(body.secret) if body.secret else None, retention_days=body.retention_days)
    db.add(s)
    db.flush()
    record(db, "ingestion", user, "data_source", s.id, new_value=_source_dict(s), ip=ip_of(request))
    db.commit()
    return _source_dict(s)


@router.get("/ingestion-runs")
def list_runs(source_id: str | None = None, user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db)) -> list[dict]:
    q = select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(200)
    if source_id:
        q = q.where(IngestionRun.source_id == source_id)
    return [{"id": r.id, "source_id": r.source_id, "status": r.status, "started_at": r.started_at.isoformat(),
             "finished_at": r.finished_at.isoformat() if r.finished_at else None, "transformation_version": r.transformation_version,
             "stats": r.stats} for r in db.scalars(q)]


# ---------------------------------------------------------------- audit
@router.get("/audit")
def get_audit(action: str | None = None, username: str | None = None, object_id: str | None = None, limit: int = Query(200, le=1000),
              before_id: int | None = None, user: Principal = Depends(require(P_AUDIT)), db: Session = Depends(get_db)) -> dict:
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    if username:
        q = q.where(AuditLog.username == username)
    if object_id:
        q = q.where(AuditLog.object_id == object_id)
    if before_id:
        q = q.where(AuditLog.id < before_id)
    rows = db.scalars(q.order_by(AuditLog.id.desc()).limit(limit)).all()
    return {"items": [{"id": a.id, "ts": a.ts.isoformat(), "user": a.username, "user_id": a.user_id, "action": a.action, "object_type": a.object_type,
                       "object": a.object_id, "previous_value": a.previous_value, "new_value": a.new_value, "details": a.details,
                       "request_id": a.request_id, "ip": a.ip, "hash": a.hash} for a in rows]}


@router.get("/audit/verify")
def audit_verify(user: Principal = Depends(require(P_AUDIT)), db: Session = Depends(get_db)) -> dict:
    return verify_chain(db)


# ---------------------------------------------------------------- privacy
class DeletionBody(BaseModel):
    entity_id: str
    reason: str = Field(min_length=10, max_length=5000)
    legal_basis: str = Field(min_length=3, max_length=200)


def _del_dict(d: DeletionRequest) -> dict:
    return {"id": d.id, "entity_id": d.entity_id, "reason": d.reason, "legal_basis": d.legal_basis, "status": d.status,
            "requested_by": d.requested_by, "approved_by": d.approved_by, "created_at": d.created_at.isoformat(),
            "completed_at": d.completed_at.isoformat() if d.completed_at else None, "result": d.result}


@router.post("/privacy/deletion-requests", status_code=201)
def request_deletion(body: DeletionBody, request: Request, user: Principal = Depends(require(P_DELETE_REQUEST)), db: Session = Depends(get_db)) -> dict:
    if db.get(Entity, body.entity_id) is None:
        raise HTTPException(404, "entity not found")
    d = DeletionRequest(id=new_id("del"), entity_id=body.entity_id, reason=body.reason, legal_basis=body.legal_basis, requested_by=user.id)
    db.add(d)
    db.flush()
    record(db, "deletion_request", user, "entity", body.entity_id, new_value=_del_dict(d), ip=ip_of(request))
    db.commit()
    return _del_dict(d)


@router.get("/privacy/deletion-requests")
def list_deletions(user: Principal = Depends(require(P_DELETE_REQUEST)), db: Session = Depends(get_db)) -> list[dict]:
    return [_del_dict(d) for d in db.scalars(select(DeletionRequest).order_by(DeletionRequest.created_at.desc()).limit(500))]


@router.post("/privacy/deletion-requests/{req_id}/approve")
def approve_deletion(req_id: str, request: Request, user: Principal = Depends(require(P_DELETE_APPROVE)), db: Session = Depends(get_db)) -> dict:
    d = db.get(DeletionRequest, req_id)
    if d is None:
        raise HTTPException(404, "request not found")
    if d.status != "PENDING":
        raise HTTPException(409, f"request is {d.status}")
    if d.requested_by == user.id:
        raise HTTPException(403, "four-eyes principle: the requester cannot approve their own deletion request")
    d.approved_by = user.id
    d.status = "APPROVED"
    d.result = execute_deletion(db, d.entity_id)
    d.status = "COMPLETED"
    d.completed_at = utcnow()
    record(db, "deletion_approve", user, "entity", d.entity_id, new_value=_del_dict(d), ip=ip_of(request))
    db.commit()
    get_cache().bump()
    return _del_dict(d)


@router.get("/privacy/retention")
def get_retention(user: Principal = Depends(require(P_AUDIT)), db: Session = Depends(get_db)) -> dict:
    return retention_report(db)


# ---------------------------------------------------------------- stats
@router.get("/stats")
def stats(user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db)) -> dict:
    from app.models import Event, Relationship

    by_type = dict(db.execute(select(Entity.type, func.count()).where(Entity.merged_into.is_(None), Entity.deleted_at.is_(None)).group_by(Entity.type)).all())
    rel_types = dict(db.execute(select(Relationship.type, func.count()).where(Relationship.deleted_at.is_(None)).group_by(Relationship.type)).all())
    ev_types = dict(db.execute(select(Event.event_type, func.count()).group_by(Event.event_type)).all())
    span = db.execute(select(func.min(Event.timestamp), func.max(Event.timestamp))).one()
    return {"entities": by_type, "relationships": rel_types, "events": ev_types,
            "event_span": [span[0].isoformat() if span[0] else None, span[1].isoformat() if span[1] else None],
            "open_alerts": db.scalar(select(func.count()).where(Alert.status == "OPEN")),
            "signals": db.scalar(select(func.count()).select_from(Signal)),
            "pending_er_reviews": db.scalar(select(func.count()).where(ResolutionCandidate.decision == "POSSIBLE_MATCH",
                                                                       ResolutionCandidate.review_status == "UNREVIEWED")),
            "data_label": "SYNTHETIC / DEMONSTRATION DATA" if db.scalar(select(func.count()).where(or_(DataSource.id.like("synthetic%")))) else None}

