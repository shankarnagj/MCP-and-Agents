"""Parquet connector (row-group streaming via pyarrow)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from app.ingestion.base import Connector, RawRecord


class ParquetConnector(Connector):
    kind = "parquet"

    def __init__(self, path: str | Path, record_type: str, id_field: str | None = None, batch_size: int = 5000) -> None:
        super().__init__(record_type, id_field)
        self.path = Path(path)
        self.batch_size = batch_size

    def iter_records(self) -> Iterator[RawRecord]:
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(self.path)
        i = 0
        for batch in pf.iter_batches(batch_size=self.batch_size):
            for row in batch.to_pylist():
                yield self._make(i, row)
                i += 1

    def describe(self) -> dict:
        return {**super().describe(), "path": str(self.path)}
