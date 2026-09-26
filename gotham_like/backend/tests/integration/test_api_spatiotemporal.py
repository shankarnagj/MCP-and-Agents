"""Timeline, geospatial and combined time + space + entity + relationship queries."""

import math

import pytest


def haversine(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    return 2 * r * math.asin(math.sqrt(math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))


def test_timeline_window_and_histogram(client, H, ids):
    r = client.get("/api/timeline", params={"entity_id": ids["shared_device"], "time_from": "2026-03-01T00:00:00Z", "time_to": "2026-03-31T23:59:59Z",
                                            "bucket": "day"}, headers=H["analyst"]).json()
    assert r["total"] == 35
    assert set(r["by_type"]) == {"auth_failure", "login", "device_connection", "dns_query", "location_change"}
    assert all("2026-03" in e["timestamp"] for e in r["events"])
    assert sum(s["total"] for s in r["histogram"]["series"]) == 35
    ts = [e["timestamp"] for e in r["events"]]
    assert ts == sorted(ts)


def test_timeline_simultaneous_grouping(client, H, ids):
    r = client.get("/api/timeline", params={"entity_id": ids["shared_device"], "simultaneous_window_s": 180}, headers=H["analyst"]).json()
    assert r["simultaneous"]["groups"], "device_connection and dns_query happen within 2 minutes"
    g = r["simultaneous"]["groups"][0]
    assert set(g["event_types"]) >= {"device_connection", "dns_query"} and ids["shared_device"] in g["shared_entities"]


def test_timeline_filters(client, H):
    r = client.get("/api/timeline", params={"event_type": "shipment_arrival", "limit": 10}, headers=H["viewer"]).json()
    assert r["total"] == 150 and len(r["events"]) == 10
    assert client.get("/api/timeline", params={"bucket": "fortnight"}, headers=H["viewer"]).status_code == 422
    assert client.get("/api/timeline", params={"lat": 51.45}, headers=H["viewer"]).status_code == 422


def test_transactions_within_2km_in_time_window(client, H):
    """Core capability: all transactions within 2 km of a location during a window."""
    body = {"lat": 51.45, "lon": 3.60, "radius_m": 2000, "time_from": "2026-02-14T18:00:00Z", "time_to": "2026-02-14T20:30:00Z",
            "entity_types": ["Transaction"], "event_types": ["transaction"]}
    r = client.post("/api/geo/query", json=body, headers=H["analyst"]).json()
    assert r["counts"] == {"entities": 25, "events": 25}
    for e in r["entities"]:
        assert e["distance_m"] <= 2000
        assert haversine(51.45, 3.60, e["lat"], e["lon"]) == pytest.approx(e["distance_m"], rel=0.01)
        assert "2026-02-14T18" <= e["observed_at"] <= "2026-02-14T20:30"


def test_geo_query_with_relationship_constraint(client, H, ids):
    """TIME × LOCATION × ENTITY × RELATIONSHIP: transactions near Harbor Plaza sent to the merchant account."""
    body = {"lat": 51.45, "lon": 3.60, "radius_m": 3000, "time_from": "2026-03-01T00:00:00Z", "time_to": "2026-03-31T00:00:00Z",
            "entity_types": ["Transaction"], "related_to": [ids["merchant_account"]], "relationship_types": ["TRANSFERRED_TO"], "include": ["entities"]}
    r = client.post("/api/geo/query", json=body, headers=H["analyst"]).json()
    assert r["counts"]["entities"] == 28  # 7 ring accounts × 4 payments


def test_polygon_intersection(client, H):
    d = 0.01
    poly = {"type": "Polygon", "coordinates": [[[3.6 - d, 51.45 - d], [3.6 + d, 51.45 - d], [3.6 + d, 51.45 + d], [3.6 - d, 51.45 + d], [3.6 - d, 51.45 - d]]]}
    r = client.post("/api/geo/query", json={"geometry": poly, "entity_types": ["Location"], "include": ["entities"]}, headers=H["analyst"]).json()
    assert any(e["label"] == "Harbor Plaza" for e in r["entities"])
    bad = client.post("/api/geo/query", json={"geometry": {"type": "Sphere"}}, headers=H["analyst"])
    assert bad.status_code == 422


def test_nearest_neighbour_ordering(client, H):
    r = client.get("/api/geo/nearest", params={"lat": 51.45, "lon": 3.6, "k": 5, "entity_type": "Location"}, headers=H["analyst"]).json()
    d = [x["distance_m"] for x in r["items"]]
    assert r["items"][0]["label"] == "Harbor Plaza" and d == sorted(d)


def test_geofences(client, H):
    fences = client.get("/api/geo/geofences", headers=H["viewer"]).json()
    harbor = next(f for f in fences["features"] if f["properties"]["name"] == "Harbor Plaza perimeter")
    evs = client.get(f"/api/geo/geofences/{harbor['id']}/events", headers=H["viewer"]).json()["items"]
    assert evs and all(abs(e["lat"] - 51.45) < 0.01 for e in evs)
    ring = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    ok = client.post("/api/geo/geofences", json={"name": "t", "geometry": {"type": "Polygon", "coordinates": [ring]}}, headers=H["analyst"])
    assert ok.status_code == 201
    bow = [[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]
    assert client.post("/api/geo/geofences", json={"name": "bad", "geometry": {"type": "Polygon", "coordinates": [bow]}}, headers=H["analyst"]).status_code == 422
    assert client.post("/api/geo/geofences", json={"name": "v", "geometry": {"type": "Polygon", "coordinates": [ring]}}, headers=H["viewer"]).status_code == 403


def test_trajectory_and_heatmap(client, H, ids):
    t = client.get(f"/api/geo/trajectory/{ids['shared_device']}", headers=H["analyst"]).json()
    assert t["geometry"]["type"] == "LineString" and len(t["geometry"]["coordinates"]) >= 10
    pts = t["properties"]["points"]
    assert [p["t"] for p in pts] == sorted(p["t"] for p in pts)
    h = client.get("/api/geo/heatmap", params={"cell_deg": 0.05, "event_type": "transaction"}, headers=H["analyst"]).json()
    assert sum(f["properties"]["count"] for f in h["features"]) == 10000


def test_geo_input_validation(client, H):
    assert client.post("/api/geo/query", json={"lat": 91, "lon": 0, "radius_m": 10}, headers=H["analyst"]).status_code == 422
    assert client.post("/api/geo/query", json={"lat": 0, "lon": 0, "radius_m": 10_000_000}, headers=H["analyst"]).status_code == 422
    assert client.post("/api/geo/query", json={"lat": 0}, headers=H["analyst"]).status_code == 422
