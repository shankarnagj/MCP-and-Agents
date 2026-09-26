# Setup

## Option A — Docker Compose (recommended)

```bash
cd gotham_like/docker
python ../scripts/gen_secrets.py > .env          # needs `pip install cryptography`, or fill .env.example by hand
echo "TESSERA_DEMO_PASSWORD=Choose-A-Demo-Passw0rd!" >> .env
docker compose up -d --build db redis backend frontend
docker compose --profile seed run --rm seed      # migrations + demo users + synthetic data + rules (≈1 min)
open http://localhost:8080                       # users: admin / investigator / analyst / viewer
```

## Option B — Local development

Requirements: Python 3.12, Node 20+, PostgreSQL 16 with PostGIS 3.4 and `pg_trgm`, Redis 7 (optional).

```bash
# database
sudo apt-get install postgresql-16 postgresql-16-postgis-3 redis-server
sudo -u postgres psql -c "CREATE USER tessera WITH PASSWORD 'tessera' CREATEDB;"
sudo -u postgres createdb -O tessera tessera
sudo -u postgres psql -d tessera -c "CREATE EXTENSION postgis; CREATE EXTENSION pg_trgm;"

# backend
cd gotham_like
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
python scripts/seed_demo.py                      # migrate + seed (prints the demo password)
cd backend && uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd gotham_like/frontend && npm ci && npm run dev  # http://localhost:5173 (proxies /api and /ws to :8000)
```

Default demo password: `Demo-Passw0rd!` (override with `TESSERA_DEMO_PASSWORD` before seeding).
Demo users exist only for local demonstration; never seed them in production.

## Configuration (environment variables, prefix `TESSERA_`)

| Variable | Default | Meaning |
|---|---|---|
| `ENV` | development | `production` refuses development secrets |
| `DATABASE_URL` | `postgresql+psycopg://tessera:tessera@localhost:5432/tessera` | PostgreSQL + PostGIS |
| `REDIS_URL` | `redis://localhost:6379/0` | cache, rate limits, WebSocket fan-out (optional; empty disables) |
| `SECRET_KEY` | dev value | JWT signing key (≥ 32 chars in production) |
| `ENCRYPTION_KEY` | dev value | Fernet key for data-source secrets |
| `ACCESS_TOKEN_MINUTES` / `SESSION_IDLE_MINUTES` | 60 / 120 | token lifetime / idle timeout |
| `RATE_LIMIT_PER_MINUTE` / `LOGIN_RATE_LIMIT_PER_MINUTE` | 600 / 20 | per IP / per IP+username |
| `GRAPH_MAX_NODES` / `GRAPH_MAX_DEPTH` / `GRAPH_MAX_FANOUT` | 2000 / 5 / 200 | graph windowing guard rails |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | SPA origins |
| `RETENTION_DAYS_RAW_RECORDS` / `RETENTION_DAYS_AUDIT` | 1825 / 2555 | retention defaults |
| `LOG_LEVEL` / `LOG_JSON` | INFO / true | structured logging |

Frontend: `VITE_MAP_STYLE_URL` (optional self-hosted MapLibre style; default is an offline graticule basemap).

## Loading your own data

1. Extend the ontology if needed (`data/schemas/ontology.json`, then `python scripts/gen_ontology_doc.py`).
2. Add a mapping to `data/schemas/mappings.json` (entities, relationships, events; `{field}` templates; `stub` references).
3. Register the source (`POST /api/sources`, secrets go in `secret` and are encrypted) or add it to `data/schemas/sources.json`.
4. Run ingestion (see `app/services/demo_loader.py` for the programmatic pattern: `run_ingestion(db, ontology, source, connector, mapping)`),
   then `resolve_type(db, ontology, "Person")` for entity resolution and `POST /api/rules/{id}/evaluate` for signals.

Connectors: `CSVConnector`, `JSONConnector`, `JSONLConnector`, `ParquetConnector`, `PostgresConnector` (read-only, validated identifiers,
server-side cursor), `RESTConnector` (cursor pagination, headers kept out of provenance).

## Running the checks

```bash
cd gotham_like
python scripts/verify_all.py                    # everything, prints PLATFORM VERIFICATION
cd backend && pytest -q                          # backend only (needs a tessera_test database; see tests/conftest.py)
cd frontend && npm test && npx tsc -b            # frontend unit tests + typecheck
node frontend/tests/e2e/smoke.mjs                # browser E2E (backend :8000 + `vite preview` :4173)
python scripts/benchmark.py --quick              # 50k/250k smoke benchmark
python scripts/benchmark.py                      # 1M entities / 10M relationships / 2M events
python scripts/demo_investigation.py             # reproducible demo investigation → docs/examples/
```

Test database: `createdb -O tessera tessera_test` (+ `postgis`, `pg_trgm`). Tests use Redis DB 15 and never touch the main database.
