"""Investigations, evidence board, assertions, saved queries, query builder, reports, exports, rules, alerts, websockets."""

import csv
import io
import json
import xml.etree.ElementTree as ET

import networkx as nx
import pytest

VERDICT_WORDS = ("is fraudulent", "is guilty", "is a criminal", "confirmed fraud", "is malicious")


@pytest.fixture(scope="module")
def inv(client, H, ids):
    r = client.post("/api/investigations", json={"name": "Shared device analysis", "description": "Analyze relationships between accounts, devices, transactions and locations.",
                                                 "scope": {"time_window": ["2026-03-01", "2026-03-31"]}}, headers=H["analyst"])
    assert r.status_code == 201
    inv = r.json()
    for eid in (ids["shared_device"], ids["merchant_account"], ids["suspicious_ip"]):
        assert client.post(f"/api/investigations/{inv['id']}/items", json={"kind": "entity", "ref_id": eid, "title": eid}, headers=H["analyst"]).status_code == 201
    return inv


def test_investigation_lifecycle_and_versioning(client, H, inv):
    full = client.get(f"/api/investigations/{inv['id']}", headers=H["viewer"]).json()
    assert full["counts"]["entity"] == 3 and full["can_write"] is False
    v = full["version"]
    ok = client.patch(f"/api/investigations/{inv['id']}", json={"description": "updated", "expected_version": v}, headers=H["analyst"])
    assert ok.status_code == 200 and ok.json()["version"] == v + 1
    stale = client.patch(f"/api/investigations/{inv['id']}", json={"description": "stale", "expected_version": v}, headers=H["analyst"])
    assert stale.status_code == 409
    assert client.patch(f"/api/investigations/{inv['id']}", json={"description": "x"}, headers=H["viewer"]).status_code == 403


def test_evidence_board_items_keep_provenance(client, H, inv, ids):
    rel = client.get(f"/api/entities/{ids['shared_device']}/relationships", params={"relationship_type": "USED"}, headers=H["analyst"]).json()["items"][0]
    r = client.post(f"/api/investigations/{inv['id']}/items", json={"kind": "relationship", "ref_id": rel["id"], "title": "USED edge"}, headers=H["analyst"]).json()
    assert r["provenance"]["source_records"] == rel["source_records"] and r["provenance"]["pinned_by"] == "analyst"
    note = client.post(f"/api/investigations/{inv['id']}/items", json={"kind": "note", "title": "n", "content": {"text": "check device logs"}}, headers=H["analyst"]).json()
    assert note["epistemic_status"] == "ANALYST_ASSERTION"
    cit = client.post(f"/api/investigations/{inv['id']}/items", json={"kind": "citation", "title": "c", "content": {"source_record_id": rel["source_records"][0]}},
                      headers=H["analyst"]).json()
    assert cit["provenance"]["content_hash"]
    assert client.post(f"/api/investigations/{inv['id']}/items", json={"kind": "citation", "title": "c", "content": {}}, headers=H["analyst"]).status_code == 422
    assert client.post(f"/api/investigations/{inv['id']}/items", json={"kind": "entity", "ref_id": "nope"}, headers=H["analyst"]).status_code == 404
    assert client.post(f"/api/investigations/{inv['id']}/items", json={"kind": "virus"}, headers=H["analyst"]).status_code == 422
    doc = client.post(f"/api/investigations/{inv['id']}/documents", files={"file": ("memo.txt", b"synthetic memo", "text/plain")}, data={"title": "Memo"},
                      headers=H["analyst"])
    assert doc.status_code == 201 and len(doc.json()["content"]["sha256"]) == 64
    exe = client.post(f"/api/investigations/{inv['id']}/documents", files={"file": ("x.exe", b"MZ", "application/x-msdownload")}, headers=H["analyst"])
    assert exe.status_code == 422
    assert client.delete(f"/api/investigations/{inv['id']}/items/{note['id']}", headers=H["analyst"]).status_code == 204


def test_assertions_are_hypotheses_never_facts(client, H, inv, ids, db):
    r = client.post("/api/assertions", json={"statement": "Entity A may be associated with Entity B.", "subject_ids": [ids["shared_device"], ids["merchant_account"]],
                                             "investigation_id": inv["id"], "analyst_confidence": "LOW"}, headers=H["analyst"])
    assert r.status_code == 201
    a = r.json()
    assert a["status"] == "HYPOTHESIS" and a["epistemic_status"] == "ANALYST_ASSERTION" and "HYPOTHESIS" in a["label"]
    upd = client.patch(f"/api/assertions/{a['id']}", json={"status": "SUPPORTED", "note": "more evidence"}, headers=H["analyst"]).json()
    assert upd["epistemic_status"] == "ANALYST_ASSERTION" and len(upd["history"]) == 2  # never promoted to a source fact
    assert client.patch(f"/api/assertions/{a['id']}", json={"status": "VERIFIED", "note": "x"}, headers=H["analyst"]).status_code == 422
    assert client.post("/api/assertions", json={"statement": "x is bad", "subject_ids": ["missing"]}, headers=H["analyst"]).status_code == 404
    assert client.post("/api/assertions", json={"statement": "hello world", "subject_ids": [ids["shared_device"]]}, headers=H["viewer"]).status_code == 403
    # assertions never alter source-derived records
    from app.models import Relationship
    from sqlalchemy import func, select

    assert db.scalar(select(func.count()).where(Relationship.epistemic_status == "ANALYST_ASSERTION")) == 0


def test_pattern_query_and_saved_queries(client, H, ids, inv):
    pattern = {"nodes": [{"var": "p", "type": "Person"}, {"var": "a", "type": "Account"}, {"var": "d", "type": "Device"}],
               "edges": [{"from": "p", "to": "a", "type": "OWNS"}, {"from": "a", "to": "d", "type": "USED", "time_from": "2026-03-01", "time_to": "2026-03-31"}],
               "aggregate": {"group_by": "d", "count_distinct": "p", "op": ">", "value": 3}}
    r = client.post("/api/query", json={"pattern": pattern, "explain": True}, headers=H["analyst"]).json()
    assert [row["group"] for row in r["rows"]] == [ids["shared_device"]] and r["rows"][0]["count"] == 7
    assert [s["step"] for s in r["plan"]] == ["scan", "scan", "scan", "join", "join", "aggregate"]
    assert r["database_plan"] and "%(" in r["sql"]  # parameterised
    s = client.post("/api/saved-queries", json={"name": "Shared devices", "query_kind": "pattern", "query": pattern, "investigation_id": inv["id"]},
                    headers=H["analyst"]).json()
    rerun = client.post(f"/api/saved-queries/{s['id']}/run", headers=H["viewer"]).json()
    assert rerun["rows"][0]["count"] == 7 and rerun["saved_query"]["created_by"]
    filt = {"nodes": [{"var": "t", "type": "Transaction", "filters": [{"property": "amount", "op": ">=", "value": 9000}]}, {"var": "a", "type": "Account"}],
            "edges": [{"from": "t", "to": "a", "type": "TRANSFERRED_TO"}], "limit": 500}
    rows = client.post("/api/query", json={"pattern": filt}, headers=H["analyst"]).json()["rows"]
    assert any(row["a"] == ids["aml_account"] for row in rows)


@pytest.mark.parametrize("bad", [
    {"nodes": [{"var": "a", "type": "Nope"}]},
    {"nodes": [{"var": "a", "type": "Account", "filters": [{"property": "nope", "value": 1}]}]},
    {"nodes": [{"var": "a", "type": "Account"}], "edges": [{"from": "a", "to": "z"}]},
    {"nodes": [{"var": "A;drop", "type": "Account"}]},
    {"nodes": [{"var": "a", "type": "Account"}, {"var": "b", "type": "Device"}], "edges": [{"from": "b", "to": "a", "type": "OWNS"}]},
])
def test_pattern_query_validation(client, H, bad):
    assert client.post("/api/query", json={"pattern": bad}, headers=H["analyst"]).status_code == 422


def test_report_sections_and_formats(client, H, inv):
    rep = client.get(f"/api/investigations/{inv['id']}/report", headers=H["analyst"]).json()
    assert list(rep["sections"]) == ["Investigation Summary", "Scope", "Entities", "Relationships", "Timeline", "Geographic Findings", "Analytical Signals",
                                     "Evidence", "Analyst Assertions", "Data Sources", "Limitations"]
    assert rep["classification_banner"] == "SYNTHETIC / DEMONSTRATION DATA"
    assert rep["sections"]["Analytical Signals"]["items"] and all(s["alternative_explanations"] for s in rep["sections"]["Analytical Signals"]["items"])
    assert rep["sections"]["Data Sources"] and rep["sections"]["Limitations"]
    text = json.dumps(rep).lower()
    assert not any(w in text for w in VERDICT_WORDS)
    md = client.get(f"/api/investigations/{inv['id']}/report", params={"format": "markdown"}, headers=H["analyst"]).text
    assert md.startswith("# Investigation Report") and "## Limitations" in md
    pdf = client.get(f"/api/investigations/{inv['id']}/report", params={"format": "pdf"}, headers=H["analyst"])
    assert pdf.content[:4] == b"%PDF" and len(pdf.content) > 3000
    assert client.get(f"/api/investigations/{inv['id']}/report", headers=H["viewer"]).status_code == 403


def test_exports_carry_provenance(client, H, inv, ids):
    j = client.post("/api/export", json={"format": "json", "investigation_id": inv["id"]}, headers=H["analyst"]).json()
    assert j["metadata"]["sources"] and j["metadata"]["transformation_versions"] and j["metadata"]["exported_by"] == "analyst"
    assert all("source_ids" in e and "epistemic_status" in e for e in j["entities"])
    c = client.post("/api/export", json={"format": "csv", "investigation_id": inv["id"], "what": "relationships"}, headers=H["analyst"]).text
    meta = [ln for ln in c.splitlines() if ln.startswith("#")]
    assert any("sources" in ln for ln in meta)
    rows = list(csv.DictReader(io.StringIO("\n".join(ln for ln in c.splitlines() if not ln.startswith("#")))))
    assert rows and all(r["source_records"] and r["epistemic_status"] for r in rows)
    g = client.post("/api/export", json={"format": "graphml", "entity_ids": [ids["shared_device"], ids["suspicious_ip"]]}, headers=H["analyst"]).text
    graph = nx.read_graphml(io.StringIO(g))
    assert graph.number_of_nodes() == 2 and "sources" in graph.graph
    assert all("source_records" in d for _, _, d in graph.edges(data=True))
    ET.fromstring(g)
    gj = client.post("/api/export", json={"format": "geojson", "entity_ids": [ids["harbor"]]}, headers=H["analyst"]).json()
    assert gj["type"] == "FeatureCollection" and gj["metadata"]["sources"] and gj["features"]
    assert client.post("/api/export", json={"format": "json", "entity_ids": [ids["harbor"]]}, headers=H["viewer"]).status_code == 403


def test_signals_explainability(client, H):
    sigs = client.get("/api/signals", params={"rule_id": "shared_device"}, headers=H["viewer"]).json()["items"]
    assert len(sigs) == 1
    x = sigs[0]["explanation"]
    for key in ("what_happened", "why_shown", "supporting_data", "data_collected", "assumptions", "uncertain", "alternative_explanations", "time_window",
                "score_meaning"):
        assert x[key], key
    assert x["label"] == "ANALYTICAL SIGNAL" and "7 distinct Account" in x["what_happened"]
    assert x["supporting_data"]["source_records_total"] >= 7
    assert sigs[0]["epistemic_status"] == "SYSTEM_INFERENCE"


def test_planted_scenarios_produce_signals(seeded):
    rules = seeded["rules"]
    assert rules["shared_device"]["new_signals"] == 1
    assert rules["suspicious_domain_dns"]["new_signals"] == 7
    assert rules["inbound_burst"]["new_signals"] >= 2
    assert rules["circular_flow"]["new_signals"] >= 1
    assert rules["auth_failure_then_login"]["new_signals"] >= 7
    assert rules["harbor_geofence"]["new_signals"] >= 1


def test_alerts_lifecycle_and_audit(client, H):
    alerts = client.get("/api/alerts", params={"status": "OPEN"}, headers=H["viewer"]).json()
    a = alerts["items"][0]
    assert a["summary"].startswith("ANALYTICAL SIGNAL detected")
    assert not any(w in a["summary"].lower() for w in VERDICT_WORDS)
    assert client.patch(f"/api/alerts/{a['id']}", json={"status": "ACKNOWLEDGED"}, headers=H["viewer"]).status_code == 403
    r = client.patch(f"/api/alerts/{a['id']}", json={"status": "ACKNOWLEDGED", "note": "looking"}, headers=H["analyst"])
    assert r.json()["status"] == "ACKNOWLEDGED"
    audit = client.get("/api/audit", params={"action": "alert_update", "object_id": a["id"]}, headers=H["admin"]).json()["items"]
    assert audit[0]["previous_value"]["status"] == "OPEN" and audit[0]["new_value"]["status"] == "ACKNOWLEDGED"


def test_rule_management_and_reevaluation_is_idempotent(client, H):
    rid = "test_big_inbound"
    body = {"id": rid, "name": "Many inbound transfers (test)", "kind": "unusual_count", "severity": "LOW",
            "definition": {"entity_type": "Account", "path": ["TRANSFERRED_TO"], "direction": "in", "window_days": 7, "min_count": 8, "percentile": 0.99, "alert": False}}
    assert client.put(f"/api/rules/{rid}", json=body, headers=H["analyst"]).status_code == 403
    assert client.put(f"/api/rules/{rid}", json=body, headers=H["admin"]).status_code == 200
    first = client.post(f"/api/rules/{rid}/evaluate", headers=H["analyst"]).json()
    second = client.post(f"/api/rules/{rid}/evaluate", headers=H["analyst"]).json()
    assert first["new_signals"] and second["new_signals"] == []
    verdict = {**body, "id": "bad_rule", "name": "Fraudster finder"}
    assert client.put("/api/rules/bad_rule", json=verdict, headers=H["admin"]).status_code == 422


def test_new_relationship_and_source_change_alerts(db, tmp_path):
    from app.config import get_settings
    from app.ingestion.csv import CSVConnector
    from app.ingestion.mapping import load_mappings
    from app.ingestion.pipeline import ensure_source, run_ingestion
    from app.ontology import get_ontology
    from app.rules import engine

    maps = load_mappings(get_settings().ontology_path.parent / "mappings.json")
    src = ensure_source(db, "test_ubo_update", "UBO update (test)", "csv")
    p = tmp_path / "c.csv"
    p.write_text("controller_type,controller_id,controlled_id,share_pct,since\nPerson,P-00042,ORG-0010,51,2026-06-01T00:00:00Z\n")
    res = run_ingestion(db, get_ontology(), src, CSVConnector(p, "control"), maps["control"])
    p.write_text("controller_type,controller_id,controlled_id,share_pct,since\nPerson,P-00042,ORG-0010,75,2026-06-01T00:00:00Z\n")
    CSVConnector(p, "control")
    out = engine.evaluate_all(db, ctx={"new_relationship_ids": res.new_relationship_ids, "changed_record_ids": []}, kinds={"new_relationship"})
    assert out[0]["new_alerts"] and "New CONTROLS relationship" in out[0]["new_alerts"][0].summary
    src2 = ensure_source(db, "test_changes", "changes", "jsonl")
    q = tmp_path / "k.jsonl"
    q.write_text('{"kyc_id":"CH-1","name":"Relo Tamsin"}\n')
    maps_k = maps["person_kyc"]
    from app.ingestion.json import JSONLConnector

    run_ingestion(db, get_ontology(), src2, JSONLConnector(q, "person_kyc", "kyc_id"), maps_k)
    q.write_text('{"kyc_id":"CH-1","name":"Relo Tamsin-Orr"}\n')
    r2 = run_ingestion(db, get_ontology(), src2, JSONLConnector(q, "person_kyc", "kyc_id"), maps_k)
    out2 = engine.evaluate_all(db, ctx={"new_relationship_ids": [], "changed_record_ids": r2.changed_record_ids}, kinds={"source_change"})
    assert out2[0]["new_alerts"] and "changed on re-ingestion" in out2[0]["new_alerts"][0].summary
    db.rollback()


def test_websocket_requires_auth_and_delivers_alerts(client, tokens):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": "bogus"}))
        with pytest.raises(Exception):
            ws.receive_text()
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": tokens["analyst"]}))
        assert json.loads(ws.receive_text())["event"] == "ready"
        ws.send_text(json.dumps({"type": "subscribe", "topic": "progress"}))
        assert json.loads(ws.receive_text())["event"] == "subscribed"
        ws.send_text(json.dumps({"type": "ping"}))
        assert json.loads(ws.receive_text())["event"] == "pong"
        r = client.post("/api/rules/shared_ip/evaluate", headers={"Authorization": f"Bearer {tokens['analyst']}"})
        assert r.status_code == 200
        msg = json.loads(ws.receive_text())
        assert msg["topic"] == "progress" and msg["event"] == "rule.started"


def test_collaborative_investigation_updates_broadcast(client, H, inv):
    from app.services.realtime import hub

    before = len(hub.published)
    client.post(f"/api/investigations/{inv['id']}/items", json={"kind": "note", "title": "collab", "content": {"text": "hi"}}, headers=H["investigator"])
    msgs = [m for m in hub.published[before - 200 if before > 200 else 0:] if m["topic"] == f"investigation:{inv['id']}"]
    assert msgs and msgs[-1]["event"] == "item.added" and msgs[-1]["payload"]["by"] == "investigator"
