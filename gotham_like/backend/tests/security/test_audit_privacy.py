"""Audit log integrity and privacy controls."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.audit.service import verify_chain
from app.models import AuditLog


def test_expected_actions_are_audited(client, H, ids):
    client.post("/api/search", json={"query": "type:Vessel"}, headers=H["analyst"])
    client.get(f"/api/entities/{ids['harbor']}", headers=H["analyst"])
    client.post("/api/graph/subgraph", json={"seeds": [ids["harbor"]], "depth": 1}, headers=H["analyst"])
    client.post("/api/export", json={"format": "json", "entity_ids": [ids["harbor"]]}, headers=H["analyst"])
    client.post("/api/query", json={"pattern": {"nodes": [{"var": "v", "type": "Vessel"}]}}, headers=H["analyst"])
    actions = {a["action"] for a in client.get("/api/audit", params={"username": "analyst", "limit": 1000}, headers=H["admin"]).json()["items"]}
    assert {"login", "search", "entity_view", "graph_operation", "data_export", "query"} <= actions
    row = client.get("/api/audit", params={"action": "entity_view", "username": "analyst"}, headers=H["admin"]).json()["items"][0]
    assert row["user"] == "analyst" and row["ts"] and row["object"] and row["request_id"] and row["hash"]


def test_audit_log_is_append_only(db):
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE audit_log SET action = 'x' WHERE id = (SELECT min(id) FROM audit_log)"))
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM audit_log"))
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("TRUNCATE audit_log"))
    db.rollback()


def test_hash_chain_detects_tampering(db, client, H):
    assert client.get("/api/audit/verify", headers=H["admin"]).json()["valid"] is True
    target = db.scalar(select(AuditLog.id).order_by(AuditLog.id).offset(3).limit(1))
    # simulate an out-of-band DBA edit that bypasses the trigger
    db.execute(text("SET session_replication_role = replica"))
    db.execute(text("UPDATE audit_log SET username = 'mallory' WHERE id = :i"), {"i": target})
    res = verify_chain(db)
    db.rollback()
    assert res["valid"] is False and res["broken_at"] == target
    assert verify_chain(db)["valid"] is True


def test_field_level_masking_via_api(client, H, ids):
    person = client.post("/api/search", json={"query": "type:Person Zusil*"}, headers=H["investigator"]).json()["results"][0]["id"]
    v = client.get(f"/api/entities/{person}", headers=H["viewer"]).json()
    a = client.get(f"/api/entities/{person}", headers=H["analyst"]).json()
    i = client.get(f"/api/entities/{person}", headers=H["investigator"]).json()
    assert "email" in v["masked_fields"] and "***@" in v["properties"]["email"] and "*" in v["label"]
    assert "@example.com" in a["properties"]["email"] and a["properties"]["date_of_birth"] == "[RESTRICTED]"
    assert i["masked_fields"] == [] and "-" in i["properties"]["date_of_birth"]
    # masking also applies to search results, graph views and exports
    sv = client.post("/api/search", json={"query": "Zusil*"}, headers=H["viewer"]).json()["results"]
    assert all("*" in r["label"] for r in sv if r["type"] == "Person")
    g = client.post("/api/graph/subgraph", json={"seeds": [person], "depth": 0}, headers=H["viewer"]).json()
    assert "*" in g["nodes"][0]["label"]


def test_viewer_cannot_filter_on_protected_fields(client, H):
    r = client.post("/api/search", json={"query": "type:Person email:zusil*"}, headers=H["viewer"])
    assert r.status_code == 200
    r2 = client.post("/api/search", json={"query": "type:Person nationality:Aldoria date_of_birth:1961*"}, headers=H["analyst"]).json()
    assert any("protected" in w for w in r2["parsed"]["warnings"])
    q = client.post("/api/query", json={"pattern": {"nodes": [{"var": "p", "type": "Person", "filters": [{"property": "email", "value": "x"}]}]}},
                    headers=H["viewer"])
    assert q.status_code == 403


def test_pii_access_is_logged(client, H, ids):
    person = client.post("/api/search", json={"query": "type:Person Zusil*"}, headers=H["investigator"]).json()["results"][0]["id"]
    client.get(f"/api/entities/{person}", headers=H["investigator"])
    rows = client.get("/api/audit", params={"action": "pii_access", "object_id": person}, headers=H["admin"]).json()["items"]
    assert rows and "email" in rows[0]["details"]["fields"]


def test_deletion_workflow_four_eyes(client, H, db):
    from app.auth.security import hash_password
    from app.models import User, new_id

    person = client.post("/api/search", json={"query": "type:Person Sidor*"}, headers=H["investigator"]).json()["results"][0]["id"]
    body = {"entity_id": person, "reason": "Data subject erasure request (synthetic test)", "legal_basis": "GDPR Art. 17 (test)"}
    assert client.post("/api/privacy/deletion-requests", json=body, headers=H["analyst"]).status_code == 403
    req = client.post("/api/privacy/deletion-requests", json=body, headers=H["investigator"]).json()
    assert req["status"] == "PENDING"
    # requester != approver: create a second admin to approve
    if not db.scalar(select(User).where(User.username == "admin2")):
        db.add(User(id=new_id("usr"), username="admin2", password_hash=hash_password("Admin2-Passw0rd!", rounds=4), role="ADMIN"))
        db.commit()
    t = client.post("/api/auth/login", json={"username": "admin2", "password": "Admin2-Passw0rd!"}).json()["access_token"]
    done = client.post(f"/api/privacy/deletion-requests/{req['id']}/approve", headers={"Authorization": f"Bearer {t}"}).json()
    assert done["status"] == "COMPLETED" and done["result"]["entities_erased"] >= 1 and done["result"]["source_records_redacted"] >= 1
    assert client.get(f"/api/entities/{person}", headers=H["investigator"]).status_code == 404
    assert person not in [r["id"] for r in client.post("/api/search", json={"query": "type:Person Sidor*"}, headers=H["investigator"]).json()["results"]]
    rec = db.execute(text("SELECT payload FROM source_records WHERE deleted_at IS NOT NULL LIMIT 1")).scalar()
    assert rec["_erased"] is True


def test_admin_cannot_approve_own_deletion(client, H):
    person = client.post("/api/search", json={"query": "type:Person Kaanvin*"}, headers=H["admin"]).json()["results"][0]["id"]
    req = client.post("/api/privacy/deletion-requests", json={"entity_id": person, "reason": "self-approval attempt (test)", "legal_basis": "test"},
                      headers=H["admin"]).json()
    assert client.post(f"/api/privacy/deletion-requests/{req['id']}/approve", headers=H["admin"]).status_code == 403


def test_retention_report(client, H):
    r = client.get("/api/privacy/retention", headers=H["admin"]).json()
    assert r["raw_records"] and all(x["retention_days"] > 0 for x in r["raw_records"])
