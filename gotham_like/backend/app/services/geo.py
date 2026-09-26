"""Geospatial intelligence on PostGIS: radius, nearest-neighbour, intersection,
geofences, trajectories, heatmaps / clusters, and combined time+space+entity queries."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from geoalchemy2 import Geography, Geometry
from sqlalchemy import cast, func, literal, select
from sqlalchemy.orm import Session

from app.models import Entity, Event, Geofence, Relationship, new_id
from app.ontology import Ontology
from app.services.serialize import entity_dict, event_dict

MAX_RADIUS_M = 500_000
ALLOWED_GEOJSON = {"Point", "LineString", "Polygon", "MultiPolygon", "MultiLineString", "MultiPoint"}


def point(lat: float, lon: float):  # noqa: ANN201
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("coordinates out of range")
    return cast(func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), Geography)


_DEPTH = {"Point": 0, "MultiPoint": 1, "LineString": 1, "MultiLineString": 2, "Polygon": 2, "MultiPolygon": 3}
MAX_POSITIONS = 20_000


def validate_geojson(geometry: Any) -> None:
    """Structural validation before anything reaches PostGIS."""
    if not isinstance(geometry, dict) or geometry.get("type") not in ALLOWED_GEOJSON:
        raise ValueError(f"geometry type must be one of {sorted(ALLOWED_GEOJSON)}")
    count = 0

    def walk(node: Any, depth: int) -> None:
        nonlocal count
        if depth == 0:
            if not (isinstance(node, list) and len(node) in (2, 3) and all(isinstance(x, int | float) and not isinstance(x, bool) for x in node)):
                raise ValueError("invalid position: expected [lon, lat]")
            lon, lat = node[0], node[1]
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("position out of range")
            count += 1
            if count > MAX_POSITIONS:
                raise ValueError("geometry has too many positions")
            return
        if not isinstance(node, list) or not node:
            raise ValueError("invalid coordinates nesting")
        for child in node:
            walk(child, depth - 1)

    walk(geometry.get("coordinates"), _DEPTH[geometry["type"]])
    if geometry["type"] in ("Polygon", "MultiPolygon"):
        rings = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        for poly in rings:
            for ring in poly:
                if len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError("polygon rings must be closed with at least 4 positions")


def geojson_geography(geometry: dict[str, Any]):  # noqa: ANN201
    validate_geojson(geometry)
    text = json.dumps(geometry)
    if len(text) > 200_000:
        raise ValueError("geometry too large")
    return cast(func.ST_SetSRID(func.ST_GeomFromGeoJSON(text), 4326), Geography)


def spatio_temporal(
    db: Session,
    ontology: Ontology,
    role: str,
    lat: float | None = None,
    lon: float | None = None,
    radius_m: float | None = None,
    geometry: dict[str, Any] | None = None,
    time_from: datetime | None = None,
    time_to: datetime | None = None,
    entity_types: list[str] | None = None,
    event_types: list[str] | None = None,
    related_to: list[str] | None = None,
    relationship_types: list[str] | None = None,
    include: tuple[str, ...] = ("entities", "events"),
    limit: int = 1000,
) -> dict[str, Any]:
    """TIME × LOCATION × ENTITY × RELATIONSHIP in one query.

    e.g. all Transactions within 2 km of (lat, lon) between t0 and t1 that are
    connected (1 hop) to one of `related_to`.
    """
    if geometry is None and (lat is None or lon is None or radius_m is None):
        raise ValueError("provide lat/lon/radius_m or a GeoJSON geometry")
    if radius_m is not None and not 0 < radius_m <= MAX_RADIUS_M:
        raise ValueError(f"radius must be in (0, {MAX_RADIUS_M}] metres")
    limit = max(1, min(limit, 5000))
    out: dict[str, Any] = {"criteria": {"lat": lat, "lon": lon, "radius_m": radius_m, "geometry": geometry is not None,
                                        "time_from": time_from.isoformat() if time_from else None,
                                        "time_to": time_to.isoformat() if time_to else None, "entity_types": entity_types,
                                        "event_types": event_types, "related_to": related_to, "relationship_types": relationship_types}}

    def spatial(col):  # noqa: ANN001, ANN202
        if geometry is not None:
            return func.ST_Intersects(col, geojson_geography(geometry))
        return func.ST_DWithin(col, point(lat, lon), radius_m)

    def dist(col):  # noqa: ANN001, ANN202
        return func.ST_Distance(col, point(lat, lon)) if geometry is None else literal(None)

    if "entities" in include:
        e = Entity
        conds = [e.merged_into.is_(None), e.deleted_at.is_(None), e.geom.is_not(None), spatial(e.geom)]
        if entity_types:
            conds.append(e.type.in_(entity_types))
        if time_from is not None:
            conds.append(e.observed_at >= time_from)
        if time_to is not None:
            conds.append(e.observed_at <= time_to)
        if related_to:
            r = Relationship
            rt = [r.deleted_at.is_(None)] + ([r.type.in_(relationship_types)] if relationship_types else [])
            linked = select(r.target_id).where(r.source_id.in_(related_to), *rt).union(select(r.source_id).where(r.target_id.in_(related_to), *rt))
            conds.append(e.id.in_(linked))
        d = dist(e.geom).label("distance_m")
        rows = db.execute(select(e, d).where(*conds).order_by(e.observed_at.nulls_last(), e.id).limit(limit)).all()
        out["entities"] = [{**entity_dict(x, ontology, role, full=False), "distance_m": round(dm, 1) if dm is not None else None} for x, dm in rows]
    if "events" in include:
        ev = Event
        conds = [ev.deleted_at.is_(None), ev.geom.is_not(None), spatial(ev.geom)]
        if event_types:
            conds.append(ev.event_type.in_(event_types))
        if time_from is not None:
            conds.append(ev.timestamp >= time_from)
        if time_to is not None:
            conds.append(ev.timestamp <= time_to)
        if related_to:
            conds.append(ev.entity_ids.overlap(related_to))
        d = dist(ev.geom).label("distance_m")
        rows = db.execute(select(ev, d).where(*conds).order_by(ev.timestamp).limit(limit)).all()
        out["events"] = [{**event_dict(x), "distance_m": round(dm, 1) if dm is not None else None} for x, dm in rows]
    out["counts"] = {k: len(out.get(k, [])) for k in include}
    out["truncated"] = any(len(out.get(k, [])) >= limit for k in include)
    return out


def nearest(db: Session, ontology: Ontology, role: str, lat: float, lon: float, k: int = 10, entity_types: list[str] | None = None) -> list[dict]:
    e = Entity
    p = point(lat, lon)
    conds = [e.merged_into.is_(None), e.deleted_at.is_(None), e.geom.is_not(None)]
    if entity_types:
        conds.append(e.type.in_(entity_types))
    # `<->` is index-assisted KNN on the GiST index
    rows = db.execute(select(e, func.ST_Distance(e.geom, p).label("d")).where(*conds).order_by(e.geom.op("<->")(p)).limit(max(1, min(k, 200)))).all()
    return [{**entity_dict(x, ontology, role, full=False), "distance_m": round(d, 1)} for x, d in rows]


def create_geofence(db: Session, name: str, geometry: dict[str, Any], created_by: str, properties: dict | None = None) -> Geofence:
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        raise ValueError("geofence must be a GeoJSON Polygon")
    validate_geojson(geometry)
    valid = db.scalar(select(func.ST_IsValid(func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)), 4326))))
    if not valid:
        raise ValueError("polygon is not valid (self-intersecting?)")
    gf = Geofence(id=new_id("gf"), name=name, geom=geojson_geography(geometry), properties=properties or {}, created_by=created_by)
    db.add(gf)
    db.flush()
    return gf


def geofence_geojson(db: Session, gf_id: str | None = None) -> list[dict[str, Any]]:
    g = Geofence
    q = select(g.id, g.name, g.properties, func.ST_AsGeoJSON(cast(g.geom, Geometry)))
    if gf_id:
        q = q.where(g.id == gf_id)
    return [{"type": "Feature", "id": i, "properties": {"name": n, **(p or {})}, "geometry": json.loads(gj)} for i, n, p, gj in db.execute(q).all()]


def events_in_geofence(db: Session, gf_id: str, time_from: datetime | None = None, time_to: datetime | None = None, limit: int = 1000) -> list[dict]:
    gf = db.get(Geofence, gf_id)
    if gf is None:
        raise KeyError(gf_id)
    ev = Event
    conds = [ev.deleted_at.is_(None), func.ST_Intersects(ev.geom, gf.geom)]
    if time_from:
        conds.append(ev.timestamp >= time_from)
    if time_to:
        conds.append(ev.timestamp <= time_to)
    return [event_dict(x) for x in db.scalars(select(ev).where(*conds).order_by(ev.timestamp).limit(limit))]


def trajectory(db: Session, entity_id: str, time_from: datetime | None = None, time_to: datetime | None = None, limit: int = 2000) -> dict[str, Any]:
    ev = Event
    conds = [ev.deleted_at.is_(None), ev.entity_ids.contains([entity_id]), ev.lat.is_not(None)]
    if time_from:
        conds.append(ev.timestamp >= time_from)
    if time_to:
        conds.append(ev.timestamp <= time_to)
    rows = db.execute(select(ev.id, ev.timestamp, ev.lat, ev.lon, ev.event_type).where(*conds).order_by(ev.timestamp).limit(limit)).all()
    coords = [[r.lon, r.lat] for r in rows]
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords} if len(coords) > 1 else {"type": "Point", "coordinates": coords[0] if coords else []},
        "properties": {"entity_id": entity_id, "points": [{"event_id": r.id, "t": r.timestamp.isoformat(), "event_type": r.event_type} for r in rows],
                       "note": "Trajectory joins event locations in time order; straight segments are not observed routes."},
    }


def heatmap(db: Session, cell_deg: float = 0.05, event_types: list[str] | None = None, time_from: datetime | None = None,
            time_to: datetime | None = None, bbox: tuple[float, float, float, float] | None = None, max_cells: int = 5000) -> dict[str, Any]:
    """Grid aggregation (also used for clustering at low zoom)."""
    cell_deg = max(0.001, min(cell_deg, 5.0))
    ev = Event
    snapped = func.ST_SnapToGrid(cast(ev.geom, Geometry), cell_deg)
    conds = [ev.deleted_at.is_(None), ev.geom.is_not(None)]
    if event_types:
        conds.append(ev.event_type.in_(event_types))
    if time_from:
        conds.append(ev.timestamp >= time_from)
    if time_to:
        conds.append(ev.timestamp <= time_to)
    if bbox:
        conds.append(func.ST_Intersects(ev.geom, cast(func.ST_MakeEnvelope(*bbox, 4326), Geography)))
    rows = db.execute(
        select(func.ST_X(snapped).label("x"), func.ST_Y(snapped).label("y"), func.count().label("n"))
        .where(*conds).group_by(snapped).order_by(func.count().desc()).limit(max_cells)
    ).all()
    return {
        "type": "FeatureCollection",
        "cell_deg": cell_deg,
        "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r.x, r.y]}, "properties": {"count": r.n}} for r in rows],
    }
