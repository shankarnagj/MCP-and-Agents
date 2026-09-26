"""REST API connector with page/cursor pagination."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

from app.ingestion.base import Connector, RawRecord
from app.ingestion.json import _dig


class RESTConnector(Connector):
    kind = "api"

    def __init__(
        self,
        url: str,
        record_type: str,
        id_field: str | None = None,
        items_path: str | None = "items",
        headers: dict[str, str] | None = None,  # may include secrets; not described
        params: dict[str, Any] | None = None,
        next_cursor_path: str | None = None,
        cursor_param: str = "cursor",
        max_pages: int = 1000,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(record_type, id_field)
        if not url.startswith(("https://", "http://")):
            raise ValueError("only http(s) URLs are supported")
        self.url = url
        self.items_path = items_path
        self._headers = headers or {}
        self.params = dict(params or {})
        self.next_cursor_path = next_cursor_path
        self.cursor_param = cursor_param
        self.max_pages = max_pages
        self.timeout = timeout
        self._transport = transport

    def iter_records(self) -> Iterator[RawRecord]:
        params = dict(self.params)
        i = 0
        with httpx.Client(timeout=self.timeout, headers=self._headers, transport=self._transport) as client:
            for _ in range(self.max_pages):
                resp = client.get(self.url, params=params)
                resp.raise_for_status()
                body = resp.json()
                items = _dig(body, self.items_path) if self.items_path else body
                for row in items or []:
                    yield self._make(i, row)
                    i += 1
                if not self.next_cursor_path:
                    break
                try:
                    cursor = _dig(body, self.next_cursor_path)
                except (KeyError, TypeError):
                    cursor = None
                if not cursor:
                    break
                params[self.cursor_param] = cursor

    def describe(self) -> dict:
        return {**super().describe(), "url": self.url, "items_path": self.items_path}
