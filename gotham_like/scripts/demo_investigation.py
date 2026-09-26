#!/usr/bin/env python3
"""Reproducible demonstration investigation over the SYNTHETIC / DEMONSTRATION DATA.

Walks the 10 analyst steps through the public REST API and writes a transcript plus
the resulting report and exports to docs/examples/:

  1 search an entity · 2 open its profile · 3 expand the graph · 4 filter relationships
  5 open the timeline · 6 open the map · 7 inspect provenance · 8 create a hypothesis
  9 save the investigation · 10 export the report

    python scripts/demo_investigation.py                 # against http://127.0.0.1:8000
    python scripts/demo_investigation.py --in-process    # no server needed (uses TESSERA_DATABASE_URL)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "docs" / "examples"


class Demo:
    def __init__(self, client) -> None:  # noqa: ANN001
        self.c = client
        self.h: dict[str, str] = {}
        self.log: list[str] = ["# Demonstration investigation transcript", "",
                               "> All data is SYNTHETIC / DEMONSTRATION DATA. Outputs are decision support, not conclusions.", ""]

    def call(self, method: str, path: str, **kw):  # noqa: ANN201
        r = self.c.request(method, path, headers=self.h, **kw)
        if r.status_code >= 400:
            raise SystemExit(f"{method} {path} → {r.status_code}: {r.text[:300]}")
        return r

    def step(self, n: int, title: str, lines: list[str]) -> None:
        self.log += [f"## Step {n}. {title}", "", *lines, ""]
        print(f"[{n:2d}] {title}")

    def run(self, password: str) -> None:
        tok = self.c.post("/api/auth/login", json={"username": "investigator", "password": password}).json()["access_token"]
        self.h = {"Authorization": f"Bearer {tok}"}

        # 1. Search
        res = self.call("POST", "/api/search", json={"query": "device:DV-7F3A-SHARED"}).json()
        dev = res["results"][0]
        self.step(1, "Search an entity", [f"Query `device:DV-7F3A-SHARED` → {res['total_estimate']} match: **{dev['label']}** (`{dev['id']}`).",
                                          f"Match reasons: {', '.join(res['match_reasons'])}."])
        # 2. Profile
        prof = self.call("GET", f"/api/entities/{dev['id']}").json()
        sig = next(s for s in prof["signals"] if s["rule_id"] == "shared_device")
        self.step(2, "Open entity profile", [f"Type {prof['type']}, status {prof['epistemic_status']}, confidence {prof['confidence']}.",
                                             f"Relationship counts: {prof['degree']}.",
                                             f"{len(prof['signals'])} analytical signal(s) involve this device, e.g. *{sig['what']}*"])
        # 3. Expand graph
        g = self.call("POST", "/api/graph/subgraph", json={"seeds": [dev["id"]], "depth": 1, "fanout": 200}).json()
        by_type: dict[str, int] = {}
        for n in g["nodes"]:
            by_type[n["type"]] = by_type.get(n["type"], 0) + 1
        self.step(3, "Expand graph (1 hop)", [f"{len(g['nodes'])} nodes / {len(g['edges'])} edges; node types {by_type}; truncated={g['truncated']}."])
        # 4. Filter relationships: device usage in March 2026, then who owns those accounts (no time filter: accounts were opened earlier)
        f = self.call("POST", "/api/graph/subgraph", json={"seeds": [dev["id"]], "depth": 1, "fanout": 200,
                                                           "filters": {"relationship_types": ["USED"], "time_from": "2026-03-01T00:00:00Z",
                                                                       "time_to": "2026-03-31T23:59:59Z"}}).json()
        accounts = [n for n in f["nodes"] if n["type"] == "Account"]
        own = self.call("POST", "/api/graph/subgraph", json={"seeds": [a["id"] for a in accounts], "depth": 1,
                                                             "filters": {"relationship_types": ["OWNS"], "direction": "in"}}).json()
        owners = [n for n in own["nodes"] if n["type"] == "Person"]
        self.step(4, "Filter relationships", [f"USED edges in March 2026 only → {len(accounts)} accounts used the device.",
                                              f"Then OWNS (inbound, any time) → {len(owners)} distinct account owners (persons).",
                                              "Time filters apply to timestamped relationships, so ownership established earlier is queried separately."])
        # 5. Timeline
        tl = self.call("GET", "/api/timeline", params={"entity_id": dev["id"], "simultaneous_window_s": 180}).json()
        first = tl["events"][:5]
        self.step(5, "Open timeline", [f"{tl['total']} events between {tl['span']['from']} and {tl['span']['to']}; by type {tl['by_type']}.",
                                       f"{len(tl['simultaneous']['groups'])} group(s) of near-simultaneous events (≤180 s).", "",
                                       *[f"- {e['timestamp']} — {e['event_type']} (source `{e['source']}`)" for e in first]])
        # 6. Map
        geo_q = self.call("POST", "/api/geo/query", json={"lat": 51.45, "lon": 3.60, "radius_m": 2000, "time_from": "2026-03-01T00:00:00Z",
                                                           "time_to": "2026-03-31T23:59:59Z", "entity_types": ["Transaction"],
                                                           "related_to": [a["id"] for a in accounts], "relationship_types": ["INITIATED"],
                                                           "include": ["entities"]}).json()
        traj = self.call("GET", f"/api/geo/trajectory/{dev['id']}").json()
        self.step(6, "Open map", [f"{geo_q['counts']['entities']} transactions initiated by these accounts within 2 km of Harbor Plaza in March 2026.",
                                  f"Device trajectory: {len(traj['geometry']['coordinates'])} located events. ({traj['properties']['note']})"])
        # 7. Provenance
        rel = self.call("GET", f"/api/entities/{dev['id']}/relationships", params={"relationship_type": "USED", "direction": "in", "limit": 1}).json()["items"][0]
        prov = self.call("GET", f"/api/provenance/{rel['id']}").json()
        sr = prov["source_records"][0]
        self.step(7, "Inspect provenance (why does this relationship exist?)",
                  [prov["why"], "", f"- Source: {sr['source']['name']} (`{sr['source']['id']}`, {sr['source']['classification']})",
                   f"- Source record: `{sr['source_record_id']}` (hash `{sr['content_hash'][:16]}…`)", f"- Ingested: {sr['ingestion_timestamp']}",
                   f"- Transformation: {sr['transformation_version']}", f"- Confidence: {prov['object']['confidence']}",
                   f"- Analyst modifications: {len(prov.get('analyst_modifications') or [])}",
                   f"- Lineage: {' → '.join([prov['lineage_upstream']['edges'][0]['from'], prov['lineage_upstream']['edges'][0]['to']])}"])
        # 8. Hypothesis (+ investigation)
        inv = self.call("POST", "/api/investigations", json={
            "name": "Demo: accounts, devices, transactions and locations",
            "description": "Analyze relationships between accounts, devices, transactions and locations around device DV-7F3A-SHARED (synthetic data).",
            "scope": {"question": "Which entities connect to DV-7F3A-SHARED in March 2026, and how?", "time_window": ["2026-03-01", "2026-03-31"],
                      "area": "2 km around Harbor Plaza"}}).json()
        merchant = self.call("POST", "/api/search", json={"query": "account:ACC-9000001"}).json()["results"][0]
        ip = self.call("POST", "/api/search", json={"query": "ip:203.0.113.66"}).json()["results"][0]
        dom = self.call("POST", "/api/search", json={"query": "domain:update-portal.example"}).json()["results"][0]
        for e in [dev, merchant, ip, dom, *accounts[:7]]:
            self.call("POST", f"/api/investigations/{inv['id']}/items", json={"kind": "entity", "ref_id": e["id"], "title": f"{e['type']}: {e['label']}"})
        self.call("POST", f"/api/investigations/{inv['id']}/items", json={"kind": "relationship", "ref_id": rel["id"], "title": "USED edge (provenance checked)"})
        self.call("POST", f"/api/investigations/{inv['id']}/items", json={"kind": "signal", "ref_id": sig["id"], "title": "Shared device signal"})
        self.call("POST", f"/api/investigations/{inv['id']}/items", json={"kind": "citation", "title": f"Source record {sr['source_record_id']}",
                                                                           "content": {"source_record_id": sr["id"]}})
        self.call("POST", f"/api/investigations/{inv['id']}/items", json={"kind": "note", "title": "Alternative explanations to check",
                                                                           "content": {"text": "Household or kiosk device? Confirm with device inventory owner."}})
        hyp = self.call("POST", "/api/assertions", json={
            "statement": "The seven accounts that used DV-7F3A-SHARED may be operated by a common party.",
            "subject_ids": [dev["id"], *[a["id"] for a in accounts[:7]]], "investigation_id": inv["id"], "analyst_confidence": "LOW",
            "rationale": "Shared device within 30 days, shared IP 203.0.113.66, payments to the same merchant account. Alternatives not yet excluded.",
            "evidence_refs": [{"kind": "signal", "id": sig["id"]}, {"kind": "relationship", "id": rel["id"]}]}).json()
        self.step(8, "Create hypothesis", [f"Investigation `{inv['id']}` created; {len(accounts[:7]) + 4} entities pinned with provenance snapshots.",
                                           f"Assertion `{hyp['id']}` recorded as **{hyp['label']}** (epistemic status {hyp['epistemic_status']})."])
        # 9. Save
        pattern = {"nodes": [{"var": "p", "type": "Person"}, {"var": "a", "type": "Account"}, {"var": "d", "type": "Device"}],
                   "edges": [{"from": "p", "to": "a", "type": "OWNS"}, {"from": "a", "to": "d", "type": "USED", "time_from": "2026-03-01", "time_to": "2026-03-31"}],
                   "aggregate": {"group_by": "d", "count_distinct": "p", "op": ">", "value": 3}}
        sq = self.call("POST", "/api/saved-queries", json={"name": "Devices shared by >3 persons in March 2026", "query_kind": "pattern", "query": pattern,
                                                           "investigation_id": inv["id"]}).json()
        q = self.call("POST", f"/api/saved-queries/{sq['id']}/run").json()
        upd = self.call("PATCH", f"/api/investigations/{inv['id']}", json={"status": "ON_HOLD", "expected_version": self.call("GET", f"/api/investigations/{inv['id']}").json()["version"]}).json()
        self.step(9, "Save investigation", [f"Saved query `{sq['id']}` → {q['row_count']} device(s) shared by >3 persons "
                                            f"({', '.join(q['entities'][r['group']]['label'] + ' × ' + str(r['count']) for r in q['rows'])}).",
                                            f"Investigation saved at version {upd['version']} (status {upd['status']}); every change is in the audit log."])
        # 10. Export
        OUT.mkdir(parents=True, exist_ok=True)
        rep = self.call("GET", f"/api/investigations/{inv['id']}/report").json()
        (OUT / "investigation_report.json").write_text(json.dumps(rep, indent=1, default=str))
        (OUT / "investigation_report.md").write_text(self.call("GET", f"/api/investigations/{inv['id']}/report", params={"format": "markdown"}).text)
        (OUT / "investigation_report.pdf").write_bytes(self.call("GET", f"/api/investigations/{inv['id']}/report", params={"format": "pdf"}).content)
        for fmt, what, ext in (("csv", "entities", "entities.csv"), ("csv", "relationships", "relationships.csv"), ("graphml", "entities", "graphml"),
                               ("geojson", "entities", "geojson"), ("json", "entities", "json")):
            (OUT / f"investigation_export.{ext}").write_text(self.call("POST", "/api/export", json={"format": fmt, "investigation_id": inv["id"], "what": what}).text)
        self.step(10, "Export report", ["Report sections: " + ", ".join(rep["sections"]) + ".",
                                        "Files: `investigation_report.{md,pdf,json}`, `investigation_export.{entities.csv,relationships.csv,graphml,geojson,json}`."])
        self.log += ["---", "", "Limitations recorded in the report:", "", *[f"- {x}" for x in rep["sections"]["Limitations"]]]
        (OUT / "DEMO_TRANSCRIPT.md").write_text("\n".join(self.log) + "\n")
        print(f"Wrote {OUT}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--in-process", action="store_true")
    ap.add_argument("--password", default=os.environ.get("TESSERA_DEMO_PASSWORD", "Demo-Passw0rd!"))
    a = ap.parse_args()
    if a.in_process:
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            Demo(c).run(a.password)
    else:
        import httpx

        with httpx.Client(base_url=a.base_url, timeout=120) as c:
            Demo(c).run(a.password)


if __name__ == "__main__":
    main()
