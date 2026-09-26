"""Visual query builder backend: pattern → validated plan → parameterised SQL.

Pattern example ("accounts sharing a device with > 3 other accounts in 30 days"):

    {"nodes": [{"var": "p", "type": "Person"},
               {"var": "a", "type": "Account", "filters": [{"property": "account_type", "op": "=", "value": "checking"}]},
               {"var": "d", "type": "Device"}],
     "edges": [{"from": "p", "to": "a", "type": "OWNS"},
               {"from": "a", "to": "d", "type": "USED", "time_from": "2026-03-01", "time_to": "2026-03-31"}],
     "aggregate": {"group_by": "d", "count_distinct": "a", "op": ">", "value": 3},
     "limit": 100}

Everything user-supplied becomes a bound parameter. Types, relationship types and
property names are validated against the ontology before any SQL is generated.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Float, and_, cast, func, select
from sqlalchemy.orm import Session, aliased

from app.ingestion.mapping import parse_ts
from app.models import Entity, Relationship
from app.ontology import Ontology
from app.privacy.masking import can_view
from app.services.serialize import entity_dict

_VAR = re.compile(r"^[a-z][a-z0-9_]{0,15}$")
Op = Literal["=", "!=", ">", ">=", "<", "<=", "contains", "in"]


class PropertyFilter(BaseModel):
    property: str
    op: Op = "="
    value: Any


class NodePattern(BaseModel):
    var: str
    type: str
    ids: list[str] | None = None
    filters: list[PropertyFilter] = Field(default_factory=list)

    @field_validator("var")
    @classmethod
    def _var(cls, v: str) -> str:
        if not _VAR.match(v):
            raise ValueError("var must be a short lowercase identifier")
        return v


class EdgePattern(BaseModel):
    from_: str = Field(alias="from")
    to: str
    type: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    min_confidence: float = 0.0

    model_config = {"populate_by_name": True}


class Aggregate(BaseModel):
    group_by: str
    count_distinct: str
    op: Literal[">", ">=", "=", "<", "<="] = ">"
    value: int


class PatternQuery(BaseModel):
    nodes: list[NodePattern] = Field(min_length=1, max_length=8)
    edges: list[EdgePattern] = Field(default_factory=list, max_length=8)
    aggregate: Aggregate | None = None
    return_vars: list[str] | None = None
    limit: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def _refs(self) -> PatternQuery:
        names = [n.var for n in self.nodes]
        if len(set(names)) != len(names):
            raise ValueError("duplicate node var")
        for e in self.edges:
            if e.from_ not in names or e.to not in names:
                raise ValueError(f"edge references unknown var {e.from_}->{e.to}")
        if self.aggregate and (self.aggregate.group_by not in names or self.aggregate.count_distinct not in names):
            raise ValueError("aggregate references unknown var")
        return self


def _cmp(col, op: str, value: Any):  # noqa: ANN001, ANN202
    if op == "=":
        return col == value
    if op == "!=":
        return col != value
    if op == ">":
        return col > value
    if op == ">=":
        return col >= value
    if op == "<":
        return col < value
    if op == "<=":
        return col <= value
    raise ValueError(op)


def plan_and_compile(pq: PatternQuery, ontology: Ontology, role: str):  # noqa: ANN201
    plan: list[dict[str, Any]] = []
    aliases = {}
    for n in pq.nodes:
        if n.type not in ontology.entity_types:
            raise ValueError(f"unknown entity type {n.type}")
        aliases[n.var] = aliased(Entity, name=f"n_{n.var}")
    conds = []
    for n in pq.nodes:
        a = aliases[n.var]
        conds += [a.type == n.type, a.merged_into.is_(None), a.deleted_at.is_(None)]
        step = {"step": "scan", "var": n.var, "type": n.type, "index": "ix_entities_live_type", "filters": []}
        if n.ids:
            conds.append(a.id.in_(n.ids[:1000]))
            step["index"] = "entities_pkey"
        for f in n.filters:
            pdef = ontology.entity_type(n.type).properties.get(f.property)
            if pdef is None:
                raise ValueError(f"{n.type} has no property {f.property}")
            if not can_view(role, pdef.sensitivity):
                raise PermissionError(f"not permitted to filter on protected property {n.type}.{f.property}")
            col = a.properties[f.property].astext
            if f.op == "contains":
                conds.append(col.ilike("%" + str(f.value).replace("%", r"\%").replace("_", r"\_") + "%"))
            elif f.op == "in":
                if not isinstance(f.value, list):
                    raise ValueError("'in' expects a list")
                conds.append(col.in_([str(v) for v in f.value][:500]))
            elif pdef.type in ("number", "integer"):
                conds.append(_cmp(cast(col, Float), f.op, float(f.value)))
            elif pdef.type in ("date", "datetime"):
                conds.append(_cmp(col, f.op, str(f.value)))  # ISO-8601 strings sort chronologically
            else:
                conds.append(_cmp(col, f.op, str(f.value)))
            step["filters"].append(f"{f.property} {f.op} {f.value!r}")
        plan.append(step)
    for i, e in enumerate(pq.edges):
        r = aliased(Relationship, name=f"r{i}")
        if e.type is not None:
            if e.type not in ontology.relationship_types:
                raise ValueError(f"unknown relationship type {e.type}")
            src_t = next(n.type for n in pq.nodes if n.var == e.from_)
            dst_t = next(n.type for n in pq.nodes if n.var == e.to)
            ontology.validate_relationship(e.type, src_t, dst_t)
            conds.append(r.type == e.type)
        conds += [r.source_id == aliases[e.from_].id, r.target_id == aliases[e.to].id, r.deleted_at.is_(None)]
        tf, tt = parse_ts(e.time_from), parse_ts(e.time_to)
        if e.time_from and tf is None or e.time_to and tt is None:
            raise ValueError("invalid edge time bound")
        if tf:
            conds.append(r.timestamp >= tf)
        if tt:
            conds.append(r.timestamp <= tt)
        if e.min_confidence:
            conds.append(r.confidence >= e.min_confidence)
        plan.append({"step": "join", "edge": f"({e.from_})-[{e.type or '*'}]->({e.to})", "index": "ix_rel_live_source / ix_rel_live_target",
                     "time_window": [e.time_from, e.time_to]})
    if pq.aggregate:
        g, c = aliases[pq.aggregate.group_by], aliases[pq.aggregate.count_distinct]
        cnt = func.count(func.distinct(c.id)).label("n")
        stmt = (select(g.id, cnt, func.array_agg(func.distinct(c.id)).label("members")).where(and_(*conds)).group_by(g.id)
                .having(_cmp(cnt, pq.aggregate.op, pq.aggregate.value)).order_by(cnt.desc()).limit(pq.limit))
        plan.append({"step": "aggregate", "group_by": pq.aggregate.group_by, "count_distinct": pq.aggregate.count_distinct,
                     "having": f"{pq.aggregate.op} {pq.aggregate.value}"})
    else:
        ret = pq.return_vars or [n.var for n in pq.nodes]
        for v in ret:
            if v not in aliases:
                raise ValueError(f"unknown return var {v}")
        stmt = select(*[aliases[v].id.label(v) for v in ret]).where(and_(*conds)).distinct().limit(pq.limit)
        plan.append({"step": "project", "vars": ret, "limit": pq.limit})
    return stmt, plan


def execute(db: Session, pq: PatternQuery, ontology: Ontology, role: str, explain: bool = False) -> dict[str, Any]:
    stmt, plan = plan_and_compile(pq, ontology, role)
    started = datetime.now()
    rows = db.execute(stmt).all()
    elapsed_ms = (datetime.now() - started).total_seconds() * 1000
    ids: set[str] = set()
    if pq.aggregate:
        result_rows = [{"group": r[0], "count": r[1], "members": list(r[2])[:200]} for r in rows]
        for r in result_rows:
            ids.add(r["group"])
            ids.update(r["members"])
    else:
        result_rows = [dict(r._mapping) for r in rows]
        for r in result_rows:
            ids.update(r.values())
    ents = {e.id: entity_dict(e, ontology, role, full=False) for e in db.scalars(select(Entity).where(Entity.id.in_(list(ids)[:5000])))}
    out: dict[str, Any] = {"plan": plan, "rows": result_rows, "entities": ents, "row_count": len(result_rows), "elapsed_ms": round(elapsed_ms, 1),
                           "truncated": len(result_rows) >= pq.limit}
    if explain:
        compiled = stmt.compile(dialect=db.bind.dialect)
        out["sql"] = str(compiled)
        # EXPLAIN (not ANALYZE) is side-effect free; parameters stay bound.
        plan_json = db.connection().exec_driver_sql("EXPLAIN (FORMAT JSON) " + str(compiled), compiled.params).scalar()
        out["database_plan"] = plan_json
    return out
