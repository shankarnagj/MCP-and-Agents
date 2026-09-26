"""Graph traversal, path finding and graph analytics."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.common import ip_of, onto, ts_param
from app.audit.service import record
from app.auth.deps import Principal, require
from app.auth.rbac import P_GRAPH
from app.config import get_settings
from app.db import get_db
from app.graph import analytics
from app.graph.paths import find_paths
from app.graph.store import EdgeFilter, edges_among, expand, load_entities, resolve_canonical
from app.models import SIGNAL_LABEL
from app.observability import GRAPH_OPS
from app.ontology import Ontology
from app.services.cache import get_cache
from app.services.serialize import edge_row_dict, entity_dict

router = APIRouter(prefix="/api/graph", tags=["graph"])


class Filters(BaseModel):
    relationship_types: list[str] | None = None
    direction: Literal["out", "in", "both"] = "both"
    time_from: str | None = None
    time_to: str | None = None
    min_confidence: float = Field(default=0.0, ge=0, le=1)
    neighbor_types: list[str] | None = None
    epistemic_statuses: list[str] | None = None

    def to_edge_filter(self, ontology: Ontology) -> EdgeFilter:
        for t in self.relationship_types or []:
            if t not in ontology.relationship_types:
                raise HTTPException(422, f"unknown relationship type {t}")
        for t in self.neighbor_types or []:
            if t not in ontology.entity_types:
                raise HTTPException(422, f"unknown entity type {t}")
        return EdgeFilter(self.relationship_types, self.direction, ts_param(self.time_from, "time_from"), ts_param(self.time_to, "time_to"),
                          self.min_confidence, self.neighbor_types, self.epistemic_statuses)


class SubgraphBody(BaseModel):
    seeds: list[str] = Field(min_length=1, max_length=200)
    depth: int = Field(default=1, ge=0, le=5)
    filters: Filters = Field(default_factory=Filters)
    max_nodes: int = Field(default=500, ge=1, le=5000)
    fanout: int = Field(default=100, ge=1, le=1000)
    include_edges_among: bool = False


def _graph_payload(db: Session, ontology: Ontology, role: str, node_hops: dict[str, int], edge_rows: list) -> dict:
    ents = load_entities(db, node_hops.keys())
    nodes = []
    for nid, hop in node_hops.items():
        e = ents.get(nid)
        if e is None:
            continue
        d = entity_dict(e, ontology, role, full=False)
        d["hop"] = hop
        nodes.append(d)
    return {"nodes": nodes, "edges": [edge_row_dict(r) for r in edge_rows]}


@router.post("/subgraph")
def subgraph(body: SubgraphBody, request: Request, user: Principal = Depends(require(P_GRAPH)), db: Session = Depends(get_db),
             ontology: Ontology = Depends(onto)) -> dict:
    """N-hop neighbourhood expansion (graph windowing: never the whole graph)."""
    s = get_settings()
    depth = min(body.depth, s.graph_max_depth)
    max_nodes = min(body.max_nodes, s.graph_max_nodes)
    fanout = min(body.fanout, s.graph_max_fanout)
    f = body.filters.to_edge_filter(ontology)
    seeds = [resolve_canonical(db, x) for x in body.seeds]

    def compute() -> dict:
        t = expand(db, seeds, depth, f, max_nodes, fanout)
        rows = list(t.edges.values())
        if body.include_edges_among and len(t.nodes) <= 1000:
            known = {r.id for r in rows}
            rows += [r for r in edges_among(db, list(t.nodes), f) if r.id not in known]
        payload = _graph_payload(db, ontology, user.role, t.nodes, rows)
        payload.update(seeds=seeds, depth=depth, truncated=t.truncated, truncation_reasons=t.truncation_reasons, hops=t.hops,
                       limits={"max_nodes": max_nodes, "fanout": fanout})
        return payload

    key = get_cache().key("subgraph", user.role, {**body.model_dump(), "seeds": seeds})
    out = get_cache().get_or_set(key, 120, compute)
    GRAPH_OPS.labels(operation="subgraph").inc()
    record(db, "graph_operation", user, "graph", ",".join(seeds)[:200], details={"op": "subgraph", "depth": depth, "nodes": len(out["nodes"])},
           ip=ip_of(request))
    db.commit()
    return out


class PathBody(BaseModel):
    source: str
    target: str
    mode: Literal["shortest", "all_simple", "weighted"] = "shortest"
    max_depth: int = Field(default=4, ge=1, le=8)
    relationship_types: list[str] | None = None
    respect_direction: bool = False
    max_paths: int = Field(default=10, ge=1, le=50)
    filters: Filters = Field(default_factory=Filters)


@router.post("/path")
def path(body: PathBody, request: Request, user: Principal = Depends(require(P_GRAPH)), db: Session = Depends(get_db),
         ontology: Ontology = Depends(onto)) -> dict:
    s = get_settings()
    for t in body.relationship_types or []:
        if t not in ontology.relationship_types:
            raise HTTPException(422, f"unknown relationship type {t}")
    src, dst = resolve_canonical(db, body.source), resolve_canonical(db, body.target)
    res = find_paths(db, src, dst, body.mode, body.max_depth, body.relationship_types, body.respect_direction, min(body.max_paths, s.path_max_results),
                     fanout=s.graph_max_fanout, max_nodes=s.graph_max_nodes * 3, f=body.filters.to_edge_filter(ontology))
    ids = {n for p in res["paths"] for n in p["nodes"]} | {src, dst}
    ents = load_entities(db, ids)
    res["entities"] = {i: entity_dict(e, ontology, user.role, full=False) for i, e in ents.items()}
    GRAPH_OPS.labels(operation=f"path_{body.mode}").inc()
    record(db, "graph_operation", user, "graph", f"{src}->{dst}", details={"op": "path", "mode": body.mode, "found": res["found"]}, ip=ip_of(request))
    db.commit()
    return res


class AnalyticsBody(BaseModel):
    seeds: list[str] = Field(min_length=1, max_length=500)
    depth: int = Field(default=2, ge=0, le=4)
    algorithms: list[str] = Field(default_factory=lambda: ["degree_centrality", "betweenness_centrality", "pagerank", "connected_components"])
    filters: Filters = Field(default_factory=Filters)
    max_nodes: int = Field(default=2000, ge=1, le=10000)
    k_core: int = Field(default=2, ge=1, le=50)
    max_cycle_len: int = Field(default=6, ge=2, le=10)
    top_k: int = Field(default=25, ge=1, le=200)

    @field_validator("algorithms")
    @classmethod
    def _algs(cls, v: list[str]) -> list[str]:
        bad = set(v) - analytics.ALGORITHMS
        if bad:
            raise ValueError(f"unknown algorithms: {sorted(bad)}")
        return v


@router.post("/analytics")
def run_analytics(body: AnalyticsBody, request: Request, user: Principal = Depends(require(P_GRAPH)), db: Session = Depends(get_db),
                  ontology: Ontology = Depends(onto)) -> dict:
    """Graph algorithms on a bounded window around the seeds. Outputs are ANALYTICAL SIGNALS."""
    s = get_settings()
    f = body.filters.to_edge_filter(ontology)
    seeds = [resolve_canonical(db, x) for x in body.seeds]

    def compute() -> dict:
        t = expand(db, seeds, body.depth, f, min(body.max_nodes, s.graph_max_nodes * 5), s.graph_max_fanout)
        rows = list(t.edges.values())
        if len(t.nodes) <= 3000:
            known = {r.id for r in rows}
            rows += [r for r in edges_among(db, list(t.nodes), f) if r.id not in known]
        g = analytics.build_graph(rows)
        g.add_nodes_from(t.nodes)
        res = analytics.run(g, body.algorithms, top_k=body.top_k, k_core=body.k_core, max_cycle_len=body.max_cycle_len)
        ids = {x["id"] for r in res["results"].values() for x in r.get("top", [])}
        ents = load_entities(db, ids)
        res["entities"] = {i: entity_dict(e, ontology, user.role, full=False) for i, e in ents.items()}
        res["window"] = {"seeds": seeds, "depth": body.depth, "nodes": len(t.nodes), "edges": len(rows), "truncated": t.truncated,
                         "truncation_reasons": t.truncation_reasons}
        return res

    key = get_cache().key("analytics", user.role, {**body.model_dump(), "seeds": seeds})
    out = get_cache().get_or_set(key, 300, compute)
    GRAPH_OPS.labels(operation="analytics").inc()
    record(db, "graph_operation", user, "graph", ",".join(seeds)[:200], details={"op": "analytics", "algorithms": body.algorithms}, ip=ip_of(request))
    db.commit()
    out["label"] = SIGNAL_LABEL
    return out
