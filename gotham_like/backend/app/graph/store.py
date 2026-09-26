"""PostgreSQL-backed graph access.

The full graph is never materialised in memory. Traversals run hop-by-hop with
indexed `= ANY(:frontier)` lookups, per-node fan-out caps and a global node budget,
and every truncation is reported so the UI can say the view is partial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.models import Entity, Relationship

Direction = Literal["out", "in", "both"]


@dataclass
class EdgeFilter:
    relationship_types: list[str] | None = None
    direction: Direction = "both"
    time_from: datetime | None = None
    time_to: datetime | None = None
    min_confidence: float = 0.0
    neighbor_types: list[str] | None = None
    epistemic_statuses: list[str] | None = None


@dataclass
class Traversal:
    nodes: dict[str, int] = field(default_factory=dict)  # id -> hop
    edges: dict[str, Any] = field(default_factory=dict)  # id -> row
    truncated: bool = False
    truncation_reasons: list[str] = field(default_factory=list)
    hops: list[dict[str, int]] = field(default_factory=list)


def _edge_conditions(f: EdgeFilter) -> list:
    r = Relationship
    conds = [r.deleted_at.is_(None)]
    if f.relationship_types:
        conds.append(r.type.in_(f.relationship_types))
    if f.time_from is not None:
        conds.append(or_(r.timestamp.is_(None), r.timestamp >= f.time_from))
    if f.time_to is not None:
        conds.append(or_(r.timestamp.is_(None), r.timestamp <= f.time_to))
    if f.min_confidence > 0:
        conds.append(r.confidence >= f.min_confidence)
    if f.epistemic_statuses:
        conds.append(r.epistemic_status.in_(f.epistemic_statuses))
    return conds


def incident_edges(db: Session, ids: list[str], f: EdgeFilter, fanout: int) -> tuple[list[Any], set[str]]:
    """Edges touching `ids`, at most `fanout` per anchor node (most recent first).

    Returns (rows, anchors_that_hit_the_cap).
    """
    if not ids:
        return [], set()
    r = Relationship
    cols = [r.id, r.source_id, r.target_id, r.type, r.timestamp, r.confidence, r.epistemic_status, r.properties, r.source_records, r.provenance]
    parts = []
    conds = _edge_conditions(f)
    if f.direction in ("out", "both"):
        parts.append(
            select(*cols, r.source_id.label("anchor"), r.target_id.label("other"), literal("out").label("dir")).where(r.source_id.in_(ids), *conds)
        )
    if f.direction in ("in", "both"):
        parts.append(
            select(*cols, r.target_id.label("anchor"), r.source_id.label("other"), literal("in").label("dir")).where(r.target_id.in_(ids), *conds)
        )
    u = union_all(*parts).subquery() if len(parts) > 1 else parts[0].subquery()
    rn = func.row_number().over(partition_by=u.c.anchor, order_by=(u.c.timestamp.desc().nulls_last(), u.c.id)).label("rn")
    ranked = select(u, rn).subquery()
    q = select(ranked).where(ranked.c.rn <= fanout + 1)
    if f.neighbor_types:
        e = Entity
        q = q.join(e, e.id == ranked.c.other).where(e.type.in_(f.neighbor_types))
    rows = db.execute(q).all()
    capped = {row.anchor for row in rows if row.rn > fanout}
    return [row for row in rows if row.rn <= fanout], capped


def expand(db: Session, seeds: list[str], depth: int, f: EdgeFilter, max_nodes: int, fanout: int) -> Traversal:
    t = Traversal()
    for s in seeds:
        t.nodes[s] = 0
    frontier = list(dict.fromkeys(seeds))
    for hop in range(1, depth + 1):
        if not frontier:
            break
        rows, capped = incident_edges(db, frontier, f, fanout)
        if capped:
            t.truncated = True
            t.truncation_reasons.append(f"hop {hop}: {len(capped)} high-degree node(s) limited to {fanout} edges")
        new_nodes: list[str] = []
        for row in rows:
            other = row.other
            if other not in t.nodes:
                if len(t.nodes) >= max_nodes:
                    t.truncated = True
                    t.truncation_reasons.append(f"node budget {max_nodes} reached at hop {hop}")
                    break
                t.nodes[other] = hop
                new_nodes.append(other)
            t.edges[row.id] = row
        t.hops.append({"hop": hop, "frontier": len(frontier), "edges": len(rows), "new_nodes": len(new_nodes)})
        frontier = new_nodes
        if len(t.nodes) >= max_nodes:
            break
    return t


def edges_among(db: Session, ids: list[str], f: EdgeFilter | None = None, limit: int = 20000) -> list[Any]:
    if not ids:
        return []
    r = Relationship
    conds = _edge_conditions(f or EdgeFilter())
    q = (
        select(r.id, r.source_id, r.target_id, r.type, r.timestamp, r.confidence, r.epistemic_status, r.properties, r.source_records, r.provenance)
        .where(and_(r.source_id.in_(ids), r.target_id.in_(ids), *conds))
        .limit(limit)
    )
    return db.execute(q).all()


def load_entities(db: Session, ids: list[str] | set[str]) -> dict[str, Entity]:
    ids = list(ids)
    out: dict[str, Entity] = {}
    for i in range(0, len(ids), 5000):
        for e in db.scalars(select(Entity).where(Entity.id.in_(ids[i : i + 5000]))):
            out[e.id] = e
    return out


def resolve_canonical(db: Session, entity_id: str) -> str:
    """Follow merge redirects (entity resolution) to the live entity id."""
    seen = set()
    cur = entity_id
    while cur not in seen:
        seen.add(cur)
        nxt = db.scalar(select(Entity.merged_into).where(Entity.id == cur))
        if not nxt:
            return cur
        cur = nxt
    return cur


def degree(db: Session, entity_id: str) -> dict[str, int]:
    r = Relationship
    rows = db.execute(
        select(r.type, func.count())
        .where(or_(r.source_id == entity_id, r.target_id == entity_id), r.deleted_at.is_(None))
        .group_by(r.type)
    ).all()
    return {t: c for t, c in rows}
