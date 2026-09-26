"""Connector contract.

Every connector yields `RawRecord`s — the payload exactly as received plus a stable
source-side identifier. Connectors never interpret data; interpretation happens in
the declarative mapping layer so that it is versioned and auditable.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RawRecord:
    source_record_id: str
    record_type: str
    payload: dict[str, Any]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.payload, sort_keys=True, default=str).encode()).hexdigest()


def jsonable(value: Any) -> Any:
    """Make connector output JSON-safe (Parquet/Postgres produce dates, decimals, ...)."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


class Connector(ABC):
    kind: str = "abstract"

    def __init__(self, record_type: str, id_field: str | None = None) -> None:
        self.record_type = record_type
        self.id_field = id_field

    def _make(self, index: int, row: dict[str, Any]) -> RawRecord:
        payload = jsonable(row)
        if self.id_field and payload.get(self.id_field) not in (None, ""):
            rid = str(payload[self.id_field])
        else:
            # Content-addressed fallback id keeps re-ingestion idempotent.
            rid = f"row-{index}-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        return RawRecord(rid, self.record_type, payload)

    @abstractmethod
    def iter_records(self) -> Iterator[RawRecord]: ...

    def describe(self) -> dict[str, Any]:
        return {"kind": self.kind, "record_type": self.record_type, "id_field": self.id_field}
