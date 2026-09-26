"""Authorization boundaries: every protected endpoint × role."""

import pytest

GET, POST, PUT, PATCH = "GET", "POST", "PUT", "PATCH"
# (method, path, body, roles allowed)
MATRIX = [
    (GET, "/api/stats", None, {"admin", "investigator", "analyst", "viewer"}),
    (POST, "/api/search", {"query": "type:Vessel"}, {"admin", "investigator", "analyst", "viewer"}),
    (GET, "/api/audit", None, {"admin"}),
    (GET, "/api/audit/verify", None, {"admin"}),
    (GET, "/api/users", None, {"admin"}),
    (GET, "/api/system/errors", None, {"admin"}),
    (GET, "/api/privacy/retention", None, {"admin"}),
    (GET, "/api/privacy/deletion-requests", None, {"admin", "investigator"}),
    (POST, "/api/investigations", {"name": "rbac"}, {"admin", "investigator", "analyst"}),
    (POST, "/api/export", {"format": "json", "entity_ids": ["__ID__"]}, {"admin", "investigator", "analyst"}),
    (POST, "/api/resolution/compare", {"entity_a": "__ID__", "entity_b": "__ID__"}, {"admin", "investigator"}),
    (POST, "/api/sources", {"id": "rbac_src", "name": "x", "kind": "csv"}, {"admin"}),
    (PUT, "/api/ontology", {}, {"admin"}),
    (POST, "/api/rules/shared_ip/evaluate", None, {"admin", "investigator", "analyst"}),
    (POST, "/api/graph/subgraph", {"seeds": ["__ID__"], "depth": 1}, {"admin", "investigator", "analyst", "viewer"}),
]


@pytest.mark.parametrize("method,path,body,allowed", MATRIX, ids=[f"{m} {p}" for m, p, _, _ in MATRIX])
@pytest.mark.parametrize("role", ["admin", "investigator", "analyst", "viewer"])
def test_rbac(client, H, ids, method, path, body, allowed, role):
    if body is not None:
        import json

        body = json.loads(json.dumps(body).replace("__ID__", ids["harbor"]))
    r = client.request(method, path, json=body, headers=H[role])
    if role in allowed:
        assert r.status_code not in (401, 403), (role, r.status_code, r.text[:200])
    else:
        assert r.status_code == 403, (role, r.status_code)


def test_denials_are_audited(client, H):
    client.get("/api/audit", headers=H["viewer"])
    rows = client.get("/api/audit", params={"action": "access_denied", "username": "viewer"}, headers=H["admin"]).json()["items"]
    assert rows and rows[0]["details"]["permission"] == "audit:read"


def test_relationship_review_requires_investigator(client, H, ids):
    rel = client.get(f"/api/entities/{ids['shared_device']}/relationships", headers=H["analyst"]).json()["items"][0]["id"]
    body = {"action": "verify", "note": "checked against device logs"}
    assert client.post(f"/api/relationships/{rel}/review", json=body, headers=H["analyst"]).status_code == 403
    r = client.post(f"/api/relationships/{rel}/review", json=body, headers=H["investigator"]).json()
    assert r["epistemic_status"] == "VERIFIED" and r["analyst_modifications"][-1]["previous_status"] == "DERIVED"
    prov = client.get(f"/api/provenance/{rel}", headers=H["viewer"]).json()
    assert prov["analyst_modifications"][-1]["by"] == "investigator"


def test_non_collaborator_cannot_edit_investigation(client, H):
    inv = client.post("/api/investigations", json={"name": "private-ish"}, headers=H["analyst"]).json()
    tok = client.post("/api/users", json={"username": "analyst2", "password": "Other-Passw0rd-2", "role": "ANALYST"}, headers=H["admin"])
    assert tok.status_code in (201, 409)
    t2 = client.post("/api/auth/login", json={"username": "analyst2", "password": "Other-Passw0rd-2"}).json()["access_token"]
    h2 = {"Authorization": f"Bearer {t2}"}
    assert client.post(f"/api/investigations/{inv['id']}/items", json={"kind": "note", "title": "x"}, headers=h2).status_code == 403
    me2 = client.get("/api/auth/me", headers=h2).json()["id"]
    client.patch(f"/api/investigations/{inv['id']}", json={"collaborators": [me2]}, headers=H["analyst"])
    assert client.post(f"/api/investigations/{inv['id']}/items", json={"kind": "note", "title": "x"}, headers=h2).status_code == 201
