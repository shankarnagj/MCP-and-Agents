"""Load the synthetic demonstration dataset through the real ingestion pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.entity_resolution.service import resolve_type
from app.ingestion.csv import CSVConnector
from app.ingestion.json import JSONConnector, JSONLConnector
from app.ingestion.mapping import load_mappings
from app.ingestion.parquet import ParquetConnector
from app.ingestion.pipeline import ensure_source, refresh_statistics, run_ingestion
from app.models import SYNTHETIC_LABEL
from app.ontology import get_ontology

log = logging.getLogger("tessera.demo")


def build_connector(spec: dict, base: Path):  # noqa: ANN201
    path = base / spec["path"]
    kind = spec["kind"]
    if kind == "csv":
        return CSVConnector(path, spec["record_type"], spec.get("id_field"))
    if kind == "jsonl":
        return JSONLConnector(path, spec["record_type"], spec.get("id_field"))
    if kind == "json":
        return JSONConnector(path, spec["record_type"], spec.get("id_field"), spec.get("items_path"))
    if kind == "parquet":
        return ParquetConnector(path, spec["record_type"], spec.get("id_field"))
    raise ValueError(f"unsupported demo source kind {kind}")


def load_demo(db: Session, data_dir: Path | None = None, only: set[str] | None = None) -> dict:
    settings = get_settings()
    data_dir = data_dir or settings.synthetic_dir
    schemas = settings.ontology_path.parent
    ontology = get_ontology()
    mappings = load_mappings(schemas / "mappings.json")
    sources = json.loads((schemas / "sources.json").read_text())["sources"]
    report: dict = {"ingestion": [], "entity_resolution": [], "results": []}
    for spec in sources:
        if only and spec["source_id"] not in only:
            continue
        src = ensure_source(db, spec["source_id"], spec["name"], spec["kind"], description=spec.get("description", ""),
                            classification=SYNTHETIC_LABEL, config={k: v for k, v in spec.items() if k in ("path", "record_type", "id_field", "items_path")})
        res = run_ingestion(db, ontology, src, build_connector(spec, data_dir), mappings[spec["record_type"]])
        db.commit()
        report["ingestion"].append(res.summary())
        report["results"].append(res)
    for etype in ("Person", "Organization"):
        report["entity_resolution"].append(resolve_type(db, ontology, etype).to_dict())
        db.commit()
    refresh_statistics(db)
    db.commit()
    return report
