# REST & WebSocket API

Base URL: `http://127.0.0.1:8000`. Interactive docs: `/docs` (Swagger UI) and `/redoc`.
Machine-readable spec: [`docs/openapi.json`](openapi.json) (regenerate with `python scripts/export_openapi.py`).

All `/api/*` endpoints except `POST /api/auth/login` require `Authorization: Bearer <token>`.
Errors are JSON `{"detail": …}`: `401` unauthenticated · `403` missing permission / not a
collaborator · `404` · `409` version conflict · `413` body too large · `422` validation ·
`429` rate limited. Every response carries `x-request-id` and `x-response-time-ms`.

## Authentication & users

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST | `/api/auth/login` | — | `{"username","password"}` → `{access_token, expires_in, user}` |
| POST | `/api/auth/logout` | any | revokes the server-side session |
| GET | `/api/auth/me` | any | id, username, role, permissions |
| GET/POST | `/api/users` | `users:manage` | create: `{"username","password","role","display_name"}` |
| PATCH | `/api/users/{id}` | `users:manage` | `{"role"?, "is_active"?, "display_name"?}` (disabling revokes sessions) |

## Entities, relationships, search

| Method | Path | Notes |
|---|---|---|
| GET | `/api/entities?type=&limit=&offset=&sort=` | paginated list (live entities only) |
| GET | `/api/entities/{id}` | full profile: masked properties, `masked_fields`, degree by type, signals, assertions, ER candidates; merged ids redirect (`redirected_from`) |
| GET | `/api/entities/{id}/relationships?relationship_type=&direction=&time_from=&time_to=&limit=&offset=` | paginated edges with the other endpoint |
| GET | `/api/relationships/{id}` | edge + endpoints |
| POST | `/api/relationships/{id}/review` | `relationship:verify`; `{"action":"verify|dispute|annotate","note","confidence"?}` — history kept in `analyst_modifications` |
| POST | `/api/search` | `{"query","entity_types"?,"date_from"?,"date_to"?,"near"?:[lat,lon,m],"limit","offset"}` |
| GET | `/api/search?q=` | convenience form |

Search query language (see `app/search/parser.py`):

```
John Smith                  fuzzy (trigram word-similarity ≥ 0.45)
"John Smith"                exact phrase
Joh*                        prefix
~Jhon Smiht                 loose fuzzy (≥ 0.3)
account:12345  device:ABC123  ip:10.10.10.10  email:a@b.example  phone:+1…  domain:x.example  txn:TX-1  shipment:SHP-1  imo:IMO9000137  id:<source key>
company:Acme  org:Acme  person:"Jane Doe"  location:Harbor  vessel:Star
type:Person  -type:Transaction
city:Marisk  jurisdiction:"Castellan Isles"   (any ontology property; protected fields refused for unauthorised roles)
after:2026-01-01  before:2026-02-01  on:2026-02-14
near:51.45,3.60,2km   bbox:minLon,minLat,maxLon,maxLat
```

Response: `results[]` (masked), `total_estimate`, `facets.type`, `parsed` (the structured query
and warnings), `match_reasons`, and a note that retrieval similarity is not an identity claim.

## Graph

| Method | Path | Body |
|---|---|---|
| POST | `/api/graph/subgraph` | `{"seeds":[…],"depth":0-5,"filters":{relationship_types,direction,time_from,time_to,min_confidence,neighbor_types,epistemic_statuses},"max_nodes","fanout","include_edges_among"}` → `nodes`, `edges`, `hops[]`, `truncated`, `truncation_reasons` |
| POST | `/api/graph/path` | `{"source","target","mode":"shortest|all_simple|weighted","max_depth":1-8,"relationship_types"?,"respect_direction","max_paths","filters"}` → `paths[].steps[]` each with `relationship_type`, `direction`, `timestamp`, `confidence`, `epistemic_status`, `source_records`, `provenance`; plus `search` diagnostics and `explanation` |
| POST | `/api/graph/analytics` | `{"seeds","depth","algorithms":[degree_centrality,betweenness_centrality,pagerank,connected_components,strongly_connected_components,communities,k_core,cycles,shortest_paths],"k_core","max_cycle_len","top_k"}` → labelled `ANALYTICAL SIGNAL` with caveat |

## Timeline & geospatial

| Method | Path | Notes |
|---|---|---|
| GET | `/api/timeline?entity_id=&event_type=&source=&time_from=&time_to=&lat=&lon=&radius_m=&bucket=minute|hour|day|week|month&limit=&offset=&simultaneous_window_s=` | events, histogram by bucket × type, `by_type`, `simultaneous.groups` |
| POST | `/api/geo/query` | `{"lat","lon","radius_m"}` **or** `{"geometry": GeoJSON}` + `time_from/time_to`, `entity_types`, `event_types`, `related_to`, `relationship_types`, `include` — the combined time × space × entity × relationship query |
| GET | `/api/geo/nearest?lat=&lon=&k=&entity_type=` | index-assisted KNN |
| GET/POST | `/api/geo/geofences` | GeoJSON FeatureCollection / create Polygon (validated) |
| GET | `/api/geo/geofences/{id}/events` | events inside a geofence |
| GET | `/api/geo/trajectory/{entity_id}` | time-ordered LineString of an entity's located events |
| GET | `/api/geo/heatmap?cell_deg=&event_type=&time_from=&time_to=&min_lon=…` | grid aggregation (heatmap / clusters) |

## Provenance & lineage

| Method | Path | Notes |
|---|---|---|
| GET | `/api/provenance/{id}` | any entity / relationship / event / source record / signal / assertion: `why`, `object`, `source_records[]` (source, record id, ingestion timestamp, transformation version, hash, payload for PII-cleared roles), `lineage_upstream`, `lineage_downstream`, `entity_resolution`, `analyst_modifications` |
| GET | `/api/provenance/{id}/lineage?kind=&direction=up|down` | lineage graph only |

## Investigations, evidence, assertions, queries

| Method | Path | Notes |
|---|---|---|
| POST / GET | `/api/investigations` | create `{"name","description","scope"}`; list (`?mine=true`) |
| GET / PATCH | `/api/investigations/{id}` | full workspace (items, assertions, saved queries, `can_write`); patch with `expected_version` for optimistic concurrency (409 on conflict) |
| POST | `/api/investigations/{id}/items` | `{"kind":"entity|relationship|event|signal|source_record|note|citation|document|map|chart|timeline|saved_query","ref_id","title","content"}` — referenced objects get a provenance snapshot |
| DELETE | `/api/investigations/{id}/items/{item_id}` | |
| POST | `/api/investigations/{id}/documents` | multipart upload (pdf/txt/csv/png/jpeg/json ≤ 10 MB), stored by SHA-256 |
| POST / PATCH / GET | `/api/assertions` | analyst assertions; always created as `HYPOTHESIS`; statuses `SUPPORTED/REFUTED/WITHDRAWN`; full history |
| POST | `/api/query` | visual query-builder pattern → `plan`, `rows`, `entities`; `explain:true` adds parameterised SQL and the PostgreSQL plan |
| POST / GET | `/api/saved-queries` | persisted queries with `query`, `filters`, `parameters`, `created_by`, timestamp |
| POST | `/api/saved-queries/{id}/run` | re-execute a saved pattern |

Pattern example (accounts sharing devices with > 3 persons within March 2026):

```json
{"nodes": [{"var": "p", "type": "Person"}, {"var": "a", "type": "Account"}, {"var": "d", "type": "Device"}],
 "edges": [{"from": "p", "to": "a", "type": "OWNS"},
           {"from": "a", "to": "d", "type": "USED", "time_from": "2026-03-01", "time_to": "2026-03-31"}],
 "aggregate": {"group_by": "d", "count_distinct": "p", "op": ">", "value": 3}}
```

## Rules, signals, alerts

| Method | Path | Notes |
|---|---|---|
| GET | `/api/rules` | definitions (kinds: threshold, unusual_count, cycle, event, sequence, geofence, new_relationship, source_change) |
| PUT | `/api/rules/{id}` | `rules:write`; conclusion words rejected; version bumps |
| POST | `/api/rules/{id}/evaluate` | idempotent (signals are fingerprinted); broadcasts progress + alerts on the WebSocket |
| GET | `/api/signals`, `/api/signals/{id}` | ANALYTICAL SIGNALS with the full explanation block |
| GET / PATCH | `/api/alerts`, `/api/alerts/{id}` | `{id, rule, timestamp, entities, evidence, status}`; statuses OPEN/ACKNOWLEDGED/ESCALATED/DISMISSED |

## Entity resolution

| Method | Path | Notes |
|---|---|---|
| GET | `/api/resolution/candidates?decision=&review_status=` | MATCH / POSSIBLE_MATCH with evidence |
| POST | `/api/resolution/compare` | `{"entity_a","entity_b"}` → decision, score, evidence, human-readable explanation |
| POST | `/api/resolution/candidates/{id}/review` | `{"decision":"CONFIRM|REJECT"}` — confirm merges (reversible), reject on a merged pair unmerges |

## Export & reports

| Method | Path | Notes |
|---|---|---|
| POST | `/api/export` | `{"format":"csv|json|graphml|geojson","entity_ids"|"investigation_id","what":"entities|relationships|events"}`; every format embeds provenance metadata (sources, transformation versions, role applied, masked field count) |
| GET | `/api/investigations/{id}/report?format=json|markdown|pdf` | sections: Investigation Summary, Scope, Entities, Relationships, Timeline, Geographic Findings, Analytical Signals, Evidence, Analyst Assertions, Data Sources, Limitations |

## Governance & system

| Method | Path | Permission |
|---|---|---|
| GET / PUT | `/api/ontology` | read / `ontology:write` |
| GET / POST | `/api/sources` | read / `ingest` (secrets encrypted, never returned) |
| GET | `/api/ingestion-runs` | read |
| GET | `/api/audit?action=&username=&object_id=&before_id=` · `/api/audit/verify` | `audit:read` |
| POST / GET | `/api/privacy/deletion-requests` · POST `/{id}/approve` | request: INVESTIGATOR+; approve: a *different* ADMIN |
| GET | `/api/privacy/retention` | `audit:read` |
| GET | `/api/stats` | read |
| GET | `/health` · `/ready` · `/metrics` · `/api/system/errors` (ADMIN) | |

## WebSocket `/ws`

1. Connect, then send `{"type":"auth","token":"<access token>"}` as the first frame (closed with 4401 otherwise).
2. Server replies `{"event":"ready"}`; you are subscribed to `alerts`.
3. `{"type":"subscribe","topic":"investigation:<id>"|"progress"}`, `{"type":"unsubscribe",…}`,
   `{"type":"presence","topic":"investigation:<id>","state":"viewing"}`, `{"type":"ping"}`.

Messages: `{"topic","event","payload","ts"}` with events `alert.created`, `alert.updated`,
`investigation.updated`, `item.added`, `item.removed`, `assertion.created`, `presence`,
`rule.started`, `rule.finished`. With Redis configured, messages fan out across API workers.
