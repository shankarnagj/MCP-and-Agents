"""JSON and JSON Lines connectors."""

from __future__ import annotations

import json as _json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.ingestion.base import Connector, RawRecord


def _dig(obj: Any, path: str | None) -> Any:
    if not path:
        return obj
    for part in path.split("."):
        obj = obj[part]
    return obj


class JSONConnector(Connector):
    """A JSON document whose `items_path` (dotted) is an array of objects."""

    kind = "json"

    def __init__(self, path: str | Path, record_type: str, id_field: str | None = None, items_path: str | None = None) -> None:
        super().__init__(record_type, id_field)
        self.path = Path(path)
        self.items_path = items_path

    def iter_records(self) -> Iterator[RawRecord]:
        data = _dig(_json.loads(self.path.read_text()), self.items_path)
        if not isinstance(data, list):
            raise ValueError("JSON items_path must point to an array")
        for i, row in enumerate(data):
            if isinstance(row, dict):
                yield self._make(i, row)

    def describe(self) -> dict:
        return {**super().describe(), "path": str(self.path), "items_path": self.items_path}


class JSONLConnector(Connector):
    kind = "jsonl"

    def __init__(self, path: str | Path, record_type: str, id_field: str | None = None) -> None:
        super().__init__(record_type, id_field)
        self.path = Path(path)

    def iter_records(self) -> Iterator[RawRecord]:
        with self.path.open() as fh:
            for i, line in enumerate(fh):
                line = line.strip()
                if line:
                    yield self._make(i, _json.loads(line))

    def describe(self) -> dict:
        return {**super().describe(), "path": str(self.path)}
