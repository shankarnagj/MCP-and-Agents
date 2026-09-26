"""Path finding between entities.

Strategy: bidirectional, fan-out-limited expansion in SQL until the two search
frontiers meet (or depth is exhausted), then exact algorithms from NetworkX on
that bounded window: shortest path, all simple paths (with limits), weighted
(Dijkstra) path and relationship-constrained paths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import networkx as nx
from sqlalchemy.orm import Session

from app.graph.store import EdgeFilter, incident_edges

PathMode = Literal["shortest", "all_simple", "weighted"]


@dataclass
class PathSearchWindow:
    graph: nx.MultiDiGraph
    edges: dict[str, Any]
    met: bool
    truncated: bool
    notes: list[str]


def _add_rows(g: nx.MultiDiGraph, edges: dict[str, Any], rows: list[Any]) -> None:
    for row in rows:
        if row.id in edges:
            continue
        edges[row.id] = row
        g.add_edge(row.source_id, row.target_id, key=row.id, type=row.type, confidence=row.confidence or 0.0)


def search_window(db: Session, a: str, b: str, max_depth: int, f: EdgeFilter, fanout: int, max_nodes: int,
                  extra_rounds: int = 0) -> PathSearchWindow:
    """extra_rounds: keep expanding after the frontiers meet (to discover alternative paths)."""
    g = nx.MultiDiGraph()
    g.add_nodes_from([a, b])
    edges: dict[str, Any] = {}
    seen_a, seen_b = {a}, {b}
    front_a, front_b = [a], [b]
    truncated = False
    notes: list[str] = []
    met = a == b
    depth_a = depth_b = 0
    both = EdgeFilter(**{**f.__dict__, "direction": "both"})
    while (not met or extra_rounds > 0) and depth_a + depth_b < max_depth and (front_a or front_b):
        if met:
            extra_rounds -= 1
        # expand the smaller frontier first (classic bidirectional BFS heuristic)
        expand_a = (len(front_a) <= len(front_b) and front_a) or not front_b
        frontier = front_a if expand_a else front_b
        rows, capped = incident_edges(db, frontier, both, fanout)
        if capped:
            truncated = True
            notes.append(f"{len(capped)} high-degree node(s) fan-out limited to {fanout}")
        _add_rows(g, edges, rows)
        seen = seen_a if expand_a else seen_b
        nxt = []
        for row in rows:
            if row.other not in seen:
                seen.add(row.other)
                nxt.append(row.other)
        if expand_a:
            front_a, depth_a = nxt, depth_a + 1
        else:
            front_b, depth_b = nxt, depth_b + 1
        if seen_a & seen_b:
            met = True
        if g.number_of_nodes() > max_nodes:
            truncated = True
            notes.append(f"search window exceeded {max_nodes} nodes")
            break
    return PathSearchWindow(g, edges, met, truncated, notes)


def _undirected_view(g: nx.MultiDiGraph, allowed: set[str] | None, respect_direction: bool) -> nx.Graph | nx.DiGraph:
    h: nx.Graph | nx.DiGraph = nx.DiGraph() if respect_direction else nx.Graph()
    h.add_nodes_from(g.nodes)
    for u, v, key, data in g.edges(keys=True, data=True):
        if allowed and data["type"] not in allowed:
            continue
        w = -math.log(max(data["confidence"], 1e-6)) + 1e-3  # low-confidence edges are "longer"
        if h.has_edge(u, v) and h[u][v]["weight"] <= w:
            continue
        h.add_edge(u, v, key=key, type=data["type"], weight=w)
    return h


def find_paths(
    db: Session,
    source: str,
    target: str,
    mode: PathMode = "shortest",
    max_depth: int = 4,
    relationship_types: list[str] | None = None,
    respect_direction: bool = False,
    max_paths: int = 10,
    fanout: int = 200,
    max_nodes: int = 5000,
    f: EdgeFilter | None = None,
) -> dict[str, Any]:
    f = f or EdgeFilter()
    if relationship_types:
        f = EdgeFilter(**{**f.__dict__, "relationship_types": relationship_types})
    win = search_window(db, source, target, max_depth, f, fanout, max_nodes, extra_rounds=2 if mode == "all_simple" else 0)
    h = _undirected_view(win.graph, set(relationship_types) if relationship_types else None, respect_direction)
    paths: list[list[str]] = []
    try:
        if mode == "shortest":
            paths = [nx.shortest_path(h, source, target)]
        elif mode == "weighted":
            paths = [nx.dijkstra_path(h, source, target, weight="weight")]
        else:
            for p in nx.all_simple_paths(h, source, target, cutoff=max_depth):
                paths.append(p)
                if len(paths) >= max_paths:
                    break
            paths.sort(key=len)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        paths = []
    out_paths = []
    for p in paths:
        steps = []
        total_w = 0.0
        min_conf = 1.0
        for u, v in zip(p, p[1:]):
            data = h[u][v]
            row = win.edges[data["key"]]
            total_w += data["weight"]
            min_conf = min(min_conf, row.confidence or 0.0)
            steps.append({"from": u, "to": v, "edge_id": row.id, "relationship_type": row.type,
                          "direction": "forward" if row.source_id == u else "reverse",
                          "timestamp": row.timestamp.isoformat() if row.timestamp else None, "confidence": row.confidence,
                          "epistemic_status": row.epistemic_status, "source_records": row.source_records, "provenance": row.provenance})
        out_paths.append({"nodes": p, "length": len(p) - 1, "steps": steps, "weight": round(total_w, 4), "min_confidence": min_conf})
    return {
        "mode": mode,
        "source": source,
        "target": target,
        "paths": out_paths,
        "found": bool(out_paths),
        "search": {"window_nodes": win.graph.number_of_nodes(), "window_edges": win.graph.number_of_edges(), "frontiers_met": win.met,
                   "truncated": win.truncated, "notes": win.notes, "max_depth": max_depth, "respect_direction": respect_direction,
                   "relationship_types": relationship_types},
        "explanation": {
            "what": f"{'No path' if not out_paths else str(len(out_paths)) + ' path(s)'} between the two entities within {max_depth} hops.",
            "assumptions": [
                "Paths are built from recorded relationships; a path shows connectivity, not intent, causation or wrongdoing.",
                "Weighted mode treats low-confidence edges as longer (weight = -ln(confidence)).",
                "High-degree nodes are fan-out limited; truncated searches may miss paths.",
            ],
            "uncertain": ["Paths through high-degree hubs (e.g. popular locations, shared infrastructure) are often coincidental."]
            + (["Search was truncated; absence of a path is not evidence of no connection."] if win.truncated else []),
        },
    }
