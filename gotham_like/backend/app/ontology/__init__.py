"""Configurable ontology: entity types, properties (with sensitivity), relationship types.

The ontology is data, not code. It is loaded from JSON and validated; the rest of
the platform (ingestion, search, query builder, masking, ER) consults it rather than
hard-coding types. This keeps the model extensible without code changes.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PropType = Literal["string", "number", "integer", "boolean", "date", "datetime"]
Sensitivity = Literal["public", "pii", "restricted"]


class PropertyDef(BaseModel):
    type: PropType = "string"
    sensitivity: Sensitivity = "public"
    searchable: bool = False
    identifier: str | None = None  # identifier kind, used for exact lookup and ER
    resolution: str | None = None  # entity-resolution signal name
    description: str = ""


class EntityTypeDef(BaseModel):
    label: str
    description: str = ""
    properties: dict[str, PropertyDef]

    @model_validator(mode="after")
    def _label_exists(self) -> "EntityTypeDef":
        if self.label not in self.properties:
            raise ValueError(f"label property '{self.label}' not declared")
        return self


class RelationshipTypeDef(BaseModel):
    description: str = ""
    source_types: list[str] = Field(default_factory=lambda: ["*"])
    target_types: list[str] = Field(default_factory=lambda: ["*"])
    symmetric: bool = False


class Ontology(BaseModel):
    version: str
    name: str
    description: str = ""
    sensitivity_levels: dict[str, str] = Field(default_factory=dict)
    entity_types: dict[str, EntityTypeDef]
    relationship_types: dict[str, RelationshipTypeDef]
    event_types: list[str] = Field(default_factory=list)

    @field_validator("entity_types", "relationship_types")
    @classmethod
    def _names_are_identifiers(cls, v: dict[str, Any]) -> dict[str, Any]:
        for name in v:
            if not name.replace("_", "").isalnum():
                raise ValueError(f"invalid type name: {name!r}")
        return v

    @model_validator(mode="after")
    def _relationship_endpoints_exist(self) -> "Ontology":
        for rname, rdef in self.relationship_types.items():
            for t in rdef.source_types + rdef.target_types:
                if t != "*" and t not in self.entity_types:
                    raise ValueError(f"relationship {rname} references unknown entity type {t}")
        return self

    # ----- queries -------------------------------------------------------
    def entity_type(self, name: str) -> EntityTypeDef:
        try:
            return self.entity_types[name]
        except KeyError as exc:
            raise OntologyError(f"Unknown entity type: {name}") from exc

    def has_property(self, entity_type: str, prop: str) -> bool:
        return prop in self.entity_type(entity_type).properties

    def all_property_names(self) -> set[str]:
        return {p for et in self.entity_types.values() for p in et.properties}

    def identifier_kinds(self) -> dict[str, list[tuple[str, str]]]:
        """identifier kind -> [(entity_type, property)]"""
        out: dict[str, list[tuple[str, str]]] = {}
        for tname, tdef in self.entity_types.items():
            for pname, pdef in tdef.properties.items():
                if pdef.identifier:
                    out.setdefault(pdef.identifier, []).append((tname, pname))
        return out

    def sensitivity(self, entity_type: str, prop: str) -> str:
        et = self.entity_types.get(entity_type)
        if not et or prop not in et.properties:
            return "public"
        return et.properties[prop].sensitivity

    def searchable_properties(self, entity_type: str) -> list[str]:
        return [p for p, d in self.entity_type(entity_type).properties.items() if d.searchable]

    def validate_relationship(self, rel_type: str, source_type: str, target_type: str) -> None:
        rdef = self.relationship_types.get(rel_type)
        if rdef is None:
            raise OntologyError(f"Unknown relationship type: {rel_type}")
        if "*" not in rdef.source_types and source_type not in rdef.source_types:
            raise OntologyError(f"{rel_type} cannot originate from {source_type}")
        if "*" not in rdef.target_types and target_type not in rdef.target_types:
            raise OntologyError(f"{rel_type} cannot target {target_type}")

    def validate_properties(self, entity_type: str, props: dict[str, Any], strict: bool = False) -> dict[str, Any]:
        """Coerce known properties; unknown properties are kept under `_extra` unless strict."""
        tdef = self.entity_type(entity_type)
        clean: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for key, value in props.items():
            if value is None or value == "":
                continue
            pdef = tdef.properties.get(key)
            if pdef is None:
                if strict:
                    raise OntologyError(f"Property {key} is not defined for {entity_type}")
                extra[key] = value
                continue
            clean[key] = _coerce(value, pdef.type, key)
        if extra:
            clean["_extra"] = extra
        return clean


class OntologyError(ValueError):
    pass


def _coerce(value: Any, ptype: str, key: str) -> Any:
    try:
        if ptype == "number":
            return float(value)
        if ptype == "integer":
            return int(value)
        if ptype == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"1", "true", "yes", "y"}
        return str(value) if not isinstance(value, str) else value
    except (TypeError, ValueError) as exc:
        raise OntologyError(f"Property {key}: cannot coerce {value!r} to {ptype}") from exc


_lock = threading.Lock()
_cached: Ontology | None = None


def load_ontology(path: Path | None = None) -> Ontology:
    from app.config import get_settings

    path = path or get_settings().ontology_path
    return Ontology.model_validate(json.loads(Path(path).read_text()))


def get_ontology() -> Ontology:
    global _cached
    with _lock:
        if _cached is None:
            _cached = load_ontology()
        return _cached


def set_ontology(onto: Ontology) -> None:
    global _cached
    with _lock:
        _cached = onto
