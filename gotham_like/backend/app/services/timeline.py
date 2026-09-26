"""Temporal analysis: event windows, histograms, simultaneous-event grouping."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.models import Event
from app.services.serialize import event_dict

BUCKETS = {"minute", "hour", "day", "week", "month"}


def _conds(entity_ids, event_types, time_from, time_to, near, bbox, sources):  # noqa: ANN001, ANN202
    ev = Event
    conds = [ev.deleted_at.is_(None)]
    if entity_ids:
        conds.append(ev.entity_ids.overlap(list(entity_ids)))
    if event_types:
        conds.append(ev.event_type.in_(event_types))
    if sources:
        conds.append(ev.source.in_(sources))
    if time_from is not None:
        conds.append(ev.timestamp >= time_from)
    if time_to is not None:
        conds.append(ev.timestamp <= time_to)
    if near:
        lat, lon, meters = near
        conds.append(func.ST_DWithin(ev.geom, cast(func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), Geography), meters))
    if bbox:
        conds.append(func.ST_Intersects(ev.geom, cast(func.ST_MakeEnvelope(*bbox, 4326), Geography)))
    return conds


def timeline(
    db: Session,
    entity_ids: list[str] | None = None,
    event_types: list[str] | None = None,
    time_from: datetime | None = None,
    time_to: datetime | None = None,
    near: tuple[float, float, float] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    sources: list[str] | None = None,
    bucket: str = "day",
    limit: int = 500,
    offset: int = 0,
    simultaneous_window_s: int = 60,
) -> dict[str, Any]:
    if bucket not in BUCKETS:
        raise ValueError(f"bucket must be one of {sorted(BUCKETS)}")
    conds = _conds(entity_ids, event_types, time_from, time_to, near, bbox, sources)
    ev = Event
    limit = max(1, min(limit, 5000))
    rows = db.scalars(select(ev).where(*conds).order_by(ev.timestamp, ev.id).limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(select(ev.id).where(*conds).limit(100_000).subquery()))
    b = func.date_trunc(bucket, ev.timestamp).label("bucket")
    hist = db.execute(select(b, ev.event_type, func.count()).where(*conds).group_by(b, ev.event_type).order_by(b)).all()
    buckets: dict[str, dict[str, int]] = {}
    for when, etype, count in hist:
        buckets.setdefault(when.isoformat(), {})[etype] = count
    by_type = db.execute(select(ev.event_type, func.count()).where(*conds).group_by(ev.event_type)).all()

    # Simultaneous events: events whose timestamps fall within `simultaneous_window_s` of each other
    groups: list[dict[str, Any]] = []
    window = timedelta(seconds=simultaneous_window_s)
    current: list[Event] = []
    for e in rows:
        if current and e.timestamp - current[0].timestamp > window:
            if len(current) > 1:
                groups.append(_group(current))
            current = []
        current.append(e)
    if len(current) > 1:
        groups.append(_group(current))

    span = (rows[0].timestamp.isoformat(), rows[-1].timestamp.isoformat()) if rows else (None, None)
    return {
        "events": [event_dict(e) for e in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "span": {"from": span[0], "to": span[1]},
        "histogram": {"bucket": bucket, "series": [{"t": k, "counts": v, "total": sum(v.values())} for k, v in buckets.items()]},
        "by_type": {t: c for t, c in by_type},
        "simultaneous": {"window_seconds": simultaneous_window_s, "groups": groups[:200]},
    }


def _group(events: list[Event]) -> dict[str, Any]:
    ents = sorted({x for e in events for x in e.entity_ids})
    return {
        "start": events[0].timestamp.isoformat(),
        "end": events[-1].timestamp.isoformat(),
        "event_ids": [e.id for e in events],
        "event_types": sorted({e.event_type for e in events}),
        "shared_entities": sorted(set.intersection(*[set(e.entity_ids) for e in events])) if events else [],
        "entities": ents[:100],
    }
