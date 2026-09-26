# Demonstration investigation transcript

> All data is SYNTHETIC / DEMONSTRATION DATA. Outputs are decision support, not conclusions.

## Step 1. Search an entity

Query `device:DV-7F3A-SHARED` → 1 match: **DV-7F3A-SHARED** (`devi_c54142cba994ccc51e36`).
Match reasons: device exact identifier match.

## Step 2. Open entity profile

Type Device, status DERIVED, confidence 1.0.
Relationship counts: {'CONNECTED_TO': 42, 'USED': 35, 'VISITED': 28}.
17 analytical signal(s) involve this device, e.g. *Device devi_c54142cba994ccc51e36 has USED relationships with 7 distinct Account entities within 30 days (threshold > 5).*

## Step 3. Expand graph (1 hop)

12 nodes / 105 edges; node types {'Device': 1, 'Account': 7, 'Location': 2, 'IPAddress': 1, 'Domain': 1}; truncated=False.

## Step 4. Filter relationships

USED edges in March 2026 only → 7 accounts used the device.
Then OWNS (inbound, any time) → 7 distinct account owners (persons).
Time filters apply to timestamped relationships, so ownership established earlier is queried separately.

## Step 5. Open timeline

35 events between 2026-03-01T01:18:00+00:00 and 2026-03-19T02:10:00+00:00; by type {'auth_failure': 7, 'device_connection': 7, 'dns_query': 7, 'location_change': 7, 'login': 7}.
7 group(s) of near-simultaneous events (≤180 s).

- 2026-03-01T01:18:00+00:00 — auth_failure (source `synthetic_activity`)
- 2026-03-01T01:30:00+00:00 — login (source `synthetic_activity`)
- 2026-03-01T01:42:00+00:00 — device_connection (source `synthetic_activity`)
- 2026-03-01T01:44:00+00:00 — dns_query (source `synthetic_activity`)
- 2026-03-01T02:10:00+00:00 — location_change (source `synthetic_activity`)

## Step 6. Open map

28 transactions initiated by these accounts within 2 km of Harbor Plaza in March 2026.
Device trajectory: 28 located events. (Trajectory joins event locations in time order; straight segments are not observed routes.)

## Step 7. Inspect provenance (why does this relationship exist?)

USED exists because source record(s) src_d24065db1d4a564c1b27 from source 'synthetic_device_usage' were mapped by 'mapping:device_usage' (version map-1.0+9eaa9e32). Status: DERIVED; confidence 1.00.

- Source: Device-session telemetry (synthetic) (`synthetic_device_usage`, SYNTHETIC / DEMONSTRATION DATA)
- Source record: `row-1985-68bda6098096` (hash `68bda6098096fdc3…`)
- Ingested: 2026-09-26T09:53:03.474365+00:00
- Transformation: map-1.0+9eaa9e32
- Confidence: 1.0
- Analyst modifications: 0
- Lineage: source_record:src_d24065db1d4a564c1b27 → relationship:rel_1eb36ef228978cd6890c

## Step 8. Create hypothesis

Investigation `inv_89b0c96a6f0d4496` created; 11 entities pinned with provenance snapshots.
Assertion `asr_b781713da743450d` recorded as **ANALYST ASSERTION — HYPOTHESIS** (epistemic status ANALYST_ASSERTION).

## Step 9. Save investigation

Saved query `sq_0f375bc9ec4e4dac` → 1 device(s) shared by >3 persons (DV-7F3A-SHARED × 7).
Investigation saved at version 18 (status ON_HOLD); every change is in the audit log.

## Step 10. Export report

Report sections: Investigation Summary, Scope, Entities, Relationships, Timeline, Geographic Findings, Analytical Signals, Evidence, Analyst Assertions, Data Sources, Limitations.
Files: `investigation_report.{md,pdf,json}`, `investigation_export.{entities.csv,relationships.csv,graphml,geojson,json}`.

---

Limitations recorded in the report:

- All results depend on the completeness and accuracy of ingested sources; absence of data is not evidence of absence.
- Relationships reflect recorded associations. They do not by themselves establish intent, causation, control or wrongdoing.
- Analytical signals are outputs of deterministic rules and graph mathematics. They are prompts for review, not findings.
- Entity resolution is deterministic but imperfect: unmerged duplicates and incorrect merges are both possible.
- Graph views and path searches are windowed and fan-out limited; truncated searches may omit connections.
- Analyst assertions are hypotheses recorded by people and have not been independently verified unless stated.
