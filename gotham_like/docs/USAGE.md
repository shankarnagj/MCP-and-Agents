# Usage guide

This guide covers what you can feed into Tessera, how to set it up, and how to use it day to day.
For installation details see [SETUP.md](SETUP.md); for every endpoint see [API.md](API.md).

---

## 1. Setup in five minutes

**Docker (recommended)**

```bash
git clone <this repo> && cd <repo>/docker
python ../scripts/gen_secrets.py > .env                  # generates DB password, JWT and encryption keys
echo "TESSERA_DEMO_PASSWORD=Choose-A-Demo-Passw0rd!" >> .env
docker compose up -d --build db redis backend frontend
docker compose --profile seed run --rm seed              # schema + demo users + synthetic data + rules
```

Open http://localhost:8080 and sign in as `investigator` with the demo password.

**Without Docker**: Python 3.12, Node 20+, PostgreSQL 16 + PostGIS 3.4 + pg_trgm, optional Redis 7:

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
python scripts/seed_demo.py                              # uses TESSERA_DATABASE_URL
(cd backend && uvicorn app.main:app --port 8000)
(cd frontend && npm ci && npm run dev)                   # http://localhost:5173
```

### Demo users and roles

| User | Role | Can |
|---|---|---|
| `viewer` | VIEWER | search, read, graph, timeline, map, provenance — personal data **masked** |
| `analyst` | ANALYST | + see PII, create investigations / hypotheses / saved queries, export, manage alerts |
| `investigator` | INVESTIGATOR | + see restricted fields, verify/dispute relationships, review entity-resolution merges, request deletions |
| `admin` | ADMIN | + users, ontology, rules, data sources, audit log, approve deletions |

Demo users are for local use only. In production create users with `POST /api/users`.

---

## 2. Types of input

Tessera ingests **records** from sources, turns them into **entities**, **relationships** and **events**
according to a declarative **mapping**, and keeps a link from every derived object back to its record.

### 2.1 Supported source formats (connectors)

| Format | Connector | Notes | Example in `data/synthetic/` |
|---|---|---|---|
| CSV | `CSVConnector(path, record_type, id_field)` | header row required; streamed | `persons_crm.csv`, `accounts.csv`, `locations.csv` |
| JSON | `JSONConnector(path, record_type, id_field, items_path)` | array of objects at a dotted path, e.g. `organizations` | `organizations.json`, `domains.json` |
| JSON Lines | `JSONLConnector(path, record_type, id_field)` | one object per line | `events.jsonl`, `devices.jsonl`, `shipments.jsonl` |
| Parquet | `ParquetConnector(path, record_type, id_field)` | streamed by row group | `transactions.parquet` |
| PostgreSQL | `PostgresConnector(dsn, table, record_type, id_field, columns, schema, equals_filters)` | read-only, server-side cursor; DSN stored encrypted | — |
| REST API | `RESTConnector(url, record_type, id_field, items_path, headers, next_cursor_path)` | JSON, cursor pagination; headers kept out of provenance | — |

`id_field` is the source's stable record id. If there is none, a content hash is used, so re-ingesting
unchanged data is a no-op and changed records are detected (and can raise a *source change* alert).

### 2.2 What the data can describe (ontology)

**Entity types** (15): Person, Organization, Account, Device, Transaction, Location, Address,
IPAddress, Domain, Vehicle, Shipment, Vessel, Event, Document, Case.

**Relationship types** (22): OWNS, WORKS_FOR, EMPLOYED_BY, CONTROLS, INITIATED, TRANSFERRED_TO,
TRANSACTED_WITH, LOCATED_AT, REGISTERED_AT, CONNECTED_TO, USED, COMMUNICATED_WITH, VISITED,
RESOLVES_TO, SHIPPED_BY, SHIPPED_TO, CARRIED_BY, PASSED_THROUGH, ASSOCIATED_WITH, DERIVED_FROM,
MENTIONS, PART_OF.

**Event types**: login, logout, auth_failure, transaction, device_connection, location_change,
shipment_departure, shipment_arrival, port_call, alert, incident, communication, process_start,
dns_query, account_opened, maintenance.

Each property has a **type** (`string, number, integer, boolean, date, datetime`), a **sensitivity**
(`public`, `pii` – masked for VIEWER, `restricted` – INVESTIGATOR/ADMIN only), and optionally an
**identifier kind** (email, phone, ip, account, device …) used for exact lookup and entity resolution.
Full reference: [ONTOLOGY.md](ONTOLOGY.md). To add a type or property, edit
`data/schemas/ontology.json` (or `PUT /api/ontology` as ADMIN).

### 2.3 Field conventions the mappings understand

| Kind of value | Accepted input | Normalised to |
|---|---|---|
| Timestamps | ISO-8601 (`2026-03-01T10:00:00Z`, `2026-03-01`), Unix seconds | UTC `timestamptz` |
| Coordinates | decimal `lat` / `lon` columns (−90..90 / −180..180) | PostGIS `geography(Point)`; out-of-range values are rejected |
| E-mail | any case, `+tag` sub-addressing | lower-case, tag removed |
| Phone | `(202) 555 0101`, `+1-202-555-0101`, `0044…` | E.164-like `+12025550101` |
| IP / domain | `010.1.1.1` rejected; `https://www.x.com/path` | canonical IP / `x.com` |
| Names / organisations | titles (Dr, Mr), accents, legal suffixes (Ltd, GmbH …) | normalised tokens for matching |
| Identifiers | `ACC-000 12` | `ACC00012` |
| Numbers | `"12.5"` | typed according to the ontology |

### 2.4 Writing a mapping

Mappings live in `data/schemas/mappings.json`. Example for a CSV of card payments with columns
`txn_id, from_account, merchant, amount, ts, lat, lon`:

```json
{"record_type": "card_payment",
 "entities": [
   {"key": "t", "type": "Transaction", "key_template": "{txn_id}", "lat": "lat", "lon": "lon", "observed_at": "ts",
    "properties": {"transaction_id": "txn_id", "amount": "amount", "timestamp": "ts", "channel": {"const": "card"}}},
   {"key": "a", "type": "Account", "key_template": "{from_account}", "stub": true},
   {"key": "m", "type": "Organization", "key_template": "{merchant}", "properties": {"name": "merchant"}}],
 "relationships": [
   {"type": "INITIATED", "source": "a", "target": "t", "timestamp": "ts"},
   {"type": "TRANSFERRED_TO", "source": "t", "target": "m", "timestamp": "ts"}],
 "events": [
   {"event_type": "transaction", "timestamp": "ts", "entities": ["a", "t", "m"], "lat": "lat", "lon": "lon"}]}
```

* `key_template` builds a **natural key**; the same key from different sources converges on the same entity.
* `stub: true` references an entity defined elsewhere without overwriting its properties.
* `type` may be a template (e.g. `"{owner_type}"`) when a column says which type the value is.
* Property values: a column name, `{"template": "..."}`, or `{"const": ...}`.
* Relationships are checked against the ontology (e.g. `OWNS` cannot start from a Transaction).
* The mapping's hash becomes the **transformation version** recorded in lineage, so any change is traceable.

### 2.5 Loading it

Register the source in `data/schemas/sources.json` (or `POST /api/sources`), then:

```python
from app.db import SessionLocal
from app.ingestion.csv import CSVConnector
from app.ingestion.mapping import load_mappings
from app.ingestion.pipeline import ensure_source, run_ingestion
from app.entity_resolution.service import resolve_type
from app.ontology import get_ontology

db = SessionLocal(); onto = get_ontology()
maps = load_mappings("data/schemas/mappings.json")
src = ensure_source(db, "card_feed", "Card payments", "csv", classification="INTERNAL")
res = run_ingestion(db, onto, src, CSVConnector("payments.csv", "card_payment", "txn_id"), maps["card_payment"])
resolve_type(db, onto, "Person")          # deterministic entity resolution
db.commit(); print(res.summary())
```

Then evaluate rules: `POST /api/rules/{id}/evaluate` (or `evaluate_all` in `app/rules/engine.py`).

### 2.6 Other inputs

| Input | Where |
|---|---|
| Documents (pdf, txt, csv, png, jpeg, json ≤ 10 MB) | Investigation → Evidence → *Attach document* / `POST /api/investigations/{id}/documents` |
| Notes, citations, hypotheses | Investigation tab or `/api/investigations/{id}/items`, `/api/assertions` |
| Geofences (GeoJSON Polygon) | `POST /api/geo/geofences` |
| Rules (JSON definitions, 8 kinds) | `data/schemas/rules.json` or `PUT /api/rules/{id}` |
| Ontology changes | `data/schemas/ontology.json` or `PUT /api/ontology` |

---

## 3. Using the workbench

Layout: **command bar** on top · **Entities / Filters / Alerts / ER** on the left · main workspace
(**Graph · Map · Timeline · Table · Entity · Investigation · Query**) · **evidence / details** on the
right · compact **timeline / table** at the bottom. Panels are resizable.

Typical flow — *Search → Inspect → Expand → Filter → Correlate → Investigate → Explain*:

1. **Search** (`Ctrl+K`). Query syntax:

   | You type | Meaning |
   |---|---|
   | `John Smith` / `~Jhon Smiht` | fuzzy / looser fuzzy |
   | `"John Smith"` | exact phrase |
   | `Joh*` | prefix |
   | `account:12345` `device:ABC123` `ip:10.10.10.10` `email:` `phone:` `domain:` `txn:` `shipment:` `imo:` `id:` | identifier lookup |
   | `company:Acme` `person:"Jane Doe"` `location:` `vessel:` | name search within a type |
   | `type:Person` `-type:Transaction` | include / exclude types |
   | `city:Marisk` `jurisdiction:"Castellan Isles"` | any ontology property |
   | `after:2026-01-01` `before:…` `on:2026-02-14` | dates |
   | `near:51.45,3.60,2km` `bbox:minLon,minLat,maxLon,maxLat` | geography |

   Enter adds the highlighted result; Shift+Enter adds it with its neighbours. Commands start with
   `>`: `>graph`, `>map`, `>timeline`, `>clear`.
2. **Inspect** — the right panel shows properties (masked by role), relationship counts, analytical
   signals, entity-resolution history and hypotheses.
3. **Expand** — *Expand 1-hop / 2-hop* or double-click a node. Large neighbourhoods are capped and
   marked "Partial view".
4. **Filter** — Filters tab: relationship types, time window, minimum confidence, epistemic status,
   hide entity types. Filters also apply to new expansions (server-side).
5. **Correlate** — Timeline (zoom, then *Apply as time filter*; simultaneous events flagged), Map
   (heatmap, radius query, trajectories, geofences), path finding (shift-click two nodes →
   *Shortest path* / *Constrained path*), graph analytics (degree, betweenness, PageRank).
6. **Investigate** — Investigation tab: create, pin entities/edges/events/signals, add notes,
   citations and documents, record hypotheses, pin map/timeline views, save queries.
   Collaborators see changes live.
7. **Explain** — click any edge for *Why does this relationship exist?* (source, source record,
   ingestion time, transformation, confidence, analyst modifications). Signals answer: what happened,
   why shown, which data, when collected, assumptions, uncertainty, alternative explanations.
   Export a **report** (PDF / Markdown / JSON) or **data** (CSV / JSON / GraphML / GeoJSON), always
   with provenance metadata.

### Visual query builder (Query tab)

Define nodes (variable + type + property filters) and relationships (type + time window), optionally
aggregate ("group by d, count distinct p > 3"), run it, and inspect the step-by-step plan and SQL.
Presets include *devices shared by > 3 persons*, *large transfers into offshore-company accounts*,
and *control chains*.

### Reading the badges

| Badge | Meaning |
|---|---|
| RAW | original source record |
| DERIVED | produced from source records by a versioned mapping |
| INFERENCE | produced by an algorithm (entity resolution, rules, analytics) — not an established fact |
| ASSERTION / HYPOTHESIS | written by an analyst |
| VERIFIED | a derived fact an investigator explicitly verified (history kept) |
| ANALYTICAL SIGNAL | a rule or graph metric fired — a prompt for review, never a verdict |

---

## 4. Using the API directly

```bash
T=$(curl -s localhost:8000/api/auth/login -H 'content-type: application/json' \
      -d '{"username":"analyst","password":"<demo password>"}' | jq -r .access_token)
curl -s localhost:8000/api/search -H "Authorization: Bearer $T" -H 'content-type: application/json' \
      -d '{"query":"device:DV-7F3A-SHARED"}' | jq '.results[0]'
```

More examples: [EXAMPLE_QUERIES.md](EXAMPLE_QUERIES.md). Interactive docs: http://localhost:8000/docs.

---

## 5. Useful scripts

| Script | Purpose |
|---|---|
| `scripts/generate_synthetic.py` | regenerate the synthetic dataset (fixed seed) |
| `scripts/seed_demo.py` | migrations + demo users + load + entity resolution + rules |
| `scripts/demo_investigation.py` | run the 10-step demo investigation via the API → `docs/examples/` |
| `scripts/verify_all.py` | run every test suite and print PLATFORM VERIFICATION |
| `scripts/benchmark.py [--quick]` | performance benchmark (1M entities / 10M relationships by default) |
| `scripts/gen_secrets.py` | generate production secrets |
| `scripts/apply_retention.py` | redact raw records past their retention period |
| `scripts/export_openapi.py` · `gen_ontology_doc.py` · `gen_benchmark_doc.py` | regenerate docs |
