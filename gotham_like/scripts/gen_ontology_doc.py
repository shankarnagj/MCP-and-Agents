#!/usr/bin/env python3
"""Render data/schemas/ontology.json to docs/ONTOLOGY.md."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
o = json.loads((ROOT / "data" / "schemas" / "ontology.json").read_text())
L = [f"# Ontology `{o['name']}` v{o['version']}", "", o["description"], "",
     "The ontology is **data**: edit `data/schemas/ontology.json` (or `PUT /api/ontology` as ADMIN). Ingestion mappings, search, the query builder,",
     "entity resolution and field-level masking all read it at run time. Removing a type that is still in use is refused.", "",
     "## Sensitivity levels", "", "| Level | Meaning |", "|---|---|", *[f"| `{k}` | {v} |" for k, v in o["sensitivity_levels"].items()], "",
     "## Entity types", ""]
for name, t in o["entity_types"].items():
    L += [f"### {name}", "", t.get("description", ""), "", f"Label property: `{t['label']}`", "",
          "| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |", "|---|---|---|---|---|---|"]
    for p, d in t["properties"].items():
        L.append(f"| `{p}` | {d.get('type', 'string')} | {d.get('sensitivity', 'public')} | {'yes' if d.get('searchable') else ''} | "
                 f"{d.get('identifier') or ''} | {d.get('resolution') or ''} |")
    L.append("")
L += ["## Relationship types", "", "| Type | From | To | Symmetric | Description |", "|---|---|---|---|---|"]
for name, r in o["relationship_types"].items():
    L.append(f"| `{name}` | {', '.join(r['source_types'])} | {', '.join(r['target_types'])} | {'yes' if r.get('symmetric') else ''} | {r.get('description', '')} |")
L += ["", "## Event types", "", ", ".join(f"`{e}`" for e in o["event_types"]), "",
      "## Common fields", "", "Every **entity** stores `id, type, properties, source_ids, created_at, updated_at, confidence, provenance, epistemic_status`.",
      "Every **relationship** stores `id, source, target, relationship_type, timestamp, confidence, source_records, provenance, epistemic_status, analyst_modifications`.",
      "Every **event** stores `timestamp, start_time, end_time, entity_ids, location, event_type, source`."]
(ROOT / "docs" / "ONTOLOGY.md").write_text("\n".join(L) + "\n")
print("wrote docs/ONTOLOGY.md")
