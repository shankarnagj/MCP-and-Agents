"""Entity search over PostgreSQL (pg_trgm + identifier index + PostGIS)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import and_, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.entity_resolution import normalize as N
from app.models import Entity, EntityIdentifier
from app.ontology import Ontology
from app.privacy.masking import can_view
from app.search.parser import ParsedQuery, QueryParseError, parse
from app.services.serialize import entity_dict

FUZZY_THRESHOLD = 0.45
LOOSE_THRESHOLD = 0.3


@dataclass
class SearchRequest:
    query: str = ""
    entity_types: list[str] | None = None
    date_from: Any = None
    date_to: Any = None
    near: tuple[float, float, float] | None = None
    limit: int = 50
    offset: int = 0


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(db: Session, ontology: Ontology, req: SearchRequest, role: str) -> dict[str, Any]:
    pq = parse(req.query, set(ontology.entity_types), ontology.all_property_names())
    if req.entity_types:
        for t in req.entity_types:
            if t not in ontology.entity_types:
                raise QueryParseError(f"unknown entity type: {t}")
        pq.include_types = list(dict.fromkeys(pq.include_types + req.entity_types))
    pq.date_from = pq.date_from or req.date_from
    pq.date_to = pq.date_to or req.date_to
    pq.near = pq.near or req.near

    e = Entity
    conds = [e.merged_into.is_(None), e.deleted_at.is_(None)]
    score_parts: list[Any] = []
    reasons: list[str] = []

    for ident in pq.identifiers:
        kinds = ident.kinds
        norms = {N.normalize_identifier(k, ident.value) or N.identifier(ident.value) for k in kinds}
        norms |= {N.identifier(ident.value)}
        norms.discard("")
        if not norms:
            raise QueryParseError(f"cannot normalise identifier {ident.alias}:{ident.value}")
        sub = select(EntityIdentifier.entity_id).where(EntityIdentifier.kind.in_(kinds))
        if ident.prefix:
            sub = sub.where(or_(*[EntityIdentifier.value.like(_escape_like(n) + "%") for n in norms]))
            reasons.append(f"{ident.alias} prefix '{ident.value}*'")
        else:
            sub = sub.where(EntityIdentifier.value.in_(norms))
            reasons.append(f"{ident.alias} exact identifier match")
        conds.append(e.id.in_(sub))
        score_parts.append(literal(1.0))

    for term in pq.text_terms:
        norm = N.basic(term.text)
        if not norm:
            continue
        if term.mode == "exact":
            conds.append(e.search_text.ilike(f"%{_escape_like(norm)}%"))
            score_parts.append(func.similarity(e.search_text, norm) * 0.2 + 0.8)
            reasons.append(f"exact phrase '{term.text}'")
        elif term.mode == "prefix":
            p = _escape_like(norm)
            conds.append(or_(e.search_text.ilike(f"{p}%"), e.search_text.ilike(f"% {p}%"), func.lower(e.label).like(f"{p.lower()}%")))
            score_parts.append(func.word_similarity(norm, e.search_text))
            reasons.append(f"prefix '{term.text}*'")
        else:
            threshold = LOOSE_THRESHOLD if term.mode == "loose" else FUZZY_THRESHOLD
            ws = func.word_similarity(norm, e.search_text)
            # `<%` uses the GIN trigram index; the explicit threshold keeps results tight
            conds.append(and_(literal(norm).op("<%")(e.search_text), ws >= threshold))
            score_parts.append(ws)
            reasons.append(f"fuzzy '{term.text}' (trigram word-similarity ≥ {threshold})")

    if pq.include_types:
        conds.append(e.type.in_(pq.include_types))
    if pq.exclude_types:
        conds.append(e.type.not_in(pq.exclude_types))
    denied: list[str] = []
    for prop, value in pq.property_filters:
        # Filtering on a field you may not see would leak it by inference: refuse.
        sens = max((ontology.sensitivity(t, prop) for t in ontology.entity_types if ontology.has_property(t, prop)),
                   key=lambda s: {"public": 0, "pii": 1, "restricted": 2}[s], default="public")
        if not can_view(role, sens):
            denied.append(prop)
            continue
        conds.append(e.properties[prop].astext.ilike(_escape_like(value).replace("*", "%")))
        reasons.append(f"{prop} = '{value}'")
    if denied:
        pq.warnings.append(f"filters on protected fields ignored: {', '.join(denied)}")
    if pq.date_from is not None:
        conds.append(e.observed_at >= pq.date_from)
    if pq.date_to is not None:
        conds.append(e.observed_at < pq.date_to)
    if pq.near:
        lat, lon, meters = pq.near
        point = cast(func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), Geography)
        conds.append(func.ST_DWithin(e.geom, point, meters))
        reasons.append(f"within {meters:.0f} m of ({lat}, {lon})")
    if pq.bbox:
        min_lon, min_lat, max_lon, max_lat = pq.bbox
        conds.append(func.ST_Intersects(e.geom, cast(func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326), Geography)))

    if len(conds) == 2:
        raise QueryParseError("empty query: provide text, an identifier, or a filter")

    score = score_parts[0] if score_parts else literal(0.5)
    for sp in score_parts[1:]:
        score = score + sp
    score = (score / max(len(score_parts), 1)).label("score")
    limit = max(1, min(int(req.limit), 200))
    offset = max(0, int(req.offset))
    q = select(e, score).where(*conds).order_by(score.desc(), e.label, e.id).limit(limit).offset(offset)
    rows = db.execute(q).all()

    facet_q = select(e.type, func.count()).where(*conds).group_by(e.type)
    capped = select(e.id, e.type).where(*conds).limit(10000).subquery()
    facet_q = select(capped.c.type, func.count()).group_by(capped.c.type)
    facets = {t: c for t, c in db.execute(facet_q).all()}
    results = []
    for ent, sc in rows:
        d = entity_dict(ent, ontology, role, full=False)
        d["score"] = round(float(sc), 4)
        d["preview"] = {k: v for k, v in entity_dict(ent, ontology, role)["properties"].items() if not k.startswith("_")}
        results.append(d)
    return {
        "query": req.query,
        "parsed": pq.describe(),
        "results": results,
        "total_estimate": sum(facets.values()),
        "facets": {"type": facets},
        "limit": limit,
        "offset": offset,
        "match_reasons": reasons,
        "note": "Search ranks by textual/identifier similarity only. A match is a retrieval result, not an identity assertion.",
    }
