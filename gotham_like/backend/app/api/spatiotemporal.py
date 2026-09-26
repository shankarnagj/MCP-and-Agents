"""Timeline and geospatial endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.common import ip_of, onto, ts_param
from app.audit.service import record
from app.auth.deps import Principal, require
from app.auth.rbac import P_INV_WRITE, P_READ
from app.db import get_db
from app.graph.store import resolve_canonical
from app.ontology import Ontology
from app.services import geo
from app.services.timeline import timeline

router = APIRouter(prefix="/api", tags=["timeline", "geo"])


def _near(lat: float | None, lon: float | None, radius_m: float | None) -> tuple[float, float, float] | None:
    if lat is None and lon is None and radius_m is None:
        return None
    if lat is None or lon is None or radius_m is None:
        raise HTTPException(422, "near requires lat, lon and radius_m")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not 0 < radius_m <= geo.MAX_RADIUS_M:
        raise HTTPException(422, "invalid near parameters")
    return lat, lon, radius_m


@router.get("/timeline")
def get_timeline(
    request: Request,
    entity_id: list[str] | None = Query(None),
    event_type: list[str] | None = Query(None),
    source: list[str] | None = Query(None),
    time_from: str | None = None,
    time_to: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_m: float | None = None,
    bucket: str = "day",
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    simultaneous_window_s: int = Query(60, ge=1, le=86400),
    user: Principal = Depends(require(P_READ)),
    db: Session = Depends(get_db),
) -> dict:
    ids = [resolve_canonical(db, e) for e in entity_id] if entity_id else None
    try:
        res = timeline(db, ids, event_type, ts_param(time_from, "time_from"), ts_param(time_to, "time_to"), _near(lat, lon, radius_m), None,
                       source, bucket, limit, offset, simultaneous_window_s)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    record(db, "timeline_query", user, "timeline", None, details={"entities": (ids or [])[:20], "event_types": event_type, "total": res["total"]},
           ip=ip_of(request))
    db.commit()
    return res


class GeoQuery(BaseModel):
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    radius_m: float | None = Field(default=None, gt=0, le=geo.MAX_RADIUS_M)
    geometry: dict[str, Any] | None = None
    time_from: str | None = None
    time_to: str | None = None
    entity_types: list[str] | None = None
    event_types: list[str] | None = None
    related_to: list[str] | None = Field(default=None, max_length=200)
    relationship_types: list[str] | None = None
    include: list[str] = Field(default_factory=lambda: ["entities", "events"])
    limit: int = Field(default=1000, ge=1, le=5000)


@router.post("/geo/query")
def geo_query(body: GeoQuery, request: Request, user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db),
              ontology: Ontology = Depends(onto)) -> dict:
    """Combined TIME + LOCATION + ENTITY + RELATIONSHIP query."""
    for t in body.entity_types or []:
        if t not in ontology.entity_types:
            raise HTTPException(422, f"unknown entity type {t}")
    if set(body.include) - {"entities", "events"}:
        raise HTTPException(422, "include must be entities and/or events")
    try:
        res = geo.spatio_temporal(db, ontology, user.role, body.lat, body.lon, body.radius_m, body.geometry, ts_param(body.time_from, "time_from"),
                                  ts_param(body.time_to, "time_to"), body.entity_types, body.event_types,
                                  [resolve_canonical(db, x) for x in body.related_to] if body.related_to else None, body.relationship_types,
                                  tuple(body.include), body.limit)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    record(db, "geo_query", user, "geo", None, details={"criteria": res["criteria"], "counts": res["counts"]}, ip=ip_of(request))
    db.commit()
    return res


@router.get("/geo/nearest")
def geo_nearest(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180), k: int = Query(10, ge=1, le=200),
                entity_type: list[str] | None = Query(None), user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db),
                ontology: Ontology = Depends(onto)) -> dict:
    return {"lat": lat, "lon": lon, "k": k, "items": geo.nearest(db, ontology, user.role, lat, lon, k, entity_type)}


class GeofenceBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geometry: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)


@router.post("/geo/geofences", status_code=201)
def create_geofence(body: GeofenceBody, user: Principal = Depends(require(P_INV_WRITE)), db: Session = Depends(get_db)) -> dict:
    try:
        gf = geo.create_geofence(db, body.name, body.geometry, user.id, body.properties)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return geo.geofence_geojson(db, gf.id)[0]


@router.get("/geo/geofences")
def list_geofences(user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db)) -> dict:
    return {"type": "FeatureCollection", "features": geo.geofence_geojson(db)}


@router.get("/geo/geofences/{gf_id}/events")
def geofence_events(gf_id: str, time_from: str | None = None, time_to: str | None = None, limit: int = Query(1000, ge=1, le=5000),
                    user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db)) -> dict:
    try:
        items = geo.events_in_geofence(db, gf_id, ts_param(time_from, "time_from"), ts_param(time_to, "time_to"), limit)
    except KeyError as exc:
        raise HTTPException(404, "geofence not found") from exc
    return {"geofence": gf_id, "items": items}


@router.get("/geo/trajectory/{entity_id}")
def get_trajectory(entity_id: str, time_from: str | None = None, time_to: str | None = None, user: Principal = Depends(require(P_READ)),
                   db: Session = Depends(get_db)) -> dict:
    return geo.trajectory(db, resolve_canonical(db, entity_id), ts_param(time_from, "time_from"), ts_param(time_to, "time_to"))


@router.get("/geo/heatmap")
def get_heatmap(cell_deg: float = Query(0.05, gt=0, le=5), event_type: list[str] | None = Query(None), time_from: str | None = None,
                time_to: str | None = None, min_lon: float | None = None, min_lat: float | None = None, max_lon: float | None = None,
                max_lat: float | None = None, user: Principal = Depends(require(P_READ)), db: Session = Depends(get_db)) -> dict:
    bbox = (min_lon, min_lat, max_lon, max_lat) if None not in (min_lon, min_lat, max_lon, max_lat) else None
    return geo.heatmap(db, cell_deg, event_type, ts_param(time_from, "time_from"), ts_param(time_to, "time_to"), bbox)  # type: ignore[arg-type]
