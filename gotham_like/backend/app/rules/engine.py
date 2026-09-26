"""Deterministic rule engine producing ANALYTICAL SIGNALS and (optionally) alerts.

Design rules:
  * A rule never labels an entity (no "fraudulent", "guilty", "malicious").
  * Every signal carries: what happened, why it was shown, supporting data, when the
    data was collected, assumptions, uncertainty and alternative explanations.
  * Scores are rule-specific magnitudes (observed / threshold), not probabilities.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import networkx as nx
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ingestion.mapping import entity_id as natural_entity_id
from app.models import SIGNAL_LABEL, Alert, Entity, Geofence, Relationship, Rule, Signal, SourceRecord, new_id, utcnow
from app.observability import ALERTS_RAISED

log = logging.getLogger("tessera.rules")

RULE_KINDS = {"threshold", "unusual_count", "cycle", "event", "sequence", "geofence", "new_relationship", "source_change"}
_OPS = {">": ">", ">=": ">="}
FORBIDDEN_WORDS = ("fraud", "guilty", "criminal", "malicious", "launder", "terror", "verdict")


@dataclass
class SignalDraft:
    key: str
    entity_ids: list[str]
    score: float
    evidence: list[dict[str, Any]]
    what: str
    window_start: datetime | None = None
    window_end: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def validate_rule_definition(kind: str, name: str, description: str, definition: dict[str, Any]) -> None:
    if kind not in RULE_KINDS:
        raise ValueError(f"unknown rule kind {kind}")
    text_blob = f"{name} {description}".lower()
    for w in FORBIDDEN_WORDS:
        if w in text_blob:
            raise ValueError(f"rule text must describe observable conditions, not conclusions (found '{w}')")
    if kind == "threshold":
        for k in ("target_type", "relationship_type", "neighbor_type", "window_days", "op", "value"):
            if k not in definition:
                raise ValueError(f"threshold rule requires '{k}'")
        if definition["op"] not in _OPS:
            raise ValueError("op must be > or >=")
        if definition.get("direction", "in") not in ("in", "out"):
            raise ValueError("direction must be in|out")
    json.dumps(definition)  # must be serialisable


def _collected_window(db: Session, record_ids: list[str]) -> dict[str, Any]:
    if not record_ids:
        return {}
    lo, hi, n = db.execute(
        select(func.min(SourceRecord.ingested_at), func.max(SourceRecord.ingested_at), func.count()).where(SourceRecord.id.in_(record_ids[:5000]))
    ).one()
    return {"ingested_from": lo.isoformat() if lo else None, "ingested_to": hi.isoformat() if hi else None, "source_records": n}


def _explanation(db: Session, rule: Rule, d: SignalDraft, assumptions: list[str], uncertain: list[str]) -> dict[str, Any]:
    records = sorted({r for ev in d.evidence for r in ev.get("source_records", [])})
    return {
        "label": SIGNAL_LABEL,
        "what_happened": d.what,
        "why_shown": f"Rule '{rule.name}' (v{rule.version}): {rule.description}",
        "supporting_data": {"evidence_items": len(d.evidence), "source_records": records[:100], "source_records_total": len(records)},
        "data_collected": _collected_window(db, records),
        "time_window": {"start": d.window_start.isoformat() if d.window_start else None, "end": d.window_end.isoformat() if d.window_end else None},
        "assumptions": assumptions,
        "uncertain": uncertain,
        "alternative_explanations": rule.definition.get("alternative_explanations", []),
        "score_meaning": "Rule-specific magnitude (observed ÷ threshold). Not a probability and not a judgement about any person or organisation.",
        "rule": {"id": rule.id, "version": rule.version, "kind": rule.kind, "definition": {k: v for k, v in rule.definition.items() if k != "alternative_explanations"}},
    }


# --------------------------------------------------------------------------- evaluators
def _eval_threshold(db: Session, rule: Rule, ctx: dict) -> tuple[list[SignalDraft], list[str], list[str]]:
    d = rule.definition
    anchor_col, nb_col = ("target_id", "source_id") if d.get("direction", "in") == "in" else ("source_id", "target_id")
    op = _OPS[d["op"]]
    sql = text(f"""
        WITH e AS (
            SELECT r.{anchor_col} AS anchor, r.{nb_col} AS nb, r.timestamp AS ts, r.id AS rid, r.source_records AS recs
            FROM relationships r
            JOIN entities t ON t.id = r.{anchor_col} AND t.type = :target_type AND t.merged_into IS NULL AND t.deleted_at IS NULL
            JOIN entities n ON n.id = r.{nb_col} AND n.type = :neighbor_type AND n.merged_into IS NULL AND n.deleted_at IS NULL
            WHERE r.type = :rel AND r.deleted_at IS NULL AND r.timestamp IS NOT NULL
        ),
        cand AS (SELECT anchor FROM e GROUP BY anchor HAVING count(DISTINCT nb) {op} :value),
        w AS (
            SELECT a.anchor, a.ts AS window_start, count(DISTINCT b.nb) AS n
            FROM e a JOIN e b ON b.anchor = a.anchor AND b.ts >= a.ts AND b.ts < a.ts + make_interval(days => :days)
            WHERE a.anchor IN (SELECT anchor FROM cand)
            GROUP BY a.anchor, a.ts
        )
        SELECT DISTINCT ON (anchor) anchor, window_start, n FROM w WHERE n {op} :value ORDER BY anchor, n DESC, window_start
    """)  # noqa: S608 - only whitelisted column names / operators are interpolated
    params = {"target_type": d["target_type"], "neighbor_type": d["neighbor_type"], "rel": d["relationship_type"],
              "value": d["value"], "days": int(d["window_days"])}
    drafts = []
    for anchor, start, n in db.execute(sql, params).all():
        end = start + timedelta(days=int(d["window_days"]))
        edges = db.execute(
            select(Relationship.id, getattr(Relationship, nb_col), Relationship.timestamp, Relationship.source_records)
            .where(getattr(Relationship, anchor_col) == anchor, Relationship.type == d["relationship_type"],
                   Relationship.timestamp >= start, Relationship.timestamp < end, Relationship.deleted_at.is_(None))
            .order_by(Relationship.timestamp)
        ).all()
        nbs = sorted({e[1] for e in edges})
        ev = [{"type": "relationship", "id": rid, "neighbor": nb, "timestamp": ts.isoformat(), "source_records": recs} for rid, nb, ts, recs in edges]
        drafts.append(SignalDraft(
            key=f"{anchor}|{start.isoformat()}", entity_ids=[anchor, *nbs], score=round(n / max(d["value"], 1), 3), evidence=ev,
            what=f"{d['target_type']} {anchor} has {d['relationship_type']} relationships with {n} distinct {d['neighbor_type']} entities "
                 f"within {d['window_days']} days (threshold {d['op']} {d['value']}).",
            window_start=start, window_end=end, extra={"observed": n},
        ))
    assumptions = [f"{d['relationship_type']} timestamps reflect when the relationship was observed.",
                   "Entity resolution merges are correct; unmerged duplicates would inflate the count."]
    uncertain = ["Telemetry may be incomplete or delayed.", "Distinct accounts may belong to the same real-world party."]
    return drafts, assumptions, uncertain


def _eval_unusual_count(db: Session, rule: Rule, ctx: dict) -> tuple[list[SignalDraft], list[str], list[str]]:
    d = rule.definition
    rel = d["path"][0]
    days = int(d["window_days"])
    anchor_col = "target_id" if d.get("direction", "in") == "in" else "source_id"
    rows = db.execute(text(f"""
        WITH e AS (
            SELECT r.{anchor_col} AS anchor, r.timestamp AS ts
            FROM relationships r JOIN entities a ON a.id = r.{anchor_col} AND a.type = :etype AND a.merged_into IS NULL
            WHERE r.type = :rel AND r.deleted_at IS NULL AND r.timestamp IS NOT NULL
        ),
        w AS (
            SELECT x.anchor, x.ts AS window_start, count(*) AS n
            FROM e x JOIN e y ON y.anchor = x.anchor AND y.ts >= x.ts AND y.ts < x.ts + make_interval(days => :days)
            GROUP BY x.anchor, x.ts
        )
        SELECT DISTINCT ON (anchor) anchor, window_start, n FROM w ORDER BY anchor, n DESC, window_start
    """), {"etype": d["entity_type"], "rel": rel, "days": days}).all()  # noqa: S608
    if not rows:
        return [], [], []
    counts = sorted(r[2] for r in rows)
    pct = counts[min(len(counts) - 1, int(len(counts) * float(d.get("percentile", 0.99))))]
    mean = sum(counts) / len(counts)
    threshold = max(int(d.get("min_count", 1)), pct + 1)
    drafts = []
    for anchor, start, n in rows:
        if n < threshold:
            continue
        end = start + timedelta(days=days)
        edges = db.execute(
            select(Relationship.id, Relationship.source_id, Relationship.timestamp, Relationship.source_records, Relationship.properties)
            .where(getattr(Relationship, anchor_col) == anchor, Relationship.type == rel, Relationship.timestamp >= start,
                   Relationship.timestamp < end).order_by(Relationship.timestamp)
        ).all()
        ev = [{"type": "relationship", "id": rid, "other": o, "timestamp": ts.isoformat(), "source_records": recs, "amount": (p or {}).get("amount")}
              for rid, o, ts, recs, p in edges]
        drafts.append(SignalDraft(
            key=f"{anchor}|{start.isoformat()}", entity_ids=[anchor], score=round(n / threshold, 3), evidence=ev,
            what=f"{d['entity_type']} {anchor} has {n} {rel} relationships in a {days}-day window; population p{int(float(d.get('percentile', .99)) * 100)} "
                 f"is {pct} (mean {mean:.1f}, n={len(counts)} {d['entity_type']}s).",
            window_start=start, window_end=end, extra={"observed": n, "population_percentile": pct, "population_mean": round(mean, 2)},
        ))
    return drafts, ["The population baseline is all entities of this type in the current dataset.",
                    "Counting uses relationship timestamps, i.e. transaction booking time."], \
        ["Baselines shift as more data is ingested; a signal may disappear or appear on re-evaluation."]


def _eval_cycle(db: Session, rule: Rule, ctx: dict) -> tuple[list[SignalDraft], list[str], list[str]]:
    d = rule.definition
    window = timedelta(days=int(d.get("window_days", 7)))
    rows = db.execute(text("""
        SELECT i.source_id AS src, t.target_id AS dst, i.timestamp AS ts, i.target_id AS txn, i.source_records || t.source_records AS recs
        FROM relationships i JOIN relationships t ON t.source_id = i.target_id AND t.type = 'TRANSFERRED_TO' AND t.deleted_at IS NULL
        WHERE i.type = 'INITIATED' AND i.deleted_at IS NULL AND i.timestamp IS NOT NULL
    """)).all()
    g = nx.DiGraph()
    for src, dst, ts, txn, recs in rows:
        if src == dst:
            continue
        if not g.has_edge(src, dst):
            g.add_edge(src, dst, tx=[])
        g[src][dst]["tx"].append((ts, txn, recs))
    drafts = []
    seen = set()
    for cyc in nx.simple_cycles(g, length_bound=int(d.get("max_length", 4))):
        if len(cyc) < 2:
            continue
        canon = tuple(min(cyc[i:] + cyc[:i] for i in range(len(cyc))))
        if canon in seen:
            continue
        seen.add(canon)
        legs = [g[u][v]["tx"] for u, v in zip(cyc, cyc[1:] + cyc[:1])]
        best = None
        for start_ts in sorted({t for leg in legs for t, _, _ in leg}):
            chosen = []
            for leg in legs:
                c = [x for x in leg if start_ts <= x[0] <= start_ts + window]
                if not c:
                    break
                chosen.append(min(c, key=lambda x: x[0]))
            else:
                best = (start_ts, chosen)
                break
        if best is None:
            continue
        start_ts, chosen = best
        ev = [{"type": "transaction", "id": txn, "from": u, "to": v, "timestamp": ts.isoformat(), "source_records": recs}
              for (ts, txn, recs), (u, v) in zip(chosen, zip(cyc, cyc[1:] + cyc[:1]))]
        drafts.append(SignalDraft(
            key="|".join(canon) + f"|{start_ts.date()}", entity_ids=list(canon) + [c[1] for c in chosen], score=1.0, evidence=ev,
            what=f"Transfers form a closed loop through {len(cyc)} accounts within {window.days} days.",
            window_start=start_ts, window_end=max(c[0] for c in chosen),
        ))
    return drafts, ["Account-to-account flow is inferred as INITIATED → Transaction → TRANSFERRED_TO."], \
        ["Amounts are not required to match; loops may be coincidental in dense data."]


def _eval_event(db: Session, rule: Rule, ctx: dict) -> tuple[list[SignalDraft], list[str], list[str]]:
    d = rule.definition
    watch = [natural_entity_id(t, k) for t, k in d.get("entity_ids_by_key", [])] + d.get("entity_ids", [])
    q = text("""SELECT id, event_type, timestamp, entity_ids, source_record_id FROM events
                WHERE event_type = ANY(:types) AND deleted_at IS NULL AND (cardinality(CAST(:watch AS varchar[])) = 0 OR entity_ids && CAST(:watch AS varchar[]))
                ORDER BY timestamp LIMIT 5000""")
    drafts = []
    for eid, etype, ts, ents, rec in db.execute(q, {"types": d["event_types"], "watch": watch}).all():
        drafts.append(SignalDraft(
            key=eid, entity_ids=list(ents), score=1.0,
            evidence=[{"type": "event", "id": eid, "event_type": etype, "timestamp": ts.isoformat(), "source_records": [rec] if rec else []}],
            what=f"Event '{etype}' at {ts.isoformat()} involves watch-listed entity(ies).", window_start=ts, window_end=ts,
        ))
    return drafts, ["The watch-list reflects analyst-provided criteria."], ["Event logs may contain automated or test traffic."]


def _eval_sequence(db: Session, rule: Rule, ctx: dict) -> tuple[list[SignalDraft], list[str], list[str]]:
    d = rule.definition
    q = text("""
        SELECT a.id, b.id, a.timestamp, b.timestamp, a.entity_ids, a.source_record_id, b.source_record_id
        FROM events a JOIN events b
          ON b.event_type = :then AND b.timestamp > a.timestamp AND b.timestamp <= a.timestamp + make_interval(mins => :mins)
         AND a.entity_ids && b.entity_ids AND (a.properties->>'ip') = (b.properties->>'ip')
        WHERE a.event_type = :first AND a.deleted_at IS NULL AND b.deleted_at IS NULL
        LIMIT 5000""")
    drafts = []
    for a, b, ta, tb, ents, ra, rb in db.execute(q, {"first": d["first"], "then": d["then"], "mins": int(d["within_minutes"])}).all():
        drafts.append(SignalDraft(
            key=f"{a}|{b}", entity_ids=list(ents), score=1.0,
            evidence=[{"type": "event", "id": a, "timestamp": ta.isoformat(), "source_records": [ra]},
                      {"type": "event", "id": b, "timestamp": tb.isoformat(), "source_records": [rb]}],
            what=f"'{d['first']}' followed by '{d['then']}' after {int((tb - ta).total_seconds() // 60)} min from the same IP.",
            window_start=ta, window_end=tb,
        ))
    return drafts, ["Events are correlated by shared entities and identical source IP."], ["IP addresses can be shared (NAT, proxies)."]


def _eval_geofence(db: Session, rule: Rule, ctx: dict) -> tuple[list[SignalDraft], list[str], list[str]]:
    d = rule.definition
    gf = db.scalar(select(Geofence).where(Geofence.name == d["geofence_name"]))
    if gf is None:
        return [], [], [f"geofence '{d['geofence_name']}' not defined"]
    q = text("""
        SELECT ent.id, count(*) AS n, min(e.timestamp), max(e.timestamp), array_agg(e.id ORDER BY e.timestamp), array_agg(e.source_record_id)
        FROM events e CROSS JOIN LATERAL unnest(e.entity_ids) AS u(eid)
        JOIN entities ent ON ent.id = u.eid AND ent.type = 'Device'
        JOIN geofences g ON g.id = :gf AND ST_Intersects(e.geom, g.geom)
        WHERE e.event_type = ANY(:types) AND e.deleted_at IS NULL
        GROUP BY ent.id""")
    drafts = []
    for dev, n, t0, t1, evs, recs in db.execute(q, {"gf": gf.id, "types": d["event_types"]}).all():
        drafts.append(SignalDraft(
            key=f"{dev}|{t0.date()}", entity_ids=[dev], score=float(n),
            evidence=[{"type": "event", "id": e, "source_records": [r] if r else []} for e, r in zip(evs[:50], recs[:50])],
            what=f"Device {dev} recorded {n} event(s) inside geofence '{gf.name}' between {t0.isoformat()} and {t1.isoformat()}.",
            window_start=t0, window_end=t1,
        ))
    return drafts, ["Event coordinates are as reported by the source."], ["Location precision varies by source; boundary events may be misplaced."]


def _eval_new_relationship(db: Session, rule: Rule, ctx: dict) -> tuple[list[SignalDraft], list[str], list[str]]:
    d = rule.definition
    ids = ctx.get("new_relationship_ids")
    q = select(Relationship).where(Relationship.type.in_(d["relationship_types"]), Relationship.deleted_at.is_(None))
    q = q.where(Relationship.id.in_(ids)) if ids is not None else q.where(Relationship.created_at >= utcnow() - timedelta(days=int(d.get("lookback_days", 1))))
    drafts = []
    for r in db.scalars(q.limit(5000)):
        drafts.append(SignalDraft(
            key=r.id, entity_ids=[r.source_id, r.target_id], score=1.0,
            evidence=[{"type": "relationship", "id": r.id, "relationship_type": r.type, "source_records": r.source_records}],
            what=f"New {r.type} relationship {r.source_id} → {r.target_id} appeared in ingested data.",
            window_start=r.timestamp, window_end=r.timestamp,
        ))
    return drafts, ["'New' means first seen by this platform, not first occurrence in the real world."], []


def _eval_source_change(db: Session, rule: Rule, ctx: dict) -> tuple[list[SignalDraft], list[str], list[str]]:
    drafts = []
    for rec_id in ctx.get("changed_record_ids", []):
        rec = db.get(SourceRecord, rec_id)
        if rec is None:
            continue
        ents = db.scalars(select(Entity.id).where(Entity.source_ids.contains([rec_id])).limit(50)).all()
        drafts.append(SignalDraft(
            key=f"{rec_id}|{rec.content_hash}", entity_ids=list(ents), score=1.0,
            evidence=[{"type": "source_record", "id": rec_id, "source_records": [rec_id], "content_hash": rec.content_hash}],
            what=f"Source record {rec.source_record_id} from {rec.source_id} changed on re-ingestion.",
        ))
    return drafts, [], ["The previous version is not retained in full; only its hash was compared."]


EVALUATORS = {
    "threshold": _eval_threshold, "unusual_count": _eval_unusual_count, "cycle": _eval_cycle, "event": _eval_event,
    "sequence": _eval_sequence, "geofence": _eval_geofence, "new_relationship": _eval_new_relationship, "source_change": _eval_source_change,
}


def evaluate(db: Session, rule: Rule, ctx: dict | None = None) -> dict[str, Any]:
    ctx = ctx or {}
    drafts, assumptions, uncertain = EVALUATORS[rule.kind](db, rule, ctx)
    created_signals: list[Signal] = []
    created_alerts: list[Alert] = []
    for dft in drafts:
        fp = hashlib.sha256(f"{rule.id}|{dft.key}".encode()).hexdigest()
        expl = _explanation(db, rule, dft, assumptions, uncertain)
        expl.update(dft.extra)
        sig_id = new_id("sig")
        stmt = pg_insert(Signal.__table__).values(
            id=sig_id, label=SIGNAL_LABEL, rule_id=rule.id, rule_version=rule.version, entity_ids=dft.entity_ids[:500], score=dft.score,
            evidence=dft.evidence[:200], explanation=expl, window_start=dft.window_start, window_end=dft.window_end,
            epistemic_status="SYSTEM_INFERENCE", fingerprint=fp, created_at=utcnow(),
        ).on_conflict_do_nothing(index_elements=["fingerprint"]).returning(Signal.__table__.c.id)
        inserted = db.execute(stmt).scalar()
        if inserted is None:
            continue  # already known – idempotent re-evaluation
        sig = db.get(Signal, inserted)
        created_signals.append(sig)
        if rule.definition.get("alert"):
            alert = Alert(id=new_id("alr"), rule=rule.id, alert_type=rule.kind, severity=rule.severity, entities=dft.entity_ids[:100],
                          evidence=dft.evidence[:50], summary=f"{SIGNAL_LABEL} detected — {dft.what}", signal_id=sig.id)
            db.add(alert)
            created_alerts.append(alert)
            ALERTS_RAISED.labels(rule=rule.id).inc()
    db.flush()
    return {"rule": rule.id, "drafts": len(drafts), "new_signals": [s.id for s in created_signals], "new_alerts": created_alerts}


def load_rules(db: Session, path) -> list[Rule]:  # noqa: ANN001
    data = json.loads(open(path).read())
    out = []
    for r in data["rules"]:
        validate_rule_definition(r["kind"], r["name"], r.get("description", ""), r["definition"])
        existing = db.get(Rule, r["id"])
        if existing is None:
            existing = Rule(id=r["id"], name=r["name"], description=r.get("description", ""), kind=r["kind"], definition=r["definition"],
                            severity=r.get("severity", "MEDIUM"), enabled=r.get("enabled", True), created_by="system")
            db.add(existing)
        elif existing.definition != r["definition"] or existing.name != r["name"]:
            existing.definition, existing.name, existing.description = r["definition"], r["name"], r.get("description", "")
            existing.version += 1
        out.append(existing)
    db.flush()
    return out


def evaluate_all(db: Session, ctx: dict | None = None, kinds: set[str] | None = None) -> list[dict[str, Any]]:
    results = []
    for rule in db.scalars(select(Rule).where(Rule.enabled.is_(True)).order_by(Rule.id)):
        if kinds and rule.kind not in kinds:
            continue
        if rule.kind in ("new_relationship", "source_change") and ctx is None:
            continue  # ingestion-driven rules need ingestion context
        results.append(evaluate(db, rule, ctx))
    return results
