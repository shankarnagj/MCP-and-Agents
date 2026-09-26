"""CSV connector (streaming; never loads the whole file)."""

from __future__ import annotations

import csv as _csv
from collections.abc import Iterator
from pathlib import Path

from app.ingestion.base import Connector, RawRecord


class CSVConnector(Connector):
    kind = "csv"

    def __init__(self, path: str | Path, record_type: str, id_field: str | None = None, delimiter: str = ",", encoding: str = "utf-8") -> None:
        super().__init__(record_type, id_field)
        self.path = Path(path)
        self.delimiter = delimiter
        self.encoding = encoding

    def iter_records(self) -> Iterator[RawRecord]:
        with self.path.open(newline="", encoding=self.encoding) as fh:
            reader = _csv.DictReader(fh, delimiter=self.delimiter)
            for i, row in enumerate(reader):
                yield self._make(i, {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k})

    def describe(self) -> dict:
        return {**super().describe(), "path": str(self.path)}
