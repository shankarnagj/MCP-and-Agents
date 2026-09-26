"""Search, entities, graph traversal, path finding, analytics."""

import pytest


def search(client, H, q, role="analyst", **kw):
    r = client.post("/api/search", json={"query": q, **kw}, headers=H[role])
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("q,type_,label", [
    ("device:DV-7F3A-SHARED", "Device", "DV-7F3A-SHARED"),
    ("ip:203.0.113.66", "IPAddress", "203.0.113.66"),
    ("account:ACC-9000001", "Account", None),
    ('"Harbor Plaza"', "Location", "Harbor Plaza"),
    ("company:Northwind Quartz", "Organization", "Northwind Quartz Trading Ltd"),
    ("domain:update-portal.example", "Domain", "update-portal.example"),
    ("shipment:SHP-000042", "Shipment", "SHP-000042"),
])
def test_search_modes(client, H, q, type_, label):
    res = search(client, H, q)
    top = res["results"][0]
    assert top["type"] == type_
    if label:
        assert top["label"] == label
    assert res["match_reasons"]


def test_fuzzy_prefix_and_typo_tolerance(client, H):
    exact = search(client, H, '"Zusil Lobetul"')["results"]
    assert exact and exact[0]["label"] == "Zusil Lobetul"
    assert any(r["label"] == "Zusil Lobetul" for r in search(client, H, "~Zusl Lobetul")["results"])
    pref = search(client, H, "Zusil*")["results"]
    assert pref and all("zusil" in r["label"].lower() for r in pref)


def test_type_date_geo_filters(client, H):
    r = search(client, H, "type:Transaction near:51.45,3.60,2km on:2026-02-14", limit=200)
    assert r["total_estimate"] >= 25 and all(x["type"] == "Transaction" for x in r["results"])
    assert all(x["observed_at"].startswith("2026-02-14") for x in r["results"])
    r2 = search(client, H, "type:Location bbox:3.5,51.4,3.7,51.5")
    assert any(x["label"] == "Harbor Plaza" for x in r2["results"])
    assert search(client, H, 'jurisdiction:"Castellan Isles" type:Organization')["total_estimate"] >= 3
    none = search(client, H, "type:Organization -type:Organization Northwind")
    assert none["results"] == []


def test_search_pagination_and_facets(client, H):
    a = search(client, H, "type:Location", limit=10)
    b = search(client, H, "type:Location", limit=10, offset=10)
    assert a["facets"]["type"] == {"Location": 500}
    assert not {x["id"] for x in a["results"]} & {x["id"] for x in b["results"]}


def test_search_errors(client, H):
    assert client.post("/api/search", json={"query": "type:Starship"}, headers=H["analyst"]).status_code == 422
    assert client.post("/api/search", json={"query": ""}, headers=H["analyst"]).status_code == 422


def test_entity_profile_and_relationships(client, H, ids):
    e = client.get(f"/api/entities/{ids['shared_device']}", headers=H["analyst"]).json()
    assert e["type"] == "Device" and e["degree"]["USED"] >= 7 and e["signals"]
    rels = client.get(f"/api/entities/{ids['shared_device']}/relationships", params={"relationship_type": "USED", "direction": "in", "limit": 5},
                      headers=H["analyst"]).json()
    assert rels["total"] >= 7 and len(rels["items"]) == 5 and all(r["relationship_type"] == "USED" for r in rels["items"])
    page = client.get("/api/entities", params={"type": "Vessel", "limit": 5}, headers=H["viewer"]).json()
    assert page["total"] == 20 and len(page["items"]) == 5


def test_merged_entity_redirects(client, H, db):
    from sqlalchemy import select

    from app.models import Entity

    dup = db.scalars(select(Entity).where(Entity.merged_into.is_not(None))).first()
    r = client.get(f"/api/entities/{dup.id}", headers=H["analyst"]).json()
    assert r["redirected_from"] == dup.id and r["id"] == dup.merged_into


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_n_hop_expansion(client, H, ids, depth):
    r = client.post("/api/graph/subgraph", json={"seeds": [ids["shared_device"]], "depth": depth, "max_nodes": 800, "fanout": 50},
                    headers=H["analyst"]).json()
    assert max(n["hop"] for n in r["nodes"]) <= depth
    assert len(r["hops"]) <= depth
    ids_ = {n["id"] for n in r["nodes"]}
    assert all(e["source"] in ids_ and e["target"] in ids_ for e in r["edges"])


def test_expansion_filters_and_limits(client, H, ids):
    r = client.post("/api/graph/subgraph", json={"seeds": [ids["shared_device"]], "depth": 1, "filters": {"relationship_types": ["USED"], "direction": "in"}},
                    headers=H["analyst"]).json()
    assert {e["relationship_type"] for e in r["edges"]} == {"USED"}
    assert {n["type"] for n in r["nodes"] if n["hop"] == 1} == {"Account"}
    t = client.post("/api/graph/subgraph", json={"seeds": [ids["harbor"]], "depth": 2, "max_nodes": 50, "fanout": 10}, headers=H["analyst"]).json()
    assert t["truncated"] and len(t["nodes"]) <= 50 and t["truncation_reasons"]
    w = client.post("/api/graph/subgraph", json={"seeds": [ids["shared_device"]], "depth": 1,
                                                 "filters": {"time_from": "2026-03-01T00:00:00Z", "time_to": "2026-03-10T00:00:00Z"}}, headers=H["analyst"]).json()
    assert all(e["timestamp"] is None or "2026-03-01" <= e["timestamp"][:10] <= "2026-03-10" for e in w["edges"])
    assert client.post("/api/graph/subgraph", json={"seeds": ["x"], "depth": 9}, headers=H["analyst"]).status_code == 422
    assert client.post("/api/graph/subgraph", json={"seeds": ["x"], "filters": {"relationship_types": ["NOPE"]}}, headers=H["analyst"]).status_code == 422


def test_paths_between_person_and_company(client, H, ids):
    """AML chain: Person P-00007 → CONTROLS → ORG-0001 → CONTROLS → ORG-0002 → CONTROLS → ORG-0000."""
    body = {"source": ids["aml_person"], "target": ids["merchant_org"], "relationship_types": ["CONTROLS"], "respect_direction": True, "max_depth": 5}
    r = client.post("/api/graph/path", json=body, headers=H["analyst"]).json()
    assert r["found"]
    p = r["paths"][0]
    assert [s["relationship_type"] for s in p["steps"]] == ["CONTROLS"] * 3
    assert all(s["source_records"] and s["provenance"] for s in p["steps"])  # every edge carries provenance
    assert "connectivity, not intent" in " ".join(r["explanation"]["assumptions"])


def test_path_modes(client, H, ids):
    base = {"source": ids["shared_device"], "target": ids["merchant_org"], "max_depth": 6}
    s = client.post("/api/graph/path", json={**base, "mode": "shortest"}, headers=H["analyst"]).json()
    a = client.post("/api/graph/path", json={**base, "mode": "all_simple", "max_paths": 5}, headers=H["analyst"]).json()
    w = client.post("/api/graph/path", json={**base, "mode": "weighted"}, headers=H["analyst"]).json()
    c = client.post("/api/graph/path", json={**base, "mode": "shortest", "relationship_types": ["USED", "INITIATED", "TRANSFERRED_TO", "OWNS"]},
                    headers=H["analyst"]).json()
    assert s["found"] and a["found"] and w["found"] and c["found"]
    assert len(a["paths"]) >= 1 and all(p["length"] <= 6 for p in a["paths"])
    types = [st["relationship_type"] for st in c["paths"][0]["steps"]]
    assert types == ["USED", "INITIATED", "TRANSFERRED_TO", "OWNS"]  # Device ← Account → Txn → Merchant account ← Org
    assert s["paths"][0]["length"] <= c["paths"][0]["length"]


def test_supply_chain_trace(client, H, ids):
    r = client.get(f"/api/entities/{ids['shipment']}/relationships", headers=H["analyst"]).json()
    types = {x["relationship_type"] for x in r["items"]}
    assert {"SHIPPED_BY", "CARRIED_BY", "PASSED_THROUGH", "SHIPPED_TO"} <= types
    p = client.post("/api/graph/path", json={"source": ids["supplier"], "target": ids["customer"], "max_depth": 2,
                                              "relationship_types": ["SHIPPED_BY", "SHIPPED_TO"]}, headers=H["analyst"]).json()
    assert p["found"]


def test_graph_analytics_signal_labelling(client, H, ids):
    r = client.post("/api/graph/analytics", json={"seeds": [ids["shared_device"]], "depth": 2,
                                                   "algorithms": ["degree_centrality", "betweenness_centrality", "pagerank", "connected_components",
                                                                  "strongly_connected_components", "communities", "k_core", "cycles"]},
                    headers=H["analyst"]).json()
    assert r["label"] == "ANALYTICAL SIGNAL" and "does not establish" in r["caveat"]
    scores = [x["score"] for x in r["results"]["degree_centrality"]["top"]]
    assert scores == sorted(scores, reverse=True)  # at depth 2 busy hubs (accounts, locations) legitimately outrank the seed
    star = client.post("/api/graph/analytics", json={"seeds": [ids["shared_device"]], "depth": 1, "algorithms": ["degree_centrality"]},
                       headers=H["analyst"]).json()
    assert star["results"]["degree_centrality"]["top"][0]["id"] == ids["shared_device"]
    assert r["window"]["nodes"] > 10
    assert client.post("/api/graph/analytics", json={"seeds": ["a"], "algorithms": ["tarot"]}, headers=H["analyst"]).status_code == 422


def test_circular_flow_detected_by_cycle_algorithm(client, H, db):
    from sqlalchemy import select

    from app.models import Signal

    sig = db.scalars(select(Signal).where(Signal.rule_id == "circular_flow")).first()
    assert sig and len(sig.evidence) >= 3
