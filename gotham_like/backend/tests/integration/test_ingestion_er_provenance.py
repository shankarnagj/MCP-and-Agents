"""Dataset loading, lineage, idempotency, change detection, entity resolution, provenance."""

import json

from sqlalchemy import func, select

from app.entity_resolution.service import resolve_type, unmerge
from app.ingestion.mapping import entity_id, load_mappings
from app.ingestion.pipeline import ensure_source, run_ingestion
from app.ingestion.json import JSONLConnector
from app.graph.store import resolve_canonical
from app.models import Entity, Event, LineageLink, Relationship, ResolutionCandidate, SourceRecord
from app.ontology import get_ontology
from app.config import get_settings


def live(db, t):
    return db.scalar(select(func.count()).where(Entity.type == t, Entity.merged_into.is_(None), Entity.deleted_at.is_(None)))


def test_synthetic_dataset_volumes(db, seeded):
    assert live(db, "Person") == 1010  # 1000 CRM persons + 10 look-alikes (60 KYC duplicates merged)
    assert live(db, "Organization") == 200
    assert live(db, "Account") == 2000
    assert live(db, "Device") == 1000
    assert live(db, "Transaction") == 10000
    assert live(db, "Location") == 500
    assert db.scalar(select(func.count()).select_from(Event)) >= 5000 + 10000
    assert db.scalar(select(func.count()).select_from(Relationship)) > 50000
    for run in seeded["report"]["ingestion"]:
        assert run["error_count"] == 0, run


def test_every_derived_object_has_lineage(db):
    for kind, model in (("entity", Entity), ("relationship", Relationship), ("event", Event)):
        orphan = db.scalar(
            select(func.count()).select_from(model).where(~model.id.in_(select(LineageLink.child_id).where(LineageLink.child_kind == kind)))
            .where(*([model.provenance["stub"].is_(None)] if kind == "entity" else []))
        )
        assert orphan == 0, kind


def test_transaction_lineage_chain(db):
    """transaction_928 → normalized entity → graph edge, all traceable back to the raw record."""
    rec = db.scalar(select(SourceRecord).where(SourceRecord.source_id == "synthetic_payments", SourceRecord.source_record_id == "TX-0000928"))
    assert rec is not None and rec.payload["txn_id"] == "TX-0000928"
    assert rec.transformation_version.startswith("map-1.0+")
    children = db.execute(select(LineageLink.child_kind, LineageLink.child_id).where(LineageLink.parent_id == rec.id)).all()
    kinds = {k for k, _ in children}
    assert {"entity", "relationship", "event"} <= kinds
    txn = entity_id("Transaction", "TX-0000928")
    assert ("entity", txn) in children
    edge = db.scalar(select(Relationship).where(Relationship.source_id == txn, Relationship.type == "TRANSFERRED_TO"))
    assert rec.id in edge.source_records and edge.provenance["transformation"] == "mapping:transaction"


def test_reingestion_is_idempotent_and_detects_changes(db, tmp_path):
    onto = get_ontology()
    mappings = load_mappings(get_settings().ontology_path.parent / "mappings.json")
    src = ensure_source(db, "test_kyc_updates", "KYC updates (test)", "jsonl", classification="SYNTHETIC / DEMONSTRATION DATA")
    path = tmp_path / "kyc.jsonl"
    path.write_text(json.dumps({"kyc_id": "T-1", "name": "Tovin Maresk", "email": "tovin@example.com", "phone": "+1-202-555-9999"}) + "\n")
    r1 = run_ingestion(db, onto, src, JSONLConnector(path, "person_kyc", "kyc_id"), mappings["person_kyc"])
    assert r1.records_new == 1
    r2 = run_ingestion(db, onto, src, JSONLConnector(path, "person_kyc", "kyc_id"), mappings["person_kyc"])
    assert (r2.records_new, r2.records_unchanged, r2.records_changed) == (0, 1, 0)
    path.write_text(json.dumps({"kyc_id": "T-1", "name": "Tovin Maresk", "email": "tovin@example.org", "phone": "+1-202-555-9999"}) + "\n")
    r3 = run_ingestion(db, onto, src, JSONLConnector(path, "person_kyc", "kyc_id"), mappings["person_kyc"])
    assert r3.records_changed == 1 and r3.changed_record_ids
    ent = db.get(Entity, entity_id("Person", "kyc:T-1"))
    assert ent.properties["email"] == "tovin@example.org"
    db.rollback()


def test_entity_resolution_merges_true_duplicates_with_evidence(db):
    merged = db.scalars(select(Entity).where(Entity.type == "Person", Entity.merged_into.is_not(None))).all()
    assert len(merged) == 60
    canon = db.get(Entity, merged[0].merged_into)
    res = canon.provenance["resolution"]
    assert res[0]["epistemic_status"] == "SYSTEM_INFERENCE" and res[0]["reasons"]
    assert canon.confidence <= res[0]["score"]
    link = db.scalar(select(LineageLink).where(LineageLink.child_id == canon.id, LineageLink.transformation == "entity_resolution.merge"))
    assert link.details["match"]["decision"] == "MATCH"
    # references to the duplicate are redirected
    assert resolve_canonical(db, merged[0].id) == canon.id


def test_lookalikes_are_possible_matches_not_merged(db):
    cands = db.scalars(select(ResolutionCandidate).where(ResolutionCandidate.entity_type == "Person", ResolutionCandidate.decision == "POSSIBLE_MATCH")).all()
    assert len(cands) >= 10
    assert not any(c.merged for c in cands)
    lookalike = db.get(Entity, entity_id("Person", "kyc:KYC-L000"))
    assert lookalike.merged_into is None


def test_unmerge_restores_entities(db):
    dup = db.scalars(select(Entity).where(Entity.type == "Person", Entity.merged_into.is_not(None))).first()
    canon_id = dup.merged_into
    before_sources = len(db.get(Entity, canon_id).source_ids)
    unmerge(db, dup.id, "tester")
    assert db.get(Entity, dup.id).merged_into is None
    assert len(db.get(Entity, canon_id).source_ids) < before_sources
    db.rollback()


def test_er_rerun_is_stable(db):
    stats = resolve_type(db, get_ontology(), "Person", merge=False)
    assert stats.matches == 0  # everything already merged
    db.rollback()


def test_provenance_api_for_relationship(client, H, ids):
    rels = client.get(f"/api/entities/{ids['shared_device']}/relationships", params={"relationship_type": "USED"}, headers=H["analyst"]).json()
    rel = rels["items"][0]
    p = client.get(f"/api/provenance/{rel['id']}", headers=H["analyst"]).json()
    assert p["kind"] == "relationship" and "exists because source record" in p["why"]
    sr = p["source_records"][0]
    assert sr["source"]["classification"] == "SYNTHETIC / DEMONSTRATION DATA"
    assert sr["ingestion_timestamp"] and sr["transformation_version"] and isinstance(sr["payload"], dict)
    assert p["lineage_upstream"]["edges"][0]["from"].startswith("source_record:")
    # viewers see provenance structure but not raw payloads
    pv = client.get(f"/api/provenance/{rel['id']}", headers=H["viewer"]).json()
    assert pv["source_records"][0]["payload"].startswith("[withheld")


def test_provenance_for_entity_source_record_and_missing(client, H, ids):
    p = client.get(f"/api/provenance/{ids['merchant_account']}", headers=H["analyst"]).json()
    assert p["kind"] == "entity" and p["source_records_total"] >= 1
    rec_id = p["source_records"][0]["id"]
    r = client.get(f"/api/provenance/{rec_id}", headers=H["analyst"]).json()
    assert r["kind"] == "source_record" and r["epistemic_status"] == "RAW"
    down = client.get(f"/api/provenance/{rec_id}/lineage", params={"kind": "source_record", "direction": "down"}, headers=H["analyst"]).json()
    assert down["edges"]
    assert client.get("/api/provenance/nope", headers=H["analyst"]).status_code == 404


def test_unmerge_order_is_enforced(db):
    import pytest

    from app.entity_resolution.resolver import compare
    from app.entity_resolution.service import merge_entities

    onto = get_ontology()
    ents = db.scalars(select(Entity).where(Entity.type == "Vessel", Entity.merged_into.is_(None)).order_by(Entity.id).limit(3)).all()
    canon, d1, d2 = ents
    r = compare(onto, "Vessel", canon.properties, canon.properties)
    merge_entities(db, canon, d1, r, actor="tester")
    merge_entities(db, canon, d2, r, actor="tester")
    with pytest.raises(ValueError, match="first"):
        unmerge(db, d1.id, "tester")
    unmerge(db, d2.id, "tester")
    unmerge(db, d1.id, "tester")
    assert db.get(Entity, d1.id).merged_into is None and db.get(Entity, d2.id).merged_into is None
    db.rollback()


def test_postgres_connector_end_to_end(db):
    """Read from a real PostgreSQL table through the connector (bound filters, validated identifiers)."""
    import os

    from sqlalchemy import text

    from app.ingestion.postgres import PostgresConnector

    db.execute(text("CREATE SCHEMA IF NOT EXISTS ext"))
    db.execute(text("DROP TABLE IF EXISTS ext.people"))
    db.execute(text("CREATE TABLE ext.people (id text primary key, name text, country text, joined date)"))
    db.execute(text("INSERT INTO ext.people VALUES ('a','Relo Tamsin','Aldoria','2026-01-02'), ('b','Sumar Tidel','Brevia','2026-02-03'), "
                    "('c','x''; DROP TABLE ext.people; --','Aldoria','2026-03-04')"))
    db.commit()
    c = PostgresConnector(os.environ["TESSERA_DATABASE_URL"], "people", "person_ext", "id", columns=["id", "name", "joined"], schema="ext",
                          equals_filters={"country": "Aldoria"})
    recs = list(c.iter_records())
    assert [r.source_record_id for r in recs] == ["a", "c"]
    assert recs[0].payload["joined"] == "2026-01-02"  # dates made JSON-safe
    inj = PostgresConnector(os.environ["TESSERA_DATABASE_URL"], "people", "t", "id", schema="ext", equals_filters={"country": "x' OR '1'='1"})
    assert list(inj.iter_records()) == []
    assert db.execute(text("SELECT count(*) FROM ext.people")).scalar() == 3
    db.execute(text("DROP SCHEMA ext CASCADE"))
    db.commit()
