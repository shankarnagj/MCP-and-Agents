"""Declarative mapping from raw records to normalised entities, relationships and events.

A mapping is data (JSON). Its hash is part of the transformation version recorded
in lineage, so any change to a mapping is traceable.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.entity_resolution import normalize as N
from app.ontology import Ontology

TRANSFORMATION_BASE_VERSION = "map-1.0"
_TEMPLATE = re.compile(r"\{(\w+)\}")


class ValueSpec(BaseModel):
    field: str | None = None
    template: str | None = None
    const: Any = None


PropMap = dict[str, str | ValueSpec]


class EntitySpec(BaseModel):
    key: str  # local handle within the record
    type: str
    key_template: str  # natural key, e.g. "{person_id}"
    properties: PropMap = Field(default_factory=dict)
    lat: str | None = None
    lon: str | None = None
    observed_at: str | None = None
    stub: bool = False  # reference only: do not overwrite properties of the full record
    confidence: float = 1.0


class RelationshipSpec(BaseModel):
    type: str
    source: str  # entity key
    target: str
    timestamp: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    properties: PropMap = Field(default_factory=dict)
    confidence: float = 1.0
    when: str | None = None  # only emit when this field is non-empty


class EventSpec(BaseModel):
    event_type: str | ValueSpec
    timestamp: str
    start_time: str | None = None
    end_time: str | None = None
    entities: list[str] = Field(default_factory=list)
    lat: str | None = None
    lon: str | None = None
    location: str | None = None  # entity key of a Location
    properties: PropMap = Field(default_factory=dict)


class RecordMapping(BaseModel):
    record_type: str
    entities: list[EntitySpec] = Field(default_factory=list)
    relationships: list[RelationshipSpec] = Field(default_factory=list)
    events: list[EventSpec] = Field(default_factory=list)

    def version(self) -> str:
        digest = hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:8]
        return f"{TRANSFORMATION_BASE_VERSION}+{digest}"


def entity_id(entity_type: str, natural_key: str) -> str:
    """Deterministic id: identical natural keys from different sources converge."""
    digest = hashlib.sha1(f"{entity_type}|{natural_key}".encode(), usedforsecurity=False).hexdigest()[:20]
    return f"{entity_type.lower()[:4]}_{digest}"


def _render(template: str, row: dict[str, Any]) -> str:
    def sub(m: re.Match[str]) -> str:
        v = row.get(m.group(1))
        return "" if v is None else str(v)

    return _TEMPLATE.sub(sub, template)


def _value(spec: str | ValueSpec, row: dict[str, Any]) -> Any:
    if isinstance(spec, str):
        return row.get(spec)
    if spec.const is not None:
        return spec.const
    if spec.template is not None:
        return _render(spec.template, row)
    return row.get(spec.field) if spec.field else None


def parse_ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            try:
                dt = datetime.fromtimestamp(float(text), tz=UTC)
            except ValueError:
                return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f


@dataclass
class NormEntity:
    id: str
    type: str
    label: str
    properties: dict[str, Any]
    identifiers: list[tuple[str, str]]
    search_text: str
    lat: float | None
    lon: float | None
    observed_at: datetime | None
    stub: bool
    confidence: float
    natural_key: str = ""


@dataclass
class NormRelationship:
    id: str
    type: str
    source_id: str
    target_id: str
    timestamp: datetime | None
    start_time: datetime | None
    end_time: datetime | None
    properties: dict[str, Any]
    confidence: float


@dataclass
class NormEvent:
    id: str
    event_type: str
    timestamp: datetime
    start_time: datetime | None
    end_time: datetime | None
    entity_ids: list[str]
    location_id: str | None
    lat: float | None
    lon: float | None
    properties: dict[str, Any]


@dataclass
class NormalizedOutput:
    entities: list[NormEntity] = field(default_factory=list)
    relationships: list[NormRelationship] = field(default_factory=list)
    events: list[NormEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def build_search_text(ontology: Ontology, etype: str, props: dict[str, Any]) -> str:
    parts: list[str] = []
    tdef = ontology.entity_type(etype)
    for pname, pdef in tdef.properties.items():
        v = props.get(pname)
        if v in (None, "") or not pdef.searchable:
            continue
        parts.append(N.basic(str(v)))
        if pdef.identifier:
            parts.append(N.normalize_identifier(pdef.identifier, str(v)).lower())
    return " ".join(dict.fromkeys(p for p in parts if p))


def apply_mapping(ontology: Ontology, mapping: RecordMapping, source_record_key: str, row: dict[str, Any]) -> NormalizedOutput:
    out = NormalizedOutput()
    keys: dict[str, str] = {}
    for spec in mapping.entities:
        natural = _render(spec.key_template, row).strip()
        if not natural or natural.strip("|:-") == "":
            continue  # nothing to identify the entity by
        etype = _render(spec.type, row) if "{" in spec.type else spec.type
        if etype not in ontology.entity_types:
            out.errors.append(f"{spec.key}: unknown entity type {etype!r}")
            continue
        spec = spec.model_copy(update={"type": etype})
        eid = entity_id(spec.type, natural)
        keys[spec.key] = eid
        raw_props = {p: _value(v, row) for p, v in spec.properties.items()}
        try:
            props = ontology.validate_properties(spec.type, raw_props)
        except ValueError as exc:
            out.errors.append(f"{spec.key}: {exc}")
            continue
        tdef = ontology.entity_type(spec.type)
        label = str(props.get(tdef.label) or natural)
        identifiers = [("key", N.identifier(natural))]  # source natural key, e.g. ACC-0000012 -> ACC0000012
        for pname, pdef in tdef.properties.items():
            if pdef.identifier and props.get(pname) not in (None, ""):
                norm = N.normalize_identifier(pdef.identifier, str(props[pname]))
                if norm:
                    identifiers.append((pdef.identifier, norm))
        lat = _float(row.get(spec.lat)) if spec.lat else None
        lon = _float(row.get(spec.lon)) if spec.lon else None
        if lat is not None and not -90 <= lat <= 90 or lon is not None and not -180 <= lon <= 180:
            out.errors.append(f"{spec.key}: coordinates out of range")
            lat = lon = None
        out.entities.append(
            NormEntity(
                id=eid, type=spec.type, label=label[:300], properties=props, identifiers=identifiers,
                search_text=build_search_text(ontology, spec.type, props) or N.basic(label),
                lat=lat, lon=lon, observed_at=parse_ts(row.get(spec.observed_at)) if spec.observed_at else None,
                stub=spec.stub, confidence=spec.confidence, natural_key=natural,
            )
        )
    etypes = {e.id: e.type for e in out.entities}
    for i, rs in enumerate(mapping.relationships):
        if rs.when and row.get(rs.when) in (None, ""):
            continue
        s, t = keys.get(rs.source), keys.get(rs.target)
        if not s or not t:
            continue
        try:
            ontology.validate_relationship(rs.type, etypes[s], etypes[t])
        except ValueError as exc:
            out.errors.append(str(exc))
            continue
        rid = "rel_" + hashlib.sha1(f"{rs.type}|{s}|{t}|{source_record_key}|{i}".encode(), usedforsecurity=False).hexdigest()[:20]
        out.relationships.append(
            NormRelationship(
                id=rid, type=rs.type, source_id=s, target_id=t,
                timestamp=parse_ts(row.get(rs.timestamp)) if rs.timestamp else None,
                start_time=parse_ts(row.get(rs.start_time)) if rs.start_time else None,
                end_time=parse_ts(row.get(rs.end_time)) if rs.end_time else None,
                properties={k: _value(v, row) for k, v in rs.properties.items() if _value(v, row) not in (None, "")},
                confidence=rs.confidence,
            )
        )
    for i, ev in enumerate(mapping.events):
        ts = parse_ts(row.get(ev.timestamp))
        if ts is None:
            out.errors.append("event without valid timestamp skipped")
            continue
        etype = _value(ev.event_type, row) if isinstance(ev.event_type, ValueSpec) else ev.event_type
        loc_id = keys.get(ev.location) if ev.location else None
        lat = _float(row.get(ev.lat)) if ev.lat else None
        lon = _float(row.get(ev.lon)) if ev.lon else None
        if loc_id and lat is None:
            loc = next((e for e in out.entities if e.id == loc_id), None)
            if loc:
                lat, lon = loc.lat, loc.lon
        out.events.append(
            NormEvent(
                id="evt_" + hashlib.sha1(f"{source_record_key}|{i}".encode(), usedforsecurity=False).hexdigest()[:20],
                event_type=str(etype), timestamp=ts,
                start_time=parse_ts(row.get(ev.start_time)) if ev.start_time else None,
                end_time=parse_ts(row.get(ev.end_time)) if ev.end_time else None,
                entity_ids=[keys[k] for k in ev.entities if k in keys], location_id=loc_id, lat=lat, lon=lon,
                properties={k: _value(v, row) for k, v in ev.properties.items() if _value(v, row) not in (None, "")},
            )
        )
    return out


def load_mappings(path) -> dict[str, RecordMapping]:  # noqa: ANN001
    data = json.loads(open(path).read())
    return {m["record_type"]: RecordMapping.model_validate(m) for m in data["mappings"]}
