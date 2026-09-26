"""Database-backed entity resolution run: blocking → pairwise comparison → merge (MATCH only).

* MATCH           → entities merged (reversibly); merge recorded as SYSTEM_INFERENCE with evidence.
* POSSIBLE_MATCH  → stored for analyst review; never merged automatically.
* NO_MATCH        → not stored (except when explicitly compared through the API).
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.entity_resolution.resolver import RESOLVER_VERSION, MatchResult, blocking_keys, compare
from app.models import Entity, EntityIdentifier, Event, LineageLink, Relationship, ResolutionCandidate, ResolutionDecision, utcnow
from app.ontology import Ontology

log = logging.getLogger("tessera.er")

MAX_BLOCK = 60  # oversize blocks (very common tokens) are skipped to bound cost


@dataclass
class ResolutionStats:
    entity_type: str
    entities: int = 0
    pairs_compared: int = 0
    matches: int = 0
    possible_matches: int = 0
    merged: int = 0
    skipped_blocks: int = 0
    merges: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "merges"} | {"merge_examples": self.merges[:10]}


def _pair_id(a: str, b: str) -> str:
    return "res_" + hashlib.sha1(f"{a}|{b}".encode(), usedforsecurity=False).hexdigest()[:20]


def active_entities(entity_type: str):  # noqa: ANN201
    return select(Entity).where(Entity.type == entity_type, Entity.merged_into.is_(None), Entity.deleted_at.is_(None))


def resolve_type(db: Session, ontology: Ontology, entity_type: str, merge: bool = True) -> ResolutionStats:
    stats = ResolutionStats(entity_type)
    ents = {e.id: e for e in db.scalars(active_entities(entity_type))}
    stats.entities = len(ents)
    blocks: dict[str, list[str]] = defaultdict(list)
    for e in ents.values():
        for k in blocking_keys(ontology, entity_type, e.properties):
            blocks[k].append(e.id)
    pairs: set[tuple[str, str]] = set()
    for members in blocks.values():
        if len(members) < 2:
            continue
        if len(members) > MAX_BLOCK:
            stats.skipped_blocks += 1
            continue
        ms = sorted(members)
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                pairs.add((ms[i], ms[j]))
    results: list[tuple[str, str, MatchResult]] = []
    for a, b in sorted(pairs):
        stats.pairs_compared += 1
        r = compare(ontology, entity_type, ents[a].properties, ents[b].properties)
        if r.decision != ResolutionDecision.NO_MATCH:
            results.append((a, b, r))
    rows = []
    for a, b, r in results:
        if r.decision == ResolutionDecision.MATCH:
            stats.matches += 1
        else:
            stats.possible_matches += 1
        rows.append(
            dict(
                id=_pair_id(a, b), entity_type=entity_type, entity_a=a, entity_b=b, decision=r.decision.value,
                score=round(r.score, 4), evidence=r.to_dict()["evidence"], resolver_version=RESOLVER_VERSION,
                review_status="UNREVIEWED", merged=False, created_at=utcnow(),
            )
        )
    for chunk_start in range(0, len(rows), 1000):
        stmt = pg_insert(ResolutionCandidate).values(rows[chunk_start : chunk_start + 1000])
        stmt = stmt.on_conflict_do_update(
            constraint="uq_resolution_pair",
            set_={"decision": stmt.excluded.decision, "score": stmt.excluded.score, "evidence": stmt.excluded.evidence,
                  "resolver_version": stmt.excluded.resolver_version},
        )
        db.execute(stmt)
    db.flush()
    if merge:
        # union-find over MATCH pairs so chains (A~B, B~C) collapse into one canonical entity
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.get(x, x) != x:
                x = parent[x]
            return x

        match_pairs = [(a, b, r) for a, b, r in results if r.decision == ResolutionDecision.MATCH]
        for a, b, _ in match_pairs:
            ra, rb = find(a), find(b)
            if ra != rb:
                # canonical = the entity backed by more source records (stable tie-break on id)
                keep = max(ra, rb, key=lambda x: (len(ents[x].source_ids), x))
                drop = rb if keep == ra else ra
                parent[drop] = keep
                parent.setdefault(keep, keep)
        for a, b, r in match_pairs:
            canon = find(a)
            for dup in (a, b):
                if dup != canon and ents[dup].merged_into is None:
                    info = merge_entities(db, ents[canon], ents[dup], r)
                    stats.merged += 1
                    stats.merges.append(info)
    db.flush()
    log.info("entity_resolution", extra={"stats": stats.to_dict()})
    return stats


def merge_entities(db: Session, canon: Entity, dup: Entity, result: MatchResult, actor: str = "system") -> dict:
    before = {"properties": dict(canon.properties), "source_ids": list(canon.source_ids), "confidence": canon.confidence,
              "search_text": canon.search_text}
    moved_src = [r for (r,) in db.execute(update(Relationship).where(Relationship.source_id == dup.id).values(source_id=canon.id).returning(Relationship.id))]
    moved_tgt = [r for (r,) in db.execute(update(Relationship).where(Relationship.target_id == dup.id).values(target_id=canon.id).returning(Relationship.id))]
    moved_evt = [
        r
        for (r,) in db.execute(
            update(Event)
            .where(Event.entity_ids.contains([dup.id]))
            .values(entity_ids=func.array_replace(Event.entity_ids, dup.id, canon.id))
            .returning(Event.id)
        )
    ]
    for kind, value in db.execute(select(EntityIdentifier.kind, EntityIdentifier.value).where(EntityIdentifier.entity_id == dup.id)).all():
        db.execute(pg_insert(EntityIdentifier).values(entity_id=canon.id, kind=kind, value=value).on_conflict_do_nothing(constraint="uq_identifier"))

    props = dict(canon.properties)
    alternates: dict[str, list] = dict(props.get("_alternates", {}))
    for k, v in dup.properties.items():
        if k.startswith("_"):
            continue
        if k not in props:
            props[k] = v
        elif props[k] != v:
            alternates.setdefault(k, [])
            if v not in alternates[k]:
                alternates[k].append(v)
    if alternates:
        props["_alternates"] = alternates
    canon.properties = props
    canon.source_ids = sorted(set(canon.source_ids) | set(dup.source_ids))
    canon.search_text = " ".join(dict.fromkeys((canon.search_text + " " + dup.search_text).split()))
    canon.confidence = round(min(canon.confidence, result.score), 4)
    if canon.lat is None and dup.lat is not None:
        canon.lat, canon.lon, canon.geom = dup.lat, dup.lon, dup.geom
    resolution = list(canon.provenance.get("resolution", []))
    resolution.append(
        {"merged": dup.id, "score": round(result.score, 4), "decision": result.decision.value, "epistemic_status": "SYSTEM_INFERENCE",
         "resolver_version": result.resolver_version, "reasons": result.reasons(), "by": actor, "at": utcnow().isoformat()}
    )
    canon.provenance = {**canon.provenance, "resolution": resolution}
    dup.merged_into = canon.id
    db.add(
        LineageLink(
            child_kind="entity", child_id=canon.id, parent_kind="entity", parent_id=dup.id,
            transformation="entity_resolution.merge", transformation_version=result.resolver_version,
            details={"match": result.to_dict(), "moved_relationships_source": moved_src, "moved_relationships_target": moved_tgt,
                     "moved_events": moved_evt, "canonical_before": before,
                     "by": actor},
        )
    )
    a, b = sorted([canon.id, dup.id])
    db.execute(update(ResolutionCandidate).where(ResolutionCandidate.entity_a == a, ResolutionCandidate.entity_b == b).values(merged=True))
    return {"canonical": canon.id, "merged": dup.id, "score": round(result.score, 4), "reasons": result.reasons()}


def unmerge(db: Session, dup_id: str, actor: str) -> dict:
    """Reverse a merge using the lineage record (analyst correction)."""
    dup = db.get(Entity, dup_id)
    if dup is None or dup.merged_into is None:
        raise ValueError("entity is not merged")
    canon = db.get(Entity, dup.merged_into)
    # Merges are undone in reverse order: restoring the canonical's pre-merge snapshot is only
    # correct for the most recent merge that is still in effect.
    active = db.scalars(
        select(LineageLink)
        .join(Entity, Entity.id == LineageLink.parent_id)
        .where(LineageLink.child_id == canon.id, LineageLink.transformation == "entity_resolution.merge", Entity.merged_into == canon.id)
        .order_by(LineageLink.id.desc())
    ).all()
    link = next((lk for lk in active if lk.parent_id == dup.id), None)
    if link is None:
        raise ValueError("merge lineage not found")
    if active[0].parent_id != dup.id:
        raise ValueError(f"unmerge {active[0].parent_id} first (merges are reversed newest-first)")
    d = link.details
    if d.get("moved_relationships_source"):
        db.execute(update(Relationship).where(Relationship.id.in_(d["moved_relationships_source"])).values(source_id=dup.id))
    if d.get("moved_relationships_target"):
        db.execute(update(Relationship).where(Relationship.id.in_(d["moved_relationships_target"])).values(target_id=dup.id))
    if d.get("moved_events"):
        db.execute(
            update(Event).where(Event.id.in_(d["moved_events"])).values(entity_ids=func.array_replace(Event.entity_ids, canon.id, dup.id))
        )
    before = d.get("canonical_before") or {}
    if before:
        canon.properties = before["properties"]
        canon.source_ids = before["source_ids"]
        canon.confidence = before["confidence"]
        canon.search_text = before["search_text"]
    canon.provenance = {
        **canon.provenance,
        "resolution": [r for r in canon.provenance.get("resolution", []) if r.get("merged") != dup.id],
    }
    dup.merged_into = None
    a, b = sorted([canon.id, dup.id])
    db.execute(
        update(ResolutionCandidate)
        .where(ResolutionCandidate.entity_a == a, ResolutionCandidate.entity_b == b)
        .values(merged=False, review_status="REJECTED", reviewed_by=actor)
    )
    db.add(
        LineageLink(child_kind="entity", child_id=dup.id, parent_kind="entity", parent_id=canon.id,
                    transformation="entity_resolution.unmerge", transformation_version=RESOLVER_VERSION, details={"by": actor})
    )
    db.flush()
    return {"restored": dup.id, "canonical": canon.id}
