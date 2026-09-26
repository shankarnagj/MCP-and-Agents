import csv
import json

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.ingestion.api import RESTConnector
from app.ingestion.base import RawRecord
from app.ingestion.csv import CSVConnector
from app.ingestion.json import JSONConnector, JSONLConnector
from app.ingestion.mapping import RecordMapping, apply_mapping, entity_id, parse_ts
from app.ingestion.parquet import ParquetConnector
from app.ingestion.postgres import PostgresConnector
from app.ontology import load_ontology

O = load_ontology()
MAPPING = RecordMapping.model_validate({
    "record_type": "t",
    "entities": [
        {"key": "a", "type": "Account", "key_template": "{acc}", "properties": {"account_number": "num"}},
        {"key": "o", "type": "{owner_type}", "key_template": "{owner}", "stub": True},
        {"key": "l", "type": "Location", "key_template": "{loc}", "lat": "lat", "lon": "lon", "properties": {"name": "loc"}},
    ],
    "relationships": [{"type": "OWNS", "source": "o", "target": "a", "timestamp": "ts"}, {"type": "LOCATED_AT", "source": "a", "target": "l"}],
    "events": [{"event_type": "account_opened", "timestamp": "ts", "entities": ["a", "o"], "location": "l"}],
})


def test_mapping_produces_normalised_records():
    out = apply_mapping(O, MAPPING, "src_1", {"acc": "ACC-1", "num": "123", "owner_type": "Person", "owner": "P-1", "loc": "L1", "lat": "51.4",
                                              "lon": "3.6", "ts": "2026-01-01T10:00:00Z"})
    assert not out.errors
    assert {e.type for e in out.entities} == {"Account", "Person", "Location"}
    acc = next(e for e in out.entities if e.type == "Account")
    assert acc.id == entity_id("Account", "ACC-1")  # deterministic ids converge across sources
    assert ("account", "123") in acc.identifiers and ("key", "ACC1") in acc.identifiers
    assert next(e for e in out.entities if e.type == "Person").stub
    assert [r.type for r in out.relationships] == ["OWNS", "LOCATED_AT"]
    assert out.events[0].lat == 51.4 and out.events[0].location_id == entity_id("Location", "L1")


def test_mapping_rejects_invalid_relationships_and_coordinates():
    out = apply_mapping(O, MAPPING, "src_2", {"acc": "ACC-1", "owner_type": "Device", "owner": "D1", "loc": "L", "lat": "999", "lon": "0", "ts": "x"})
    assert any("cannot originate" in e for e in out.errors)
    assert any("coordinates out of range" in e for e in out.errors)
    assert any("timestamp" in e for e in out.errors)


def test_mapping_version_changes_with_mapping():
    v1 = MAPPING.version()
    m2 = MAPPING.model_copy(deep=True)
    m2.entities[0].properties["status"] = "status"
    assert v1 != m2.version() and v1.startswith("map-1.0+")


@pytest.mark.parametrize("v,ok", [("2026-01-01T00:00:00Z", True), ("2026-01-01", True), ("1700000000", True), ("nope", False), ("", False)])
def test_parse_ts(v, ok):
    assert (parse_ts(v) is not None) == ok


def test_raw_record_hash_stable():
    assert RawRecord("1", "t", {"a": 1, "b": 2}).content_hash == RawRecord("1", "t", {"b": 2, "a": 1}).content_hash


def test_file_connectors(tmp_path):
    rows = [{"id": "1", "name": "a"}, {"id": "2", "name": "b"}]
    with (tmp_path / "x.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "name"])
        w.writeheader()
        w.writerows(rows)
    (tmp_path / "x.json").write_text(json.dumps({"data": {"items": rows}}))
    (tmp_path / "x.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n\n")
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / "x.parquet")
    for c in (CSVConnector(tmp_path / "x.csv", "t", "id"), JSONConnector(tmp_path / "x.json", "t", "id", "data.items"),
              JSONLConnector(tmp_path / "x.jsonl", "t", "id"), ParquetConnector(tmp_path / "x.parquet", "t", "id")):
        recs = list(c.iter_records())
        assert [r.source_record_id for r in recs] == ["1", "2"], c.kind
        assert recs[0].payload["name"] == "a"


def test_connector_without_id_field_is_content_addressed(tmp_path):
    (tmp_path / "y.jsonl").write_text('{"a":1}\n{"a":2}\n')
    a = [r.source_record_id for r in JSONLConnector(tmp_path / "y.jsonl", "t").iter_records()]
    b = [r.source_record_id for r in JSONLConnector(tmp_path / "y.jsonl", "t").iter_records()]
    assert a == b and a[0] != a[1]


def test_rest_connector_paginates():
    pages = {None: {"items": [{"id": 1}, {"id": 2}], "next": "c2"}, "c2": {"items": [{"id": 3}], "next": None}}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(200, json=pages[request.url.params.get("cursor")])

    c = RESTConnector("https://api.example/records", "t", "id", headers={"Authorization": "Bearer secret"}, next_cursor_path="next",
                      transport=httpx.MockTransport(handler))
    assert [r.source_record_id for r in c.iter_records()] == ["1", "2", "3"]
    assert "secret" not in json.dumps(c.describe())


def test_rest_connector_rejects_non_http():
    with pytest.raises(ValueError):
        RESTConnector("file:///etc/passwd", "t")


def test_postgres_connector_rejects_injection_identifiers():
    for bad in ("users; DROP TABLE x", "a b", "1abc", "x\"y"):
        with pytest.raises(ValueError):
            PostgresConnector("postgresql+psycopg://u:p@h/db", bad, "t")
    c = PostgresConnector("postgresql+psycopg://u:p@h/db", "people", "t", "id", columns=["id", "name"], equals_filters={"country": "X'; --"})
    sql = str(c.build_query().compile())
    assert "X'" not in sql and ":country" in sql or "%(country" in sql
    assert "u:p" not in json.dumps(c.describe())
