from types import SimpleNamespace

import pytest

from app.graph import analytics
from app.graph.paths import _undirected_view
from app.models import SIGNAL_LABEL


def edges(pairs):
    return [SimpleNamespace(id=f"e{i}", source_id=a, target_id=b, type=t, confidence=c) for i, (a, b, t, c) in enumerate(pairs)]


@pytest.fixture()
def g():
    # triangle a->b->c->a (cycle / SCC), plus a star around hub h, plus an isolated pair x-y
    E = [("a", "b", "T", 1), ("b", "c", "T", 1), ("c", "a", "T", 1)] + [("h", f"s{i}", "U", 1) for i in range(5)] + [("a", "h", "U", 1), ("x", "y", "U", 1)]
    return analytics.build_graph(edges(E))


def test_all_algorithms_labelled_as_signals(g):
    res = analytics.run(g, sorted(analytics.ALGORITHMS))
    assert res["label"] == SIGNAL_LABEL and "not establish" in res["caveat"]
    r = res["results"]
    assert r["degree_centrality"]["top"][0]["id"] == "h"
    assert r["betweenness_centrality"]["top"][0]["id"] in ("h", "a")
    assert sum(x["score"] for x in analytics.run(g, ["pagerank"], top_k=100)["results"]["pagerank"]["top"]) == pytest.approx(1.0, abs=1e-3)
    assert r["connected_components"]["count"] == 2
    assert r["strongly_connected_components"]["components"][0] == ["a", "b", "c"]
    assert r["cycles"]["count"] == 1 and set(r["cycles"]["cycles"][0]) == {"a", "b", "c"}
    assert set(r["k_core"]["members"]) == {"a", "b", "c"}
    assert r["communities"]["count"] >= 2


def test_unknown_algorithm_rejected(g):
    with pytest.raises(ValueError):
        analytics.run(g, ["astrology"])


def test_empty_graph():
    import networkx as nx

    assert analytics.run(nx.MultiDiGraph(), ["pagerank"])["results"] == {}


def test_weighted_view_prefers_high_confidence_and_respects_constraints():
    import networkx as nx

    g = analytics.build_graph(edges([("a", "b", "X", 0.2), ("b", "d", "X", 0.2), ("a", "c", "Y", 1.0), ("c", "d", "Y", 1.0)]))
    h = _undirected_view(g, None, False)
    assert nx.dijkstra_path(h, "a", "d", weight="weight") == ["a", "c", "d"]
    assert nx.shortest_path(_undirected_view(g, {"X"}, False), "a", "d") == ["a", "b", "d"]
    with pytest.raises(nx.NetworkXNoPath):
        nx.shortest_path(_undirected_view(g, None, True), "d", "a")
