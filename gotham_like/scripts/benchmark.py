#!/usr/bin/env python3
"""Performance benchmark on a large generated graph (SYNTHETIC / DEMONSTRATION DATA).

Creates a separate database, bulk-loads N entities / M relationships / K events with a
heavy-tailed degree distribution (hubs exist, as in real data) via COPY, then times the
*application* code paths (the same functions the API uses):

  graph:   1-hop / 2-hop / 3-hop windowed expansion, shortest path, analytics on a window
  search:  identifier lookup, fuzzy trigram search
  time:    entity timeline, global time-window histogram
  geo:     2 km radius × time window, KNN nearest

and stores EXPLAIN (ANALYZE, BUFFERS) plans for the expensive statements.

    python scripts/benchmark.py --entities 1000000 --relationships 10000000 --events 2000000
    python scripts/benchmark.py --quick         # 50k / 250k / 50k smoke run
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

TYPES = [("Person", 0.25), ("Account", 0.30), ("Device", 0.12), ("Transaction", 0.18), ("Location", 0.03), ("IPAddress", 0.08), ("Organization", 0.04)]
REL_TYPES = ["OWNS", "USED", "INITIATED", "TRANSFERRED_TO", "LOCATED_AT", "CONNECTED_TO", "WORKS_FOR", "VISITED"]
T0 = datetime(2025, 1, 1, tzinfo=UTC)


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def timed(fn, n: int) -> dict:  # noqa: ANN001
    out = []
    res = None
    for _ in range(n):
        t = time.perf_counter()
        res = fn()
        out.append((time.perf_counter() - t) * 1000)
    return {"n": n, "p50_ms": round(statistics.median(out), 2), "p95_ms": round(pct(out, 0.95), 2), "max_ms": round(max(out), 2), "_last": res}


def ensure_db(admin_url: str, name: str) -> str:
    from sqlalchemy import create_engine, text

    eng = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {name}"))
    eng.dispose()
    url = admin_url.rsplit("/", 1)[0] + f"/{name}"
    e2 = create_engine(url, isolation_level="AUTOCOMMIT")
    with e2.connect() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    e2.dispose()
    return url


def copy_rows(conn, table: str, cols: list[str], rows_iter, batch: int = 200_000) -> int:  # noqa: ANN001
    n = 0
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
            for row in rows_iter:
                cp.write_row(row)
                n += 1
    return n


def generate(url: str, n_ent: int, n_rel: int, n_evt: int, seed: int) -> dict:
    import psycopg

    rng = random.Random(seed)
    dsn = url.replace("postgresql+psycopg://", "postgresql://")
    type_of: list[str] = []
    cum = []
    acc = 0.0
    for t, w in TYPES:
        acc += w
        cum.append((acc, t))
    for _ in range(n_ent):
        r = rng.random()
        type_of.append(next(t for c, t in cum if r <= c) if r <= cum[-1][0] else TYPES[-1][0])
    t_load = time.time()
    now = datetime.now(UTC)

    def ents():
        for i in range(n_ent):
            t = type_of[i]
            geo = t in ("Location", "Transaction", "Device") and rng.random() < 0.8
            lat = round(40 + rng.gauss(10, 6), 5) if geo else None
            lon = round(rng.gauss(10, 12), 5) if geo else None
            label = f"{t[:3].upper()}-{i:08d}"
            yield (f"b{i}", t, label, json.dumps({"name": label}), "{src_bench}", 1.0, "DERIVED", '{"source":"bench"}', "SYNTHETIC / DEMONSTRATION DATA",
                   f"SRID=4326;POINT({lon} {lat})" if geo else None, lat, lon,
                   (T0 + timedelta(seconds=rng.randint(0, 365 * 86400))) if t == "Transaction" else None, f"{label.lower()} {t.lower()}", now, now)

    def ident_rows():
        for i in range(n_ent):
            yield (f"b{i}", "key", f"{type_of[i][:3].upper()}{i:08d}")

    # heavy-tailed endpoints: 1% of nodes attract ~25% of edge endpoints (hubs)
    hubs = max(1, n_ent // 100)

    def endpoint() -> int:
        return rng.randrange(hubs) * 100 if rng.random() < 0.25 else rng.randrange(n_ent)

    def rels():
        for i in range(n_rel):
            s, t = endpoint(), endpoint()
            if s == t:
                t = (t + 1) % n_ent
            yield (f"r{i}", f"b{s}", f"b{t}", REL_TYPES[i % len(REL_TYPES)], T0 + timedelta(seconds=rng.randint(0, 365 * 86400)), round(rng.uniform(0.6, 1), 3),
                   "DERIVED", "{}", "{src_bench}", '{"source":"bench"}', "[]", now, now)

    def evts():
        for i in range(n_evt):
            a, b = endpoint(), rng.randrange(n_ent)
            lat, lon = round(40 + rng.gauss(10, 6), 5), round(rng.gauss(10, 12), 5)
            yield (f"e{i}", rng.choice(["login", "transaction", "device_connection", "location_change"]), T0 + timedelta(seconds=rng.randint(0, 365 * 86400)),
                   "{" + f"b{a},b{b}" + "}", f"SRID=4326;POINT({lon} {lat})", lat, lon, "bench", "{}", 1.0, "DERIVED", "{}", now)

    stats = {}
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET synchronous_commit = off")
        # Standard bulk-load strategy: drop secondary indexes, COPY, rebuild them afterwards.
        idx = conn.execute("""SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'
                              AND tablename IN ('entities', 'relationships', 'events', 'entity_identifiers')
                              AND indexname NOT LIKE '%pkey' AND indexname NOT LIKE 'uq_%'""").fetchall()
        for name, _ in idx:
            conn.execute(f'DROP INDEX "{name}"')
        for name, table, cols, it in (
            ("entities", "entities", ["id", "type", "label", "properties", "source_ids", "confidence", "epistemic_status", "provenance", "classification", "geom",
                                      "lat", "lon", "observed_at", "search_text", "created_at", "updated_at"], ents()),
            ("identifiers", "entity_identifiers", ["entity_id", "kind", "value"], ident_rows()),
            ("relationships", "relationships", ["id", "source_id", "target_id", "type", "timestamp", "confidence", "epistemic_status", "properties", "source_records",
                                                "provenance", "analyst_modifications", "created_at", "updated_at"], rels()),
            ("events", "events", ["id", "event_type", "timestamp", "entity_ids", "geom", "lat", "lon", "source", "properties", "confidence", "epistemic_status",
                                  "provenance", "created_at"], evts()),
        ):
            t = time.time()
            n = copy_rows(conn, table, cols, it)
            stats[name] = {"rows": n, "seconds": round(time.time() - t, 1), "rows_per_s": int(n / max(time.time() - t, 1e-6))}
            print(f"  loaded {n:,} {name} in {stats[name]['seconds']} s", flush=True)
        t = time.time()
        conn.execute("SET maintenance_work_mem = '1GB'")
        conn.execute("SET max_parallel_maintenance_workers = 4")
        for name, ddl in idx:
            conn.execute(ddl)
        stats["index_build_seconds"] = round(time.time() - t, 1)
        stats["indexes_rebuilt"] = len(idx)
        print(f"  rebuilt {len(idx)} indexes in {stats['index_build_seconds']} s", flush=True)
        t = time.time()
        conn.execute("VACUUM ANALYZE")
        stats["vacuum_analyze_s"] = round(time.time() - t, 1)
        size = conn.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
    stats["load_seconds"] = round(time.time() - t_load, 1)
    stats["database_size"] = size
    stats["hubs"] = hubs
    return stats


def explain(db, sql: str, params: dict) -> str:  # noqa: ANN001
    from sqlalchemy import text

    rows = db.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + sql), params).all()
    return "\n".join(r[0] for r in rows)


def run_queries(url: str, n_ent: int, reps: int, seed: int, out_dir: Path) -> dict:
    os.environ["TESSERA_DATABASE_URL"] = url
    os.environ.setdefault("TESSERA_REDIS_URL", "")
    from app.config import get_settings

    get_settings.cache_clear()
    from app.db import SessionLocal, reset_engine
    from app.graph import analytics
    from app.graph.paths import find_paths
    from app.graph.store import EdgeFilter, edges_among, expand
    from app.ontology import get_ontology
    from app.search.service import SearchRequest, search
    from app.services import geo
    from app.services.timeline import timeline

    reset_engine()
    rng = random.Random(seed + 1)
    onto = get_ontology()
    res: dict = {}
    with SessionLocal() as db:
        f = EdgeFilter()
        # typical (non-hub) seeds and hub seeds
        typical = [f"b{rng.randrange(n_ent)}" for _ in range(reps)]
        hub = [f"b{rng.randrange(max(1, n_ent // 100)) * 100}" for _ in range(reps)]
        it = iter(typical * 10)
        res["expand_1hop_typical"] = timed(lambda: len(expand(db, [next(it)], 1, f, 2000, 200).nodes), reps)
        it = iter(typical * 10)
        res["expand_2hop_typical"] = timed(lambda: len(expand(db, [next(it)], 2, f, 2000, 100).nodes), reps)
        it = iter(typical * 10)
        res["expand_3hop_typical"] = timed(lambda: len(expand(db, [next(it)], 3, f, 2000, 50).nodes), reps)
        ih = iter(hub * 10)
        res["expand_2hop_hub_seed"] = timed(lambda: len(expand(db, [next(ih)], 2, f, 2000, 100).nodes), reps)
        pairs = iter([(f"b{rng.randrange(n_ent)}", f"b{rng.randrange(n_ent)}") for _ in range(reps * 2)])
        res["shortest_path_depth6"] = timed(lambda: find_paths(db, *next(pairs), mode="shortest", max_depth=6, fanout=100, max_nodes=20000)["found"], reps)
        seeds = iter(typical * 10)

        def analytics_window() -> int:
            t = expand(db, [next(seeds)], 2, f, 3000, 100)
            rows = list(t.edges.values()) + edges_among(db, list(t.nodes), f)
            g = analytics.build_graph(rows)
            analytics.run(g, ["degree_centrality", "pagerank", "connected_components", "betweenness_centrality"])
            return g.number_of_nodes()

        res["analytics_2hop_window"] = timed(analytics_window, max(3, reps // 3))
        labels = iter([f"ACC-{rng.randrange(n_ent):08d}" for _ in range(reps * 2)])
        res["search_identifier"] = timed(lambda: len(search(db, onto, SearchRequest(query=f"id:{next(labels)}"), "ANALYST")["results"]), reps)
        res["search_fuzzy"] = timed(lambda: len(search(db, onto, SearchRequest(query=f"acc-{rng.randrange(10**6):06d}", limit=20), "ANALYST")["results"]), reps)
        ents = iter(hub * 10)
        res["timeline_entity"] = timed(lambda: timeline(db, [next(ents)], limit=500)["total"], reps)
        res["timeline_global_week"] = timed(lambda: timeline(db, None, None, T0 + timedelta(days=100), T0 + timedelta(days=107), limit=500, bucket="hour")["total"], max(3, reps // 3))
        pts = iter([(round(40 + rng.gauss(10, 6), 3), round(rng.gauss(10, 12), 3)) for _ in range(reps * 2)])

        def radius() -> int:
            lat, lon = next(pts)
            r = geo.spatio_temporal(db, onto, "ANALYST", lat, lon, 2000, None, T0 + timedelta(days=30), T0 + timedelta(days=60), ["Transaction"], None, None, None,
                                    ("entities", "events"), 1000)
            return sum(r["counts"].values())

        res["geo_radius_2km_time_window"] = timed(radius, reps)
        res["geo_knn_10"] = timed(lambda: len(geo.nearest(db, onto, "ANALYST", *next(pts), k=10)), reps)
        # EXPLAIN ANALYZE of expensive statements
        plans = {
            "incident_edges_1hop": explain(db, """SELECT id, source_id, target_id, type FROM relationships WHERE source_id = ANY(:ids) AND deleted_at IS NULL
                                                  UNION ALL SELECT id, source_id, target_id, type FROM relationships WHERE target_id = ANY(:ids) AND deleted_at IS NULL""",
                                           {"ids": typical[:20]}),
            "timeline_entity": explain(db, "SELECT * FROM events WHERE entity_ids && CAST(:ids AS varchar[]) AND deleted_at IS NULL ORDER BY timestamp LIMIT 500",
                                       {"ids": hub[:1]}),
            "geo_radius_time": explain(db, """SELECT id FROM entities WHERE type='Transaction' AND merged_into IS NULL AND deleted_at IS NULL
                                              AND ST_DWithin(geom, ST_SetSRID(ST_MakePoint(10, 50), 4326)::geography, 2000)
                                              AND observed_at BETWEEN :a AND :b""", {"a": T0 + timedelta(days=30), "b": T0 + timedelta(days=60)}),
            "search_trigram": explain(db, "SELECT id FROM entities WHERE 'acc-00012345' <% search_text AND word_similarity('acc-00012345', search_text) >= 0.45 LIMIT 50", {}),
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    for k, v in plans.items():
        (out_dir / f"explain_{k}.txt").write_text(v)
    for v in res.values():
        v.pop("_last", None)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entities", type=int, default=1_000_000)
    ap.add_argument("--relationships", type=int, default=10_000_000)
    ap.add_argument("--events", type=int, default=2_000_000)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep the benchmark database")
    ap.add_argument("--admin-url", default=os.environ.get("TESSERA_ADMIN_DATABASE_URL", "postgresql+psycopg://tessera:tessera@localhost:5432/postgres"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "benchmarks"))
    a = ap.parse_args()
    if a.quick:
        a.entities, a.relationships, a.events, a.reps = 50_000, 250_000, 50_000, 10
    db_name = "tessera_bench"
    url = ensure_db(a.admin_url, db_name)
    from app.services.seed import migrate

    print(f"Migrating {db_name} …", flush=True)
    migrate(url)
    print(f"Generating {a.entities:,} entities / {a.relationships:,} relationships / {a.events:,} events …", flush=True)
    load = generate(url, a.entities, a.relationships, a.events, a.seed)
    print("Running queries …", flush=True)
    q = run_queries(url, a.entities, a.reps, a.seed, Path(a.out))
    result = {"generated_at": datetime.now(UTC).isoformat(), "label": "SYNTHETIC / DEMONSTRATION DATA",
              "scale": {"entities": a.entities, "relationships": a.relationships, "events": a.events}, "load": load, "queries_ms": q,
              "machine": {"cpus": os.cpu_count(), "postgres": "16 + PostGIS 3.4 (default config)"}}
    Path(a.out).mkdir(parents=True, exist_ok=True)
    tag = "quick" if a.quick else f"{a.entities // 1000}k_{a.relationships // 1000}k"
    (Path(a.out) / f"benchmark_{tag}.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if not a.keep:
        ensure_db(a.admin_url, db_name)  # recreate empty to free disk


if __name__ == "__main__":
    main()
