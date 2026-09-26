"""Latency budgets on the synthetic dataset, and bounded behaviour on a generated large graph.

Budgets are deliberately generous (shared CI machines); the full-scale numbers live in
docs/BENCHMARKS.md (scripts/benchmark.py).
"""

import importlib.util
import os
import statistics
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.perf


def p95(fn, n=15):
    xs = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t) * 1000)
    xs.sort()
    return xs[int(0.95 * (len(xs) - 1))], statistics.median(xs)


def test_api_latency_budgets(client, H, ids):
    from app.services.cache import get_cache

    h = H["analyst"]
    budgets = {
        "search_identifier": (lambda: client.post("/api/search", json={"query": "device:DV-7F3A-SHARED"}, headers=h), 250),
        "search_fuzzy": (lambda: client.post("/api/search", json={"query": "Zusil Lobetul"}, headers=h), 400),
        "entity_profile": (lambda: client.get(f"/api/entities/{ids['shared_device']}", headers=h), 250),
        "timeline_entity": (lambda: client.get("/api/timeline", params={"entity_id": ids["shared_device"]}, headers=h), 250),
        "timeline_all_events_histogram": (lambda: client.get("/api/timeline", params={"limit": 500, "bucket": "day"}, headers=h), 1500),
        "geo_radius_time": (lambda: client.post("/api/geo/query", json={"lat": 51.45, "lon": 3.6, "radius_m": 2000, "time_from": "2026-02-14T00:00:00Z",
                                                                         "time_to": "2026-02-15T00:00:00Z"}, headers=h), 400),
        "path_shortest": (lambda: client.post("/api/graph/path", json={"source": ids["aml_person"], "target": ids["merchant_org"], "max_depth": 5}, headers=h), 1500),
    }
    results = {}
    for name, (fn, budget) in budgets.items():
        get_cache().bump()  # measure uncached
        worst, med = p95(fn)
        results[name] = (round(med, 1), round(worst, 1), budget)
        assert worst < budget, f"{name}: p95 {worst:.0f} ms > {budget} ms"
    print("\nlatency (median, p95, budget) ms:", results)


def test_subgraph_expansion_is_bounded(client, H, ids):
    h = H["analyst"]
    t = time.perf_counter()
    r = client.post("/api/graph/subgraph", json={"seeds": [ids["harbor"]], "depth": 3, "max_nodes": 2000, "fanout": 200}, headers=h).json()
    elapsed = (time.perf_counter() - t) * 1000
    assert len(r["nodes"]) <= 2000 and elapsed < 5000


def test_cache_serves_repeated_graph_reads(client, H, ids):
    from app.services.cache import get_cache

    body = {"seeds": [ids["shared_device"]], "depth": 2}
    get_cache().bump()
    t = time.perf_counter()
    client.post("/api/graph/subgraph", json=body, headers=H["analyst"])
    cold = time.perf_counter() - t
    t = time.perf_counter()
    client.post("/api/graph/subgraph", json=body, headers=H["analyst"])
    warm = time.perf_counter() - t
    assert warm < cold


@pytest.mark.slow
def test_large_generated_graph(tmp_path):
    """Generate 50k entities / 250k relationships / 50k events and check windowed operations stay fast."""
    if os.environ.get("TESSERA_SKIP_SLOW"):
        pytest.skip("TESSERA_SKIP_SLOW set")
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("bench", root / "scripts" / "benchmark.py")
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    admin = os.environ["TESSERA_DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    url = bench.ensure_db(admin, "tessera_bench_pytest")
    from app.services.seed import migrate

    migrate(url)
    load = bench.generate(url, 50_000, 250_000, 50_000, seed=3)
    assert load["relationships"]["rows"] == 250_000
    prev = os.environ["TESSERA_DATABASE_URL"]
    try:
        q = bench.run_queries(url, 50_000, 8, 3, tmp_path)
    finally:
        os.environ["TESSERA_DATABASE_URL"] = prev
        from app.config import get_settings
        from app.db import reset_engine

        get_settings.cache_clear()
        reset_engine()
    assert q["expand_2hop_typical"]["p95_ms"] < 1000
    assert q["search_identifier"]["p95_ms"] < 200
    assert q["geo_radius_2km_time_window"]["p95_ms"] < 300
    assert q["timeline_entity"]["p95_ms"] < 300
    assert (tmp_path / "explain_incident_edges_1hop.txt").read_text().count("Index") >= 1
