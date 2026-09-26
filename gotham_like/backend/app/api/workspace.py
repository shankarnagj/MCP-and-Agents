"""Investigations, evidence board, assertions, saved queries, pattern queries, export and reports."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.common import ip_of, onto
from app.audit.service import record
from app.auth.deps import Principal, require
from app.auth.rbac import P_ASSERT, P_EXPORT, P_INV_READ, P_INV_WRITE, P_SEARCH
from app.db import get_db
from app.graph.store import resolve_canonical
from app.models import Assertion, Investigation, InvestigationItem, SavedQuery, new_id
from app.ontology import Ontology
from app.services import export as exporter
from app.services import investigations as svc
from app.services import report as reporter
from app.services.query_builder import PatternQuery
from app.services.query_builder import execute as run_pattern

router = APIRouter(prefix="/api", tags=["investigations"])


def _load(db: Session, inv_id: str) -> Investigation:
    inv = db.get(Investigation, inv_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")
    return inv


def _writable(db: Session, user: Principal, inv_id: str) -> Investigation:
    inv = _load(db, inv_id)
    if not svc.can_write(user, inv):
        raise HTTPException(403, "not a collaborator on this investigation")
    return inv


class InvestigationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10000)
    scope: dict[str, Any] = Field(default_factory=dict)


class InvestigationPatch(BaseModel):
    name: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    status: Literal["OPEN", "ON_HOLD", "CLOSED"] | None = None
    scope: dict[str, Any] | None = None
    collaborators: list[str] | None = None
    expected_version: int | None = None


@router.post("/investigations", status_code=201)
def create_investigation(body: InvestigationCreate, request: Request, user: Principal = Depends(require(P_INV_WRITE)), db: Session = Depends(get_db)) -> dict:
    inv = svc.create(db, user, body.name, body.description, body.scope, ip_of(request))
    db.commit()
    return svc.inv_dict(inv)


@router.get("/investigations")
def list_investigations(mine: bool = False, user: Principal = Depends(require(P_INV_READ)), db: Session = Depends(get_db)) -> list[dict]:
    q = select(Investigation).order_by(Investigation.updated_at.desc())
    if mine:
        q = q.where(or_(Investigation.created_by == user.id, Investigation.collaborators.contains([user.id])))
    return [svc.inv_dict(i) for i in db.scalars(q.limit(500))]


@router.get("/investigations/{inv_id}")
def get_investigation(inv_id: str, user: Principal = Depends(require(P_INV_READ)), db: Session = Depends(get_db)) -> dict:
    inv = _load(db, inv_id)
    return {**svc.get_full(db, inv), "can_write": svc.can_write(user, inv)}


@router.patch("/investigations/{inv_id}")
def patch_investigation(inv_id: str, body: InvestigationPatch, request: Request, user: Principal = Depends(require(P_INV_WRITE)),
                        db: Session = Depends(get_db)) -> dict:
    inv = _writable(db, user, inv_id)
    if body.collaborators is not None and user.id != inv.created_by and user.role != "ADMIN":
        raise HTTPException(403, "only the owner or an ADMIN may change collaborators")
    try:
        svc.update(db, user, inv, body.model_dump(exclude={"expected_version"}), body.expected_version, ip_of(request))
    except svc.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return svc.inv_dict(inv)


class ItemCreate(BaseModel):
    kind: str
    ref_id: str | None = Field(default=None, max_length=200)
    title: str = Field(default="", max_length=300)
    content: dict[str, Any] = Field(default_factory=dict)


@router.post("/investigations/{inv_id}/items", status_code=201)
def add_item(inv_id: str, body: ItemCreate, request: Request, user: Principal = Depends(require(P_INV_WRITE)), db: Session = Depends(get_db)) -> dict:
    inv = _writable(db, user, inv_id)
    ref = resolve_canonical(db, body.ref_id) if body.kind == "entity" and body.ref_id else body.ref_id
    try:
        it = svc.add_item(db, user, inv, body.kind, ref, body.title, body.content, ip_of(request))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return svc.item_dict(it)


@router.delete("/investigations/{inv_id}/items/{item_id}", status_code=204)
def delete_item(inv_id: str, item_id: str, request: Request, user: Principal = Depends(require(P_INV_WRITE)), db: Session = Depends(get_db)) -> Response:
    inv = _writable(db, user, inv_id)
    try:
        svc.remove_item(db, user, inv, item_id, ip_of(request))
    except KeyError as exc:
        raise HTTPException(404, "item not found") from exc
    db.commit()
    return Response(status_code=204)


@router.post("/investigations/{inv_id}/documents", status_code=201)
async def upload_document(inv_id: str, request: Request, file: UploadFile = File(...), title: str = Form(""), user: Principal = Depends(require(P_INV_WRITE)),
                          db: Session = Depends(get_db)) -> dict:
    inv = _writable(db, user, inv_id)
    data = await file.read(svc.MAX_UPLOAD + 1)
    try:
        meta = svc.store_upload(data, file.filename or "upload", file.content_type or "application/octet-stream")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    it = svc.add_item(db, user, inv, "document", meta["sha256"], title or meta["filename"], meta, ip_of(request))
    db.commit()
    return svc.item_dict(it)


class AssertionCreate(BaseModel):
    statement: str = Field(min_length=5, max_length=5000)
    subject_ids: list[str] = Field(min_length=1, max_length=50)
    investigation_id: str | None = None
    rationale: str = Field(default="", max_length=10000)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    analyst_confidence: Literal["LOW", "MEDIUM", "HIGH"] | None = None


class AssertionPatch(BaseModel):
    status: Literal["HYPOTHESIS", "SUPPORTED", "REFUTED", "WITHDRAWN"] | None = None
    note: str = Field(min_length=1, max_length=2000)
    rationale: str | None = Field(default=None, max_length=10000)


@router.post("/assertions", status_code=201)
def create_assertion(body: AssertionCreate, request: Request, user: Principal = Depends(require(P_ASSERT)), db: Session = Depends(get_db)) -> dict:
    if body.investigation_id:
        _writable(db, user, body.investigation_id)
    subjects = [resolve_canonical(db, s) for s in body.subject_ids]
    try:
        a = svc.create_assertion(db, user, body.statement, subjects, body.investigation_id, body.rationale, body.evidence_refs,
                                 body.analyst_confidence, ip_of(request))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    db.commit()
    return svc.assertion_dict(a)


@router.patch("/assertions/{assertion_id}")
def patch_assertion(assertion_id: str, body: AssertionPatch, request: Request, user: Principal = Depends(require(P_ASSERT)),
                    db: Session = Depends(get_db)) -> dict:
    a = db.get(Assertion, assertion_id)
    if a is None:
        raise HTTPException(404, "assertion not found")
    if a.created_by != user.id and user.role not in ("ADMIN", "INVESTIGATOR"):
        raise HTTPException(403, "only the author or an INVESTIGATOR may change this assertion")
    svc.update_assertion(db, user, a, body.status, body.note, body.rationale, ip_of(request))
    db.commit()
    return svc.assertion_dict(a)


@router.get("/assertions")
def list_assertions(investigation_id: str | None = None, subject_id: str | None = None, user: Principal = Depends(require(P_INV_READ)),
                    db: Session = Depends(get_db)) -> list[dict]:
    q = select(Assertion).order_by(Assertion.created_at.desc())
    if investigation_id:
        q = q.where(Assertion.investigation_id == investigation_id)
    if subject_id:
        q = q.where(Assertion.subject_ids.contains([subject_id]))
    return [svc.assertion_dict(a) for a in db.scalars(q.limit(500))]


# ---------------------------------------------------------------- queries
class QueryBody(BaseModel):
    pattern: dict[str, Any]
    explain: bool = False


@router.post("/query")
def post_query(body: QueryBody, request: Request, user: Principal = Depends(require(P_SEARCH)), db: Session = Depends(get_db),
               ontology: Ontology = Depends(onto)) -> dict:
    """Execute a visual-query-builder pattern. Returns the query plan with the results."""
    try:
        pq = PatternQuery.model_validate(body.pattern)
        res = run_pattern(db, pq, ontology, user.role, explain=body.explain)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    record(db, "query", user, "pattern_query", None, details={"pattern": body.pattern, "rows": res["row_count"]}, ip=ip_of(request))
    db.commit()
    return res


class SavedQueryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    query_kind: Literal["search", "pattern", "geo", "timeline", "graph"]
    query: dict[str, Any]
    filters: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    investigation_id: str | None = None


@router.post("/saved-queries", status_code=201)
def save_query(body: SavedQueryCreate, request: Request, user: Principal = Depends(require(P_INV_WRITE)), db: Session = Depends(get_db)) -> dict:
    if body.query_kind == "pattern":
        try:
            PatternQuery.model_validate(body.query)
        except ValidationError as exc:
            raise HTTPException(422, "invalid pattern") from exc
    if body.investigation_id:
        _writable(db, user, body.investigation_id)
    q = SavedQuery(id=new_id("sq"), name=body.name, description=body.description, query_kind=body.query_kind, query=body.query,
                   filters=body.filters, parameters=body.parameters, investigation_id=body.investigation_id, created_by=user.id)
    db.add(q)
    db.flush()
    record(db, "investigation_update" if body.investigation_id else "query", user, "saved_query", q.id, new_value=svc.saved_query_dict(q),
           ip=ip_of(request))
    db.commit()
    return svc.saved_query_dict(q)


@router.get("/saved-queries")
def list_saved(user: Principal = Depends(require(P_INV_READ)), db: Session = Depends(get_db)) -> list[dict]:
    return [svc.saved_query_dict(q) for q in db.scalars(select(SavedQuery).order_by(SavedQuery.created_at.desc()).limit(500))]


@router.post("/saved-queries/{sq_id}/run")
def run_saved(sq_id: str, request: Request, user: Principal = Depends(require(P_SEARCH)), db: Session = Depends(get_db),
              ontology: Ontology = Depends(onto)) -> dict:
    q = db.get(SavedQuery, sq_id)
    if q is None:
        raise HTTPException(404, "saved query not found")
    if q.query_kind != "pattern":
        return {"saved_query": svc.saved_query_dict(q), "note": "Non-pattern saved queries are re-executed by the client against their endpoint."}
    return {"saved_query": svc.saved_query_dict(q), **post_query(QueryBody(pattern=q.query), request, user, db, ontology)}


# ---------------------------------------------------------------- export & report
class ExportBody(BaseModel):
    format: Literal["csv", "json", "graphml", "geojson"]
    entity_ids: list[str] | None = Field(default=None, max_length=exporter.MAX_EXPORT_ENTITIES)
    investigation_id: str | None = None
    what: Literal["entities", "relationships", "events"] = "entities"


MEDIA = {"csv": "text/csv", "json": "application/json", "graphml": "application/graphml+xml", "geojson": "application/geo+json"}


@router.post("/export")
def export(body: ExportBody, request: Request, user: Principal = Depends(require(P_EXPORT)), db: Session = Depends(get_db),
           ontology: Ontology = Depends(onto)) -> Response:
    ids = [resolve_canonical(db, x) for x in (body.entity_ids or [])]
    if body.investigation_id:
        _load(db, body.investigation_id)
        ids += [r for (r,) in db.execute(select(InvestigationItem.ref_id).where(InvestigationItem.investigation_id == body.investigation_id,
                                                                                InvestigationItem.kind == "entity"))]
    if not ids:
        raise HTTPException(422, "nothing to export: provide entity_ids or an investigation with pinned entities")
    try:
        data = exporter.collect(db, ontology, user.role, list(dict.fromkeys(ids)))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    data["metadata"]["exported_by"] = user.username
    body_text = {"csv": lambda: exporter.to_csv(data, body.what), "json": lambda: exporter.to_json(data),
                 "graphml": lambda: exporter.to_graphml(data), "geojson": lambda: exporter.to_geojson(data)}[body.format]()
    record(db, "data_export", user, "export", body.investigation_id, details={"format": body.format, "what": body.what, **data["metadata"]["counts"]},
           ip=ip_of(request))
    db.commit()
    ext = {"graphml": "graphml", "geojson": "geojson", "csv": "csv", "json": "json"}[body.format]
    return Response(body_text, media_type=MEDIA[body.format], headers={"Content-Disposition": f'attachment; filename="tessera-export.{ext}"'})


@router.get("/investigations/{inv_id}/report")
def investigation_report(inv_id: str, request: Request, format: Literal["json", "markdown", "pdf"] = Query("json"),
                         user: Principal = Depends(require(P_EXPORT)), db: Session = Depends(get_db), ontology: Ontology = Depends(onto)) -> Any:
    inv = _load(db, inv_id)
    rep = reporter.build_report(db, ontology, inv, user.role, user.username)
    record(db, "data_export", user, "investigation", inv.id, details={"format": f"report/{format}"}, ip=ip_of(request))
    db.commit()
    if format == "markdown":
        return PlainTextResponse(reporter.to_markdown(rep), media_type="text/markdown")
    if format == "pdf":
        return Response(reporter.to_pdf(rep), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{inv.id}-report.pdf"'})
    return rep
