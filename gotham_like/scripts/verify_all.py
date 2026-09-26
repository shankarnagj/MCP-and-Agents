#!/usr/bin/env python3
"""Run every verification step and print the PLATFORM VERIFICATION summary.

Steps: synthetic data generation · backend pytest (unit, integration incl. migrations, security,
performance incl. large generated graph) · frontend typecheck, unit tests, production build ·
frontend↔backend browser E2E · quick graph/geospatial benchmark.

Each area's PASS/FAIL is computed from the JUnit results of the tests that exercise it.

    python scripts/verify_all.py            # everything
    python scripts/verify_all.py --no-e2e   # skip the browser test (no Chromium available)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable

AREAS: dict[str, callable] = {
    "Ontology": lambda f, n: "test_ontology" in f,
    "Entity Resolution": lambda f, n: "test_entity_resolution" in f or any(k in n for k in ("entity_resolution", "lookalikes", "unmerge", "er_rerun", "merged_entity")),
    "Graph": lambda f, n: "test_graph_algorithms" in f or any(k in n for k in ("hop", "path", "analytics", "expansion", "cycle", "supply_chain")),
    "Search": lambda f, n: "test_search_parser" in f or "search" in n,
    "Timeline": lambda f, n: "timeline" in n,
    "Geospatial": lambda f, n: "test_api_spatiotemporal" in f and "timeline" not in n,
    "Provenance": lambda f, n: "provenance" in n or "lineage" in n,
    "Investigation Workspace": lambda f, n: "test_workspace" in f,
    "RBAC": lambda f, n: "test_rbac" in f or "rbac" in n,
    "Audit Logging": lambda f, n: "audit" in n or "audited" in n,
    "Security": lambda f, n: "/security/" in f or "test_security_primitives" in f,
    "Database": lambda f, n: "test_migrations" in f or "test_ingestion_er_provenance" in f,
}


def run(cmd: list[str], cwd: Path, env: dict | None = None, timeout: int = 3600) -> tuple[bool, str]:
    t = time.time()
    p = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, timeout=timeout)
    out = (p.stdout + p.stderr)[-4000:]
    print(f"  {'ok  ' if p.returncode == 0 else 'FAIL'} {' '.join(cmd)[:110]} ({time.time() - t:.0f}s)", flush=True)
    return p.returncode == 0, out


def parse_junit(path: Path) -> list[tuple[str, str, bool]]:
    cases = []
    for tc in ET.parse(path).getroot().iter("testcase"):
        f = (tc.get("file") or tc.get("classname", "").replace(".", "/"))
        ok = not any(tc.find(t) is not None for t in ("failure", "error"))
        skipped = tc.find("skipped") is not None
        if not skipped:
            cases.append((f, tc.get("name", ""), ok))
    return cases


def wait_for(url: str, seconds: int = 30) -> bool:
    for _ in range(seconds * 2):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-e2e", action="store_true")
    ap.add_argument("--skip-slow", action="store_true")
    a = ap.parse_args()
    results: dict[str, bool] = {}
    details: dict[str, str] = {}

    print("1. Synthetic data generation")
    with tempfile.TemporaryDirectory() as td:
        ok, out = run([PY, "scripts/generate_synthetic.py", "--out", td], ROOT)
        counts = json.loads(out[out.index("{"):]) if ok else {}
        expect = {"persons": 1000, "organizations": 200, "accounts": 2000, "devices": 1000, "transactions": 10000, "locations": 500, "events": 5000}
        gen_ok = ok and all(counts.get(k) == v for k, v in expect.items())
        # determinism: same seed → identical files as committed
        same = gen_ok and all((Path(td) / f).read_bytes() == (ROOT / "data" / "synthetic" / f).read_bytes()
                              for f in ("persons_crm.csv", "accounts.csv", "events.jsonl"))
    results["Synthetic Data"] = gen_ok and same
    details["Synthetic Data"] = f"counts={counts} deterministic={same}"

    print("2. Backend test suite (unit · integration · migrations · security · performance)")
    junit = Path(tempfile.gettempdir()) / "tessera-junit.xml"
    env = {"TESSERA_SKIP_SLOW": "1"} if a.skip_slow else {}
    ok, out = run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"], BACKEND, env, timeout=5400)
    cases = parse_junit(junit) if junit.exists() else []
    results["Backend"] = ok and bool(cases)
    details["Backend"] = f"{sum(c[2] for c in cases)}/{len(cases)} tests passed"
    for area, pred in AREAS.items():
        sel = [c for c in cases if pred(c[0], c[1])]
        results[area] = bool(sel) and all(c[2] for c in sel)
        details[area] = f"{sum(c[2] for c in sel)}/{len(sel)} tests"
    perf = [c for c in cases if "/performance/" in c[0]]
    results["Performance"] = bool(perf) and all(c[2] for c in perf)
    details["Performance"] = f"{sum(c[2] for c in perf)}/{len(perf)} tests"
    if not ok:
        print(out)

    print("3. Frontend (typecheck · unit tests · production build)")
    npx = shutil.which("npx") or "npx"
    f1, o1 = run([npx, "tsc", "-b"], FRONTEND)
    f2, o2 = run([npx, "vitest", "run"], FRONTEND)
    f3, o3 = run([npx, "vite", "build"], FRONTEND)
    fe_ok = f1 and f2 and f3
    details["Frontend"] = "tsc ok" if f1 else o1[-300:]
    if f2:
        line = next((ln for ln in o2.splitlines() if "Tests" in ln and "passed" in ln), "")
        details["Frontend"] += f"; vitest {line.strip()}"

    if not a.no_e2e:
        print("4. Frontend ↔ backend E2E (Chromium)")
        procs = []
        try:
            env_srv = {**os.environ, "TESSERA_LOG_LEVEL": "WARNING"}
            if not wait_for("http://127.0.0.1:8000/health", 1):
                procs.append(subprocess.Popen([PY, "-m", "uvicorn", "app.main:app", "--port", "8000"], cwd=BACKEND, env=env_srv,
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True))
            if not wait_for("http://127.0.0.1:4173", 1):
                procs.append(subprocess.Popen([npx, "vite", "preview", "--port", "4173", "--host", "127.0.0.1"], cwd=FRONTEND,
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True))
            up = wait_for("http://127.0.0.1:8000/health") and wait_for("http://127.0.0.1:4173")
            e2e_ok, e2e_out = run(["node", "tests/e2e/smoke.mjs"], FRONTEND, timeout=600) if up else (False, "servers did not start")
            details["Frontend"] += "; e2e " + ("PASS" if e2e_ok else "FAIL")
            fe_ok = fe_ok and e2e_ok
            if not e2e_ok:
                print(e2e_out)
        finally:
            for p in procs:
                os.killpg(p.pid, signal.SIGTERM)
    results["Frontend"] = fe_ok

    print("5. Quick graph + geospatial benchmark")
    with tempfile.TemporaryDirectory() as td:
        bok, bout = run([PY, "scripts/benchmark.py", "--quick", "--out", td], ROOT, timeout=1800)
        bench = json.loads(Path(td, "benchmark_quick.json").read_text()) if bok else {}
    if bench:
        q = bench["queries_ms"]
        details["Performance"] += (f"; quick bench p95: 2-hop {q['expand_2hop_typical']['p95_ms']} ms, path {q['shortest_path_depth6']['p95_ms']} ms, "
                                   f"geo {q['geo_radius_2km_time_window']['p95_ms']} ms")
    results["Performance"] = results.get("Performance", False) and bok

    order = ["Backend", "Frontend", "Database", "Ontology", "Entity Resolution", "Graph", "Search", "Timeline", "Geospatial", "Provenance",
             "Investigation Workspace", "RBAC", "Audit Logging", "Security", "Performance"]
    print("\n============================\nPLATFORM VERIFICATION\n============================\n")
    for k in order:
        print(f"{k + ':':26s}{'PASS' if results.get(k) else 'FAIL'}   ({details.get(k, '')})")
    print(f"{'Synthetic Data:':26s}{'PASS' if results['Synthetic Data'] else 'FAIL'}   ({details['Synthetic Data']})")
    lines = ["# Verification", "", f"Latest run of `scripts/verify_all.py`: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}.", "",
             "```", "============================", "PLATFORM VERIFICATION", "============================", ""]
    lines += [f"{k + ':':26s}{'PASS' if results.get(k) else 'FAIL'}" for k in order] + ["```", "", "| Area | Evidence |", "|---|---|"]
    lines += [f"| {k} | {details.get(k, '')} |" for k in [*order, "Synthetic Data"]]
    lines += ["", "Steps executed: synthetic data generation (counts + byte-for-byte determinism) · backend pytest "
              "(unit, integration incl. migration upgrade/downgrade/parity, security, performance incl. a generated "
              "50k-entity / 250k-edge graph) · frontend `tsc`, Vitest, production build · Chromium E2E against the live API · "
              "quick graph + geospatial benchmark. Full-scale numbers: [BENCHMARKS.md](BENCHMARKS.md).", "",
              "Known limitations, technical debt, performance bottlenecks, security risks and recommended next steps: "
              "[LIMITATIONS.md](LIMITATIONS.md)."]
    (ROOT / "docs" / "VERIFICATION.md").write_text("\n".join(lines) + "\n")
    sys.exit(0 if all(results.get(k) for k in order) else 1)


if __name__ == "__main__":
    main()
