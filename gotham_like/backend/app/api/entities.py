"""Entities, relationships, search."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.common import ip_of, onto, ts_param
from app.audit.service import record
from app.auth.deps import Principal, require
from app.auth.rbac import P_PII, P_READ, P_SEARCH, P_VERIFY
from app.db import get_db
from app.graph.store import degree, resolve_canonical
from app.models import Alert, Assertion, Entity, EpistemicStatus, Relationship, ResolutionCandidate, Signal, utcnow
from app.ontology import Ontology
from app.search.parser import QueryParseError
from app.search.service import SearchRequest, search
from app.services.cache import get_cache
from app.services.serialize import entity_dict, relationship_dict

router = APIRouter(prefix="/api", tags=["entities"])


@router.get("/entities")
def list_entities(
    type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort: Literal["label", "updated_at", "confidence"] = "label",
    user: Principal = Depends(require(P_READ)),
    db: Session = Depends(get_db),
    ontology: Ontology = Depends(onto),
) -> dict:
    e = Entity
    conds = [e.merged_into.is_(None), e.deleted_at.is_(None)]
    if type:
        if type not in ontology.entity_types:
            raise HTTPException(422, f"unknown entity type {type}")
        conds.append(e.type == type)
    order = {"label": e.label, "updated_at": e.updated_at.desc(), "confidence": e.confidence.desc()}[sort]
    rows = db.scalars(select(e).where(*conds).order_by(order, e.id).limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(select(e.id).where(*conds).limit(1_000_000).subquery()))
    return {"items": [entity_dict(x, ontology, user.role, full=False) for x in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str, request: Request, user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db),
               ontology: Ontology = Depends(onto)) -> dict:
    ent = db.get(Entity, entity_id)
    if ent is None or ent.deleted_at is not None:
        raise HTTPException(404, "entity not found")
    redirected_from = None
    if ent.merged_into:
        redirected_from = ent.id
        ent = db.get(Entity, resolve_canonical(db, ent.id))
    d = entity_dict(ent, ontology, user.role)
    d["redirected_from"] = redirected_from
    d["degree"] = degree(db, ent.id)
    d["signals"] = [{"id": s.id, "label": s.label, "rule_id": s.rule_id, "score": s.score, "what": s.explanation.get("what_happened"),
                     "created_at": s.created_at.isoformat()}
                    for s in db.scalars(select(Signal).where(Signal.entity_ids.contains([ent.id])).order_by(Signal.created_at.desc()).limit(20))]
    d["open_alerts"] = db.scalar(select(func.count()).where(Alert.entities.contains([ent.id]), Alert.status == "OPEN"))
    d["assertions"] = [{"id": a.id, "statement": a.statement, "status": a.status, "epistemic_status": a.epistemic_status}
                       for a in db.scalars(select(Assertion).where(Assertion.subject_ids.contains([ent.id])).limit(20))]
    d["resolution_candidates"] = [
        {"id": c.id, "other": c.entity_b if c.entity_a == ent.id else c.entity_a, "decision": c.decision, "score": c.score,
         "review_status": c.review_status, "merged": c.merged}
        for c in db.scalars(select(ResolutionCandidate).where(or_(ResolutionCandidate.entity_a == ent.id, ResolutionCandidate.entity_b == ent.id)).limit(20))
    ]
    record(db, "entity_view", user, "entity", ent.id, ip=ip_of(request))
    sensitive = [k for k in ent.properties if ontology.sensitivity(ent.type, k) != "public"]
    if sensitive and user.can(P_PII):
        record(db, "pii_access", user, "entity", ent.id, details={"fields": sensitive}, ip=ip_of(request))
    db.commit()
    return d


@router.get("/entities/{entity_id}/relationships")
def entity_relationships(
    entity_id: str,
    relationship_type: list[str] | None = Query(None),
    direction: Literal["in", "out", "both"] = "both",
    time_from: str | None = None,
    time_to: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: Principal = Depends(require(P_READ)),
    db: Session = Depends(get_db),
    ontology: Ontology = Depends(onto),
) -> dict:
    eid = resolve_canonical(db, entity_id)
    r = Relationship
    dirs = []
    if direction in ("out", "both"):
        dirs.append(r.source_id == eid)
    if direction in ("in", "both"):
        dirs.append(r.target_id == eid)
    conds = [or_(*dirs), r.deleted_at.is_(None)]
    if relationship_type:
        conds.append(r.type.in_(relationship_type))
    tf, tt = ts_param(time_from, "time_from"), ts_param(time_to, "time_to")
    if tf:
        conds.append(r.timestamp >= tf)
    if tt:
        conds.append(r.timestamp <= tt)
    rows = db.scalars(select(r).where(*conds).order_by(r.timestamp.desc().nulls_last(), r.id).limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).where(*conds))
    others = {x.target_id if x.source_id == eid else x.source_id for x in rows}
    ents = {e.id: entity_dict(e, ontology, user.role, full=False) for e in db.scalars(select(Entity).where(Entity.id.in_(others)))}
    by_type = dict(db.execute(select(r.type, func.count()).where(or_(r.source_id == eid, r.target_id == eid), r.deleted_at.is_(None)).group_by(r.type)).all())
    return {"entity_id": eid, "items": [{**relationship_dict(x), "other": ents.get(x.target_id if x.source_id == eid else x.source_id)} for x in rows],
            "total": total, "by_type": by_type, "limit": limit, "offset": offset}


@router.get("/relationships/{rel_id}")
def get_relationship(rel_id: str, user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db), ontology: Ontology = Depends(onto)) -> dict:
    r = db.get(Relationship, rel_id)
    if r is None:
        raise HTTPException(404, "relationship not found")
    ents = {e.id: entity_dict(e, ontology, user.role, full=False) for e in db.scalars(select(Entity).where(Entity.id.in_([r.source_id, r.target_id])))}
    return {**relationship_dict(r), "source_entity": ents.get(r.source_id), "target_entity": ents.get(r.target_id)}


class VerifyBody(BaseModel):
    action: Literal["verify", "dispute", "annotate"]
    note: str = Field(min_length=3, max_length=2000)
    confidence: float | None = Field(default=None, ge=0, le=1)


@router.post("/relationships/{rel_id}/review")
def review_relationship(rel_id: str, body: VerifyBody, request: Request, user: Principal = Depends(require(P_VERIFY)),
                        db: Session = Depends(get_db)) -> dict:
    """Analyst modification of a source-derived relationship. The original is preserved in history."""
    r = db.get(Relationship, rel_id)
    if r is None:
        raise HTTPException(404, "relationship not found")
    before = relationship_dict(r)
    mod = {"action": body.action, "note": body.note, "by": user.username, "at": utcnow().isoformat(),
           "previous_status": r.epistemic_status, "previous_confidence": r.confidence}
    if body.action == "verify":
        r.epistemic_status = EpistemicStatus.VERIFIED.value
    elif body.action == "dispute":
        r.epistemic_status = EpistemicStatus.DERIVED.value
        mod["disputed"] = True
    if body.confidence is not None:
        r.confidence = body.confidence
    r.analyst_modifications = [*r.analyst_modifications, mod]
    record(db, "relationship_verify", user, "relationship", r.id, previous_value=before, new_value=relationship_dict(r), ip=ip_of(request))
    db.commit()
    get_cache().bump()
    return relationship_dict(r)


class SearchBody(BaseModel):
    query: str = Field(default="", max_length=500)
    entity_types: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    near: tuple[float, float, float] | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=100_000)


@router.post("/search")
def post_search(body: SearchBody, request: Request, user: Principal = Depends(require(P_SEARCH)), db: Session = Depends(get_db),
                ontology: Ontology = Depends(onto)) -> dict:
    req = SearchRequest(query=body.query, entity_types=body.entity_types, date_from=ts_param(body.date_from, "date_from"),
                        date_to=ts_param(body.date_to, "date_to"), near=body.near, limit=body.limit, offset=body.offset)
    try:
        key = get_cache().key("search", user.role, body.model_dump())
        res = get_cache().get_or_set(key, 60, lambda: search(db, ontology, req, user.role))
    except QueryParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    record(db, "search", user, "search", None, details={"query": body.query[:500], "results": len(res["results"])}, ip=ip_of(request))
    db.commit()
    return res


@router.get("/search")
def get_search(q: str = Query("", max_length=500), limit: int = Query(20, ge=1, le=200), request: Request = None,  # type: ignore[assignment]
               user: Principal = Depends(require(P_SEARCH)), db: Session = Depends(get_db), ontology: Ontology = Depends(onto)) -> dict:
    return post_search(SearchBody(query=q, limit=limit), request, user, db, ontology)
