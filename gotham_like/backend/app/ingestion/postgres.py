"""PostgreSQL connector.

Reads from an external PostgreSQL table/view with a server-side cursor. The table
and column names are validated identifiers and quoted by SQLAlchemy; filter values
are bound parameters — no string-built SQL. The DSN is a secret and is expected to
be supplied decrypted from `DataSource.secret_encrypted` at run time.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from sqlalchemy import column, create_engine, literal_column, select, table

from app.ingestion.base import Connector, RawRecord

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"invalid SQL identifier: {name!r}")
    return name


class PostgresConnector(Connector):
    kind = "postgres"

    def __init__(
        self,
        dsn: str,
        table_name: str,
        record_type: str,
        id_field: str | None = None,
        columns: list[str] | None = None,
        schema: str | None = None,
        equals_filters: dict[str, Any] | None = None,
        limit: int | None = None,
        batch_size: int = 2000,
    ) -> None:
        super().__init__(record_type, id_field)
        self._dsn = dsn
        self.table_name = _ident(table_name)
        self.schema = _ident(schema) if schema else None
        self.columns = [_ident(c) for c in columns] if columns else None
        self.equals_filters = {_ident(k): v for k, v in (equals_filters or {}).items()}
        self.limit = limit
        self.batch_size = batch_size

    def build_query(self):  # noqa: ANN201
        names = list(dict.fromkeys((self.columns or []) + list(self.equals_filters) + ([self.id_field] if self.id_field else [])))
        t = table(self.table_name, *[column(_ident(c)) for c in names], schema=self.schema)
        stmt = select(*[t.c[c] for c in self.columns]) if self.columns else select(literal_column("*")).select_from(t)
        for key, value in self.equals_filters.items():
            stmt = stmt.where(t.c[key] == value)  # bound parameter
        if self.id_field:
            stmt = stmt.order_by(t.c[self.id_field])
        if self.limit:
            stmt = stmt.limit(int(self.limit))
        return stmt

    def iter_records(self) -> Iterator[RawRecord]:
        engine = create_engine(self._dsn, future=True)
        try:
            with engine.connect().execution_options(stream_results=True, yield_per=self.batch_size) as conn:
                result = conn.execute(self.build_query())
                for i, row in enumerate(result.mappings()):
                    yield self._make(i, dict(row))
        finally:
            engine.dispose()

    def describe(self) -> dict:
        # Never include the DSN (secret) in descriptions / provenance.
        return {**super().describe(), "table": self.table_name, "schema": self.schema}
