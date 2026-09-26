"""Classical graph analytics on bounded subgraphs.

All outputs are ANALYTICAL SIGNALS: mathematical properties of the recorded
graph. They are not evidence of wrongdoing or of real-world importance.
"""

from __future__ import annotations

from typing import Any

import networkx as nx

from app.models import SIGNAL_LABEL

ALGORITHMS = {
    "degree_centrality", "betweenness_centrality", "pagerank", "connected_components", "strongly_connected_components",
    "communities", "k_core", "cycles", "shortest_paths",
}

CAVEAT = (
    "ANALYTICAL SIGNAL: a mathematical property of the recorded relationships within the analysed window. "
    "It does not establish significance, intent, or wrongdoing, and depends on data coverage."
)


def build_graph(edges: list[Any]) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for row in edges:
        g.add_edge(row.source_id, row.target_id, key=row.id, type=row.type, confidence=row.confidence or 0.0)
    return g


def _top(scores: dict[str, float], k: int) -> list[dict[str, Any]]:
    return [{"id": n, "score": round(s, 6)} for n, s in sorted(scores.items(), key=lambda x: -x[1])[:k]]


def run(g: nx.MultiDiGraph, algorithms: list[str], top_k: int = 25, k_core: int = 2, max_cycle_len: int = 6, max_cycles: int = 50,
        seed: int = 7) -> dict[str, Any]:
    unknown = set(algorithms) - ALGORITHMS
    if unknown:
        raise ValueError(f"unknown algorithms: {sorted(unknown)}")
    simple_d = nx.DiGraph(g)
    simple_u = nx.Graph(simple_d.to_undirected())
    simple_u.remove_edges_from(nx.selfloop_edges(simple_u))
    n = simple_u.number_of_nodes()
    res: dict[str, Any] = {"label": SIGNAL_LABEL, "caveat": CAVEAT, "graph": {"nodes": n, "edges": g.number_of_edges()}, "results": {}}
    out = res["results"]
    if n == 0:
        return res
    for alg in algorithms:
        if alg == "degree_centrality":
            out[alg] = {"top": _top(nx.degree_centrality(simple_u), top_k), "method": "networkx.degree_centrality (undirected)"}
        elif alg == "betweenness_centrality":
            k = None if n <= 1500 else 300
            out[alg] = {"top": _top(nx.betweenness_centrality(simple_u, k=k, seed=seed), top_k),
                        "method": "Brandes" + (f" (sampled k={k})" if k else " (exact)")}
        elif alg == "pagerank":
            out[alg] = {"top": _top(nx.pagerank(simple_d, alpha=0.85), top_k), "method": "PageRank alpha=0.85 (directed)"}
        elif alg == "connected_components":
            comps = sorted(nx.connected_components(simple_u), key=len, reverse=True)
            out[alg] = {"count": len(comps), "sizes": [len(c) for c in comps[:top_k]], "components": [sorted(c)[:200] for c in comps[:10]],
                        "method": "weakly connected (undirected)"}
        elif alg == "strongly_connected_components":
            comps = [c for c in nx.strongly_connected_components(simple_d) if len(c) > 1]
            comps.sort(key=len, reverse=True)
            out[alg] = {"count_nontrivial": len(comps), "components": [sorted(c) for c in comps[:top_k]], "method": "Tarjan (directed)"}
        elif alg == "communities":
            comms = nx.community.louvain_communities(simple_u, seed=seed)
            comms = sorted(comms, key=len, reverse=True)
            out[alg] = {"count": len(comms), "communities": [sorted(c)[:200] for c in comms[:top_k]],
                        "modularity": round(nx.community.modularity(simple_u, comms), 4), "method": f"Louvain (seed={seed})"}
        elif alg == "k_core":
            core = nx.core_number(simple_u)
            members = [nid for nid, c in core.items() if c >= k_core]
            out[alg] = {"k": k_core, "members": members[:500], "max_core": max(core.values()) if core else 0, "method": "Batagelj-Zaversnik"}
        elif alg == "cycles":
            cycles = []
            for c in nx.simple_cycles(simple_d, length_bound=max_cycle_len):
                if len(c) > 1:
                    cycles.append(c)
                if len(cycles) >= max_cycles:
                    break
            out[alg] = {"cycles": cycles, "count": len(cycles), "truncated": len(cycles) >= max_cycles,
                        "method": f"Johnson (length ≤ {max_cycle_len}, directed)"}
        elif alg == "shortest_paths":
            lengths = dict(nx.all_pairs_shortest_path_length(simple_u, cutoff=4)) if n <= 400 else {}
            ecc = {k: max(v.values()) for k, v in lengths.items() if v}
            out[alg] = {"diameter_within_window": max(ecc.values()) if ecc else None,
                        "average_shortest_path": round(nx.average_shortest_path_length(simple_u), 4) if n <= 400 and nx.is_connected(simple_u) else None,
                        "method": "BFS (cutoff 4; windows ≤ 400 nodes)"}
    return res
