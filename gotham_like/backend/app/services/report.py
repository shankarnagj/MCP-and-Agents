"""Structured investigation report (JSON / Markdown / PDF).

Signals are reported as ANALYTICAL SIGNALS with alternative explanations; analyst
assertions are reported as hypotheses. The report never states conclusions about
people or organisations.
"""

from __future__ import annotations

import io
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph.store import edges_among
from app.models import (
    SIGNAL_LABEL,
    Assertion,
    DataSource,
    Entity,
    Investigation,
    InvestigationItem,
    Relationship,
    ResolutionCandidate,
    Signal,
    SourceRecord,
    utcnow,
)
from app.ontology import Ontology
from app.privacy.masking import mask_label
from app.services.investigations import assertion_dict, item_dict
from app.services.serialize import edge_row_dict, entity_dict
from app.services.timeline import timeline

STANDARD_LIMITATIONS = [
    "All results depend on the completeness and accuracy of ingested sources; absence of data is not evidence of absence.",
    "Relationships reflect recorded associations. They do not by themselves establish intent, causation, control or wrongdoing.",
    "Analytical signals are outputs of deterministic rules and graph mathematics. They are prompts for review, not findings.",
    "Entity resolution is deterministic but imperfect: unmerged duplicates and incorrect merges are both possible.",
    "Graph views and path searches are windowed and fan-out limited; truncated searches may omit connections.",
    "Analyst assertions are hypotheses recorded by people and have not been independently verified unless stated.",
]


def build_report(db: Session, ontology: Ontology, inv: Investigation, role: str, author: str) -> dict[str, Any]:
    items = db.scalars(select(InvestigationItem).where(InvestigationItem.investigation_id == inv.id).order_by(InvestigationItem.created_at)).all()
    ent_ids = [i.ref_id for i in items if i.kind == "entity" and i.ref_id]
    rel_ids = [i.ref_id for i in items if i.kind == "relationship" and i.ref_id]
    ents = db.scalars(select(Entity).where(Entity.id.in_(ent_ids))).all() if ent_ids else []
    pinned_rels = db.scalars(select(Relationship).where(Relationship.id.in_(rel_ids))).all() if rel_ids else []
    among = edges_among(db, ent_ids, limit=2000)
    rel_rows = [edge_row_dict(r) for r in among]
    seen = {r["id"] for r in rel_rows}
    for r in pinned_rels:
        if r.id not in seen:
            rel_rows.append({"id": r.id, "source": r.source_id, "target": r.target_id, "relationship_type": r.type,
                             "timestamp": r.timestamp.isoformat() if r.timestamp else None, "confidence": r.confidence,
                             "epistemic_status": r.epistemic_status, "source_records": r.source_records, "provenance": r.provenance})
    end_ids = {x for r in rel_rows for x in (r["source"], r["target"])}
    ends = {e.id: e for e in db.scalars(select(Entity).where(Entity.id.in_(list(end_ids))))} if end_ids else {}
    for r in rel_rows:
        for side in ("source", "target"):
            e = ends.get(r[side])
            r[f"{side}_label"] = f"{e.type}: {mask_label(ontology, e.type, e.label, role)}" if e else r[side]
    tl = timeline(db, entity_ids=ent_ids, limit=200, bucket="day") if ent_ids else {"events": [], "total": 0, "histogram": {"series": []}}
    signals = db.scalars(select(Signal).where(Signal.entity_ids.overlap(ent_ids)).order_by(Signal.created_at.desc()).limit(100)).all() if ent_ids else []
    assertions = db.scalars(select(Assertion).where(Assertion.investigation_id == inv.id)).all()
    # data sources behind everything in scope
    record_ids = {rid for e in ents for rid in e.source_ids} | {rid for r in rel_rows for rid in (r["source_records"] or [])}
    src_rows = db.execute(
        select(SourceRecord.source_id, SourceRecord.transformation_version, SourceRecord.ingested_at).where(SourceRecord.id.in_(list(record_ids)[:20000]))
    ).all() if record_ids else []
    by_source: dict[str, dict[str, Any]] = {}
    for sid, ver, at in src_rows:
        s = by_source.setdefault(sid, {"records": 0, "transformation_versions": set(), "first_ingested": at, "last_ingested": at})
        s["records"] += 1
        s["transformation_versions"].add(ver)
        s["first_ingested"] = min(s["first_ingested"], at)
        s["last_ingested"] = max(s["last_ingested"], at)
    sources = []
    for sid, s in sorted(by_source.items()):
        ds = db.get(DataSource, sid)
        sources.append({"source_id": sid, "name": ds.name if ds else sid, "classification": ds.classification if ds else None,
                        "records_cited": s["records"], "transformation_versions": sorted(s["transformation_versions"]),
                        "ingested": [s["first_ingested"].isoformat(), s["last_ingested"].isoformat()]})
    geo_points = [(e.lat, e.lon) for e in ents if e.lat is not None] + [(ev["lat"], ev["lon"]) for ev in tl["events"] if ev.get("lat") is not None]
    geo = {"points": len(geo_points)}
    if geo_points:
        lats, lons = [p[0] for p in geo_points], [p[1] for p in geo_points]
        geo.update(bbox=[min(lons), min(lats), max(lons), max(lats)])
        locs = Counter(ev.get("location_id") for ev in tl["events"] if ev.get("location_id"))
        geo["most_frequent_locations"] = [{"location_id": k, "events": v} for k, v in locs.most_common(5)]
    pending_er = db.scalars(select(ResolutionCandidate).where(
        ResolutionCandidate.decision == "POSSIBLE_MATCH", ResolutionCandidate.review_status == "UNREVIEWED",
        (ResolutionCandidate.entity_a.in_(ent_ids)) | (ResolutionCandidate.entity_b.in_(ent_ids)))).all() if ent_ids else []
    ent_dicts = [entity_dict(e, ontology, role) for e in ents]
    masked = sum(len(d["masked_fields"]) for d in ent_dicts)
    limitations = list(STANDARD_LIMITATIONS)
    if pending_er:
        limitations.append(f"{len(pending_er)} unreviewed POSSIBLE_MATCH entity-resolution candidate(s) involve entities in scope.")
    if masked:
        limitations.append(f"{masked} field(s) are masked for the report author's role ({role}).")
    if tl.get("total", 0) > len(tl["events"]):
        limitations.append(f"Timeline lists {len(tl['events'])} of {tl['total']} events.")
    type_counts = Counter(e.type for e in ents)
    return {
        "title": f"Investigation Report — {inv.name}",
        "classification_banner": "SYNTHETIC / DEMONSTRATION DATA" if any("SYNTHETIC" in (s["classification"] or "") for s in sources) else "UNCLASSIFIED",
        "generated_at": utcnow().isoformat(),
        "generated_by": author,
        "decision_support_notice": "This report supports human decision-making. It does not make determinations about any person or organisation.",
        "sections": {
            "Investigation Summary": {"id": inv.id, "name": inv.name, "description": inv.description, "status": inv.status,
                                      "created_by": inv.created_by, "created_at": inv.created_at.isoformat(), "updated_at": inv.updated_at.isoformat(),
                                      "counts": {"entities": len(ents), "relationships": len(rel_rows), "events": tl.get("total", 0),
                                                 "signals": len(signals), "assertions": len(assertions), "evidence_items": len(items)}},
            "Scope": inv.scope or {"note": "No explicit scope recorded."},
            "Entities": {"by_type": dict(type_counts), "items": ent_dicts},
            "Relationships": {"items": rel_rows},
            "Timeline": {"span": tl.get("span"), "events": tl["events"][:100], "histogram": tl["histogram"]},
            "Geographic Findings": geo,
            "Analytical Signals": {"label": SIGNAL_LABEL, "note": "Signals are not conclusions. Review evidence and alternative explanations.",
                                   "items": [{"id": s.id, "rule_id": s.rule_id, "rule_version": s.rule_version, "score": s.score,
                                              "what_happened": s.explanation.get("what_happened"),
                                              "alternative_explanations": s.explanation.get("alternative_explanations", []),
                                              "time_window": s.explanation.get("time_window"), "entity_ids": s.entity_ids[:20]} for s in signals]},
            "Evidence": {"items": [item_dict(i) for i in items if i.kind not in ("entity", "relationship")]},
            "Analyst Assertions": {"note": "Hypotheses recorded by analysts — not source-derived facts.", "items": [assertion_dict(a) for a in assertions]},
            "Data Sources": sources,
            "Limitations": limitations,
        },
    }


def to_markdown(rep: dict[str, Any]) -> str:
    s = rep["sections"]
    lines = [f"# {rep['title']}", "", f"**{rep['classification_banner']}**", "", f"_{rep['decision_support_notice']}_", "",
             f"Generated {rep['generated_at']} by {rep['generated_by']}", ""]
    summ = s["Investigation Summary"]
    lines += ["## Investigation Summary", "", summ["description"] or "", "", *[f"- {k}: {v}" for k, v in summ["counts"].items()], ""]
    lines += ["## Scope", "", *[f"- {k}: {v}" for k, v in s["Scope"].items()], ""]
    lines += ["## Entities", "", "| Type | Label | Confidence | Status | Sources |", "|---|---|---|---|---|"]
    lines += [f"| {e['type']} | {e['label']} | {e['confidence']:.2f} | {e['epistemic_status']} | {len(e['source_ids'])} |" for e in s["Entities"]["items"]]
    lines += ["", "## Relationships", "", "| Source | Type | Target | Time | Confidence | Status | Source records |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {r['source_label']} | {r['relationship_type']} | {r['target_label']} | {r['timestamp'] or ''} | {r['confidence']:.2f} | {r['epistemic_status']} | "
              f"{', '.join((r['source_records'] or [])[:2])} |" for r in s["Relationships"]["items"][:200]]
    lines += ["", "## Timeline", "", f"Span: {s['Timeline']['span']}", ""]
    lines += [f"- {ev['timestamp']} — {ev['event_type']} (source: {ev['source']})" for ev in s["Timeline"]["events"][:50]]
    lines += ["", "## Geographic Findings", "", *[f"- {k}: {v}" for k, v in s["Geographic Findings"].items()], ""]
    lines += ["## Analytical Signals", "", f"> {s['Analytical Signals']['note']}", ""]
    for sig in s["Analytical Signals"]["items"]:
        lines += [f"### {SIGNAL_LABEL} — {sig['rule_id']} (v{sig['rule_version']}, score {sig['score']})", "", sig["what_happened"] or "", "",
                  "Alternative explanations:", *[f"- {a}" for a in sig["alternative_explanations"]], ""]
    lines += ["## Evidence", ""] + [f"- [{i['kind']}] {i['title']} ({i['epistemic_status']})" for i in s["Evidence"]["items"]] + [""]
    lines += ["## Analyst Assertions", "", f"> {s['Analyst Assertions']['note']}", ""]
    lines += [f"- **{a['label']}**: {a['statement']} — by {a['created_by']}" for a in s["Analyst Assertions"]["items"]] + [""]
    lines += ["## Data Sources", ""] + [f"- {d['name']} ({d['source_id']}, {d['classification']}): {d['records_cited']} records, "
                                         f"transformations {', '.join(d['transformation_versions'])}" for d in s["Data Sources"]] + [""]
    lines += ["## Limitations", ""] + [f"- {x}" for x in s["Limitations"]]
    return "\n".join(lines) + "\n"


def to_pdf(rep: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    banner = rep["classification_banner"]

    def on_page(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.HexColor("#a15c00"))
        canvas.drawCentredString(A4[0] / 2, A4[1] - 10 * mm, banner)
        canvas.drawCentredString(A4[0] / 2, 8 * mm, f"{banner} — page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, title=rep["title"], leftMargin=15 * mm, rightMargin=15 * mm, topMargin=18 * mm, bottomMargin=16 * mm)
    st = getSampleStyleSheet()
    small = st["BodyText"].clone("small", fontSize=7.5, leading=9)
    esc = lambda x: str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    flow: list[Any] = [Paragraph(esc(rep["title"]), st["Title"]), Paragraph(esc(rep["decision_support_notice"]), st["Italic"]),
                       Paragraph(f"Generated {esc(rep['generated_at'])} by {esc(rep['generated_by'])}", small), Spacer(1, 6)]
    s = rep["sections"]

    def table(header: list[str], rows: list[list[Any]], widths: list[float] | None = None) -> Table:
        data = [[Paragraph(f"<b>{esc(h)}</b>", small) for h in header]] + [[Paragraph(esc(c), small) for c in r] for r in rows]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecf2")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    flow += [Paragraph("Investigation Summary", st["Heading2"]), Paragraph(esc(s["Investigation Summary"]["description"]), st["BodyText"]),
             table(["Metric", "Count"], [[k, v] for k, v in s["Investigation Summary"]["counts"].items()], [60 * mm, 30 * mm])]
    flow += [Paragraph("Scope", st["Heading2"]), table(["Key", "Value"], [[k, v] for k, v in s["Scope"].items()], [40 * mm, 135 * mm])]
    flow += [Paragraph("Entities", st["Heading2"]),
             table(["Type", "Label", "Conf.", "Status", "Sources"], [[e["type"], e["label"], f"{e['confidence']:.2f}", e["epistemic_status"],
                                                                     len(e["source_ids"])] for e in s["Entities"]["items"]],
                   [25 * mm, 70 * mm, 15 * mm, 35 * mm, 20 * mm])]
    flow += [Paragraph("Relationships", st["Heading2"]),
             table(["Source", "Type", "Target", "Time", "Conf.", "Source records"],
                   [[r["source_label"], r["relationship_type"], r["target_label"], r["timestamp"] or "", f"{r['confidence']:.2f}",
                     ", ".join((r["source_records"] or [])[:2])] for r in s["Relationships"]["items"][:150]],
                   [32 * mm, 24 * mm, 32 * mm, 30 * mm, 12 * mm, 50 * mm])]
    flow += [Paragraph("Timeline", st["Heading2"]),
             table(["Time", "Event", "Source", "Entities"], [[ev["timestamp"], ev["event_type"], ev["source"], len(ev["entity_ids"])]
                                                            for ev in s["Timeline"]["events"][:80]], [40 * mm, 35 * mm, 60 * mm, 20 * mm])]
    flow += [Paragraph("Geographic Findings", st["Heading2"]), table(["Key", "Value"], [[k, v] for k, v in s["Geographic Findings"].items()],
                                                                     [45 * mm, 130 * mm])]
    flow += [Paragraph("Analytical Signals", st["Heading2"]), Paragraph(esc(s["Analytical Signals"]["note"]), st["Italic"])]
    for sig in s["Analytical Signals"]["items"]:
        flow += [Paragraph(f"<b>{SIGNAL_LABEL}</b> — {esc(sig['rule_id'])} v{sig['rule_version']} (score {sig['score']})", st["BodyText"]),
                 Paragraph(esc(sig["what_happened"] or ""), small),
                 Paragraph("Alternative explanations: " + esc("; ".join(sig["alternative_explanations"])), small), Spacer(1, 3)]
    flow += [Paragraph("Evidence", st["Heading2"]), table(["Kind", "Title", "Status"], [[i["kind"], i["title"], i["epistemic_status"]]
                                                                                       for i in s["Evidence"]["items"]], [30 * mm, 110 * mm, 35 * mm])]
    flow += [Paragraph("Analyst Assertions", st["Heading2"]), Paragraph(esc(s["Analyst Assertions"]["note"]), st["Italic"]),
             table(["Label", "Statement", "By"], [[a["label"], a["statement"], a["created_by"]] for a in s["Analyst Assertions"]["items"]],
                   [45 * mm, 100 * mm, 30 * mm])]
    flow += [Paragraph("Data Sources", st["Heading2"]),
             table(["Source", "Classification", "Records", "Transformations"], [[d["name"], d["classification"], d["records_cited"],
                                                                               ", ".join(d["transformation_versions"])] for d in s["Data Sources"]],
                   [55 * mm, 50 * mm, 20 * mm, 50 * mm])]
    flow += [Paragraph("Limitations", st["Heading2"])] + [Paragraph("• " + esc(x), small) for x in s["Limitations"]]
    doc.build(flow, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
