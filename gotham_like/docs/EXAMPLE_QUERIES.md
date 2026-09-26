# Example queries

All examples run against the seeded SYNTHETIC / DEMONSTRATION DATA. `$T` is a bearer token:

```bash
T=$(curl -s localhost:8000/api/auth/login -H 'content-type: application/json' \
      -d '{"username":"analyst","password":"Demo-Passw0rd!"}' | jq -r .access_token)
api() { curl -s -H "Authorization: Bearer $T" -H 'content-type: application/json' "$@"; }
```

## Search

| Query | Finds |
|---|---|
| `"Harbor Plaza"` | exact phrase |
| `Zusil Lobetul` / `~Zusl Lobetul` | fuzzy / typo-tolerant |
| `Zusil*` | prefix |
| `account:ACC-9000001` | account by source key (identifier index) |
| `device:DV-7F3A-SHARED` | device |
| `ip:203.0.113.66` | IP address |
| `company:Northwind` | organisations named like "Northwind" |
| `type:Transaction near:51.45,3.60,2km on:2026-02-14` | geo + date + type |
| `jurisdiction:"Castellan Isles" type:Organization` | property filter |
| `type:Person -type:Transaction after:2026-01-01` | include/exclude types, date |

```bash
api localhost:8000/api/search -d '{"query":"type:Transaction near:51.45,3.60,2km on:2026-02-14","limit":50}' | jq '.total_estimate, .match_reasons'
```

## Fraud: accounts sharing devices within 30 days

```bash
api localhost:8000/api/query -d '{"pattern":{
  "nodes":[{"var":"p","type":"Person"},{"var":"a","type":"Account"},{"var":"d","type":"Device"}],
  "edges":[{"from":"p","to":"a","type":"OWNS"},{"from":"a","to":"d","type":"USED","time_from":"2026-03-01","time_to":"2026-03-31"}],
  "aggregate":{"group_by":"d","count_distinct":"p","op":">","value":3}}, "explain": true}' | jq '.rows, .plan'
```

Rule-based equivalent (sliding 30-day window, deterministic, explainable):
`POST /api/rules/shared_device/evaluate`, then `GET /api/signals?rule_id=shared_device`.

## Cybersecurity: everything connected to a suspicious IP in a time window

```bash
IP=$(api localhost:8000/api/search -d '{"query":"ip:203.0.113.66"}' | jq -r '.results[0].id')
api localhost:8000/api/graph/subgraph -d "{\"seeds\":[\"$IP\"],\"depth\":2,\"filters\":{\"time_from\":\"2026-03-01T00:00:00Z\",\"time_to\":\"2026-03-31T23:59:59Z\"}}" | jq '[.nodes[].type] | group_by(.) | map({(.[0]): length}) | add'
api "localhost:8000/api/timeline?entity_id=$IP&time_from=2026-03-01T00:00:00Z&time_to=2026-03-31T23:59:59Z" | jq '.by_type'
```

## AML: explainable ownership path between a person and a company

```bash
P=$(api localhost:8000/api/search -d '{"query":"id:P-00007"}' | jq -r '.results[0].id')
C=$(api localhost:8000/api/search -d '{"query":"company:Northwind Quartz"}' | jq -r '.results[0].id')
api localhost:8000/api/graph/path -d "{\"source\":\"$P\",\"target\":\"$C\",\"relationship_types\":[\"CONTROLS\"],\"respect_direction\":true}" \
  | jq '.paths[0].steps[] | {relationship_type, from, to, timestamp, source_records, transformation: .provenance.transformation}'
```

Weighted (prefers high-confidence edges) and all-simple-paths variants: `"mode":"weighted"`, `"mode":"all_simple","max_paths":10`.

## Supply chain: trace a product

```bash
S=$(api localhost:8000/api/search -d '{"query":"shipment:SHP-000042"}' | jq -r '.results[0].id')
api "localhost:8000/api/entities/$S/relationships" | jq '.items[] | {relationship_type, timestamp, other: .other.label}'
api "localhost:8000/api/timeline?entity_id=$S" | jq '.events[] | {timestamp, event_type, lat, lon}'
```

## Time × space × entity × relationship

All transactions within 2 km of Harbor Plaza in February 14 18:00–20:30:

```bash
api localhost:8000/api/geo/query -d '{"lat":51.45,"lon":3.60,"radius_m":2000,
  "time_from":"2026-02-14T18:00:00Z","time_to":"2026-02-14T20:30:00Z","entity_types":["Transaction"],"event_types":["transaction"]}' | jq '.counts'
```

…restricted to transactions paid **to** a specific account:

```bash
M=$(api localhost:8000/api/search -d '{"query":"account:ACC-9000001"}' | jq -r '.results[0].id')
api localhost:8000/api/geo/query -d "{\"lat\":51.45,\"lon\":3.60,\"radius_m\":3000,\"time_from\":\"2026-03-01T00:00:00Z\",\"time_to\":\"2026-03-31T00:00:00Z\",
  \"entity_types\":[\"Transaction\"],\"related_to\":[\"$M\"],\"relationship_types\":[\"TRANSFERRED_TO\"],\"include\":[\"entities\"]}" | jq '.counts'
```

Polygon / geofence, KNN, heatmap:

```bash
api localhost:8000/api/geo/geofences | jq '.features[].properties.name'
api "localhost:8000/api/geo/nearest?lat=51.45&lon=3.6&k=5&entity_type=Location" | jq '.items[] | {label, distance_m}'
api "localhost:8000/api/geo/heatmap?cell_deg=0.05&event_type=transaction" | jq '.features | length'
```

## Graph analytics (ANALYTICAL SIGNALS)

```bash
D=$(api localhost:8000/api/search -d '{"query":"device:DV-7F3A-SHARED"}' | jq -r '.results[0].id')
api localhost:8000/api/graph/analytics -d "{\"seeds\":[\"$D\"],\"depth\":2,\"algorithms\":[\"pagerank\",\"betweenness_centrality\",\"communities\",\"k_core\",\"cycles\"]}" \
  | jq '{label, caveat, window, top_pagerank: .results.pagerank.top[:5]}'
```

## Provenance

```bash
R=$(api "localhost:8000/api/entities/$D/relationships?relationship_type=USED&limit=1" | jq -r '.items[0].id')
api "localhost:8000/api/provenance/$R" | jq '{why, source: .source_records[0].source, record: .source_records[0].source_record_id,
  ingested: .source_records[0].ingestion_timestamp, transformation: .source_records[0].transformation_version, lineage: .lineage_upstream.edges}'
```
