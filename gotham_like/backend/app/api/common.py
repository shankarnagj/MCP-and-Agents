from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, Request

from app.auth.deps import Principal, client_ip
from app.ingestion.mapping import parse_ts
from app.ontology import Ontology, get_ontology


def onto() -> Ontology:
    return get_ontology()


def ip_of(request: Request) -> str:
    return client_ip(request)


def ts_param(value: str | None, name: str) -> datetime | None:
    if value in (None, ""):
        return None
    dt = parse_ts(value)
    if dt is None:
        raise HTTPException(422, f"invalid timestamp for {name}")
    return dt


def not_found(what: str) -> HTTPException:
    return HTTPException(404, f"{what} not found")


def forbid(detail: str) -> HTTPException:
    return HTTPException(403, detail)


__all__ = ["Principal", "onto", "ip_of", "ts_param", "not_found", "forbid"]
