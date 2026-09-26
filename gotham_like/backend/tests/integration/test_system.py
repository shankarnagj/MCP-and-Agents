def test_health_ready_metrics(client):
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/ready").json()
    assert r["status"] == "ready" and r["checks"]["database"] == "ok" and r["checks"]["postgis"] and r["checks"]["migrations"] == "0002"
    m = client.get("/metrics").text
    assert "tessera_http_requests_total" in m and "tessera_db_query_seconds" in m and "tessera_http_request_seconds" in m


def test_request_ids_and_timing_headers(client):
    r = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123" and float(r.headers["x-response-time-ms"]) >= 0
    r2 = client.get("/health", headers={"X-Request-ID": "<script>"})
    assert r2.headers["x-request-id"] != "<script>"


def test_stats_and_ontology(client, H):
    s = client.get("/api/stats", headers=H["viewer"]).json()
    assert s["entities"]["Person"] == 1010 and s["data_label"] == "SYNTHETIC / DEMONSTRATION DATA"
    o = client.get("/api/ontology", headers=H["viewer"]).json()
    assert "Person" in o["entity_types"]


def test_sources_and_runs(client, H):
    src = client.get("/api/sources", headers=H["viewer"]).json()
    assert len([s for s in src if s["id"].startswith("synthetic")]) == 14 and all(s["last_run"] for s in src if s["id"].startswith("synthetic"))
    runs = client.get("/api/ingestion-runs", headers=H["viewer"]).json()
    assert runs and runs[0]["transformation_version"]
