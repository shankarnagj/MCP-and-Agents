"""Search query language.

    John Smith                 fuzzy free text (trigram word-similarity)
    "John Smith"               exact phrase
    Joh*                       prefix
    ~Jhon                      explicitly fuzzy (lower threshold)
    account:12345              identifier lookup (normalised; also matches source keys)
    device:ABC123  ip:10.10.10.10  email:a@b.example  phone:+1...  domain:x.example
    company:Acme   org:Acme    person:"Jane Doe"     type-scoped name search
    type:Person    -type:Transaction                 entity-type filter / exclusion
    city:Marisk    jurisdiction:"Castellan Isles"    ontology property filter
    after:2026-01-01  before:2026-02-01  on:2026-02-14   date filter (observed_at)
    near:51.45,3.60,2km                              geographic radius filter
    bbox:minLon,minLat,maxLon,maxLat                 geographic box filter

The parser is pure (no database access) and never builds SQL text; the search
service turns the parsed structure into bound-parameter SQLAlchemy expressions.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

# alias -> (identifier kinds, entity types)
IDENTIFIER_ALIASES: dict[str, tuple[list[str], list[str]]] = {
    "account": (["account", "key"], ["Account"]),
    "acct": (["account", "key"], ["Account"]),
    "device": (["device", "device_fp", "key"], ["Device"]),
    "ip": (["ip", "key"], ["IPAddress"]),
    "email": (["email"], []),
    "phone": (["phone"], []),
    "domain": (["domain", "key"], ["Domain"]),
    "txn": (["transaction", "key"], ["Transaction"]),
    "transaction": (["transaction", "key"], ["Transaction"]),
    "shipment": (["shipment", "key"], ["Shipment"]),
    "imo": (["imo"], ["Vessel"]),
    "plate": (["plate"], ["Vehicle"]),
    "reg": (["org_reg"], ["Organization"]),
    "id": (["key"], []),
}
TYPE_ALIASES: dict[str, str] = {
    "company": "Organization", "org": "Organization", "organization": "Organization", "person": "Person",
    "location": "Location", "vessel": "Vessel", "place": "Location",
}
_GEO_NEAR = re.compile(r"^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),(\d+(?:\.\d+)?)(m|km)?$")
_BBOX = re.compile(r"^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$")
MAX_QUERY_LENGTH = 500
MAX_TERMS = 20


@dataclass
class TextTerm:
    text: str
    mode: str  # fuzzy | exact | prefix | loose
    field: str | None = None  # None = search_text


@dataclass
class IdentifierTerm:
    alias: str
    kinds: list[str]
    value: str
    prefix: bool = False


@dataclass
class ParsedQuery:
    raw: str
    text_terms: list[TextTerm] = field(default_factory=list)
    identifiers: list[IdentifierTerm] = field(default_factory=list)
    include_types: list[str] = field(default_factory=list)
    exclude_types: list[str] = field(default_factory=list)
    property_filters: list[tuple[str, str]] = field(default_factory=list)
    date_from: datetime | None = None
    date_to: datetime | None = None
    near: tuple[float, float, float] | None = None  # lat, lon, meters
    bbox: tuple[float, float, float, float] | None = None
    warnings: list[str] = field(default_factory=list)

    def describe(self) -> dict:
        return {
            "text_terms": [t.__dict__ for t in self.text_terms],
            "identifiers": [i.__dict__ for i in self.identifiers],
            "include_types": self.include_types,
            "exclude_types": self.exclude_types,
            "property_filters": self.property_filters,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "near": self.near,
            "bbox": self.bbox,
            "warnings": self.warnings,
        }


class QueryParseError(ValueError):
    pass


def _parse_date(value: str) -> datetime:
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QueryParseError(f"invalid date: {value!r}") from exc
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _tokens(q: str) -> list[str]:
    try:
        lex = shlex.shlex(q, posix=True)
        lex.whitespace_split = True
        lex.commenters = ""
        lex.escape = ""
        return list(lex)
    except ValueError:
        # unbalanced quotes: fall back to whitespace split without quotes
        return q.replace('"', " ").split()


def parse(q: str, entity_types: set[str], property_names: set[str]) -> ParsedQuery:
    q = (q or "").strip()
    if len(q) > MAX_QUERY_LENGTH:
        raise QueryParseError(f"query longer than {MAX_QUERY_LENGTH} characters")
    pq = ParsedQuery(raw=q)
    # Detect quoted phrases before shlex strips the quotes
    phrases = set(re.findall(r'(?<![:\w])"([^"]+)"', q))
    tokens = _tokens(q)
    if len(tokens) > MAX_TERMS:
        raise QueryParseError(f"too many terms (max {MAX_TERMS})")
    for tok in tokens:
        if not tok:
            continue
        negate = tok.startswith("-") and ":" in tok
        body = tok[1:] if negate else tok
        key, sep, value = body.partition(":")
        key_l = key.lower()
        if sep and value and not key_l.startswith("http"):
            if key_l == "type":
                t = _match_type(value, entity_types)
                if t is None:
                    raise QueryParseError(f"unknown entity type: {value}")
                (pq.exclude_types if negate else pq.include_types).append(t)
            elif key_l in IDENTIFIER_ALIASES:
                kinds, types = IDENTIFIER_ALIASES[key_l]
                prefix = value.endswith("*")
                pq.identifiers.append(IdentifierTerm(key_l, kinds, value.rstrip("*"), prefix))
                for t in types:
                    if t not in pq.include_types:
                        pq.include_types.append(t)
            elif key_l in TYPE_ALIASES:
                pq.include_types.append(TYPE_ALIASES[key_l])
                mode = "prefix" if value.endswith("*") else "fuzzy"
                pq.text_terms.append(TextTerm(value.rstrip("*"), mode))
            elif key_l in ("after", "from", "since"):
                pq.date_from = _parse_date(value)
            elif key_l in ("before", "to", "until"):
                pq.date_to = _parse_date(value)
            elif key_l == "on":
                d = _parse_date(value)
                pq.date_from, pq.date_to = d, d + timedelta(days=1)
            elif key_l == "near":
                m = _GEO_NEAR.match(value)
                if not m:
                    raise QueryParseError("near: expects lat,lon,radius[m|km]")
                lat, lon, r, unit = float(m.group(1)), float(m.group(2)), float(m.group(3)), m.group(4) or "m"
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise QueryParseError("near: coordinates out of range")
                pq.near = (lat, lon, min(r * (1000 if unit == "km" else 1), 500_000))
            elif key_l == "bbox":
                m = _BBOX.match(value)
                if not m:
                    raise QueryParseError("bbox: expects minLon,minLat,maxLon,maxLat")
                pq.bbox = tuple(float(x) for x in m.groups())  # type: ignore[assignment]
            elif key in property_names:
                pq.property_filters.append((key, value))
            else:
                pq.warnings.append(f"unknown field '{key}' treated as text")
                pq.text_terms.append(TextTerm(body, "fuzzy"))
            continue
        if tok in phrases or (" " in tok):
            pq.text_terms.append(TextTerm(tok, "exact"))
        elif tok.endswith("*") and len(tok) > 1:
            pq.text_terms.append(TextTerm(tok[:-1], "prefix"))
        elif tok.startswith("~") and len(tok) > 1:
            pq.text_terms.append(TextTerm(tok[1:], "loose"))
        else:
            pq.text_terms.append(TextTerm(tok, "fuzzy"))
    # merge consecutive plain fuzzy words into one phrase-like fuzzy term ("John Smith")
    merged: list[TextTerm] = []
    for t in pq.text_terms:
        if merged and t.mode == "fuzzy" and merged[-1].mode == "fuzzy" and t.field is None and merged[-1].field is None:
            merged[-1] = TextTerm(merged[-1].text + " " + t.text, "fuzzy")
        else:
            merged.append(t)
    pq.text_terms = merged
    return pq


def _match_type(value: str, entity_types: set[str]) -> str | None:
    for t in entity_types:
        if t.lower() == value.lower():
            return t
    return TYPE_ALIASES.get(value.lower())
