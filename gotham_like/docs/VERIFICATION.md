# Verification

Latest run of `scripts/verify_all.py`: 2026-09-26 10:42 UTC.

```
============================
PLATFORM VERIFICATION
============================

Backend:                  PASS
Frontend:                 PASS
Database:                 PASS
Ontology:                 PASS
Entity Resolution:        PASS
Graph:                    PASS
Search:                   PASS
Timeline:                 PASS
Geospatial:               PASS
Provenance:               PASS
Investigation Workspace:  PASS
RBAC:                     PASS
Audit Logging:            PASS
Security:                 PASS
Performance:              PASS
```

| Area | Evidence |
|---|---|
| Backend | 299/299 tests passed |
| Frontend | tsc ok; vitest Tests  24 passed (24); e2e PASS |
| Database | 14/14 tests |
| Ontology | 8/8 tests |
| Entity Resolution | 44/44 tests |
| Graph | 29/29 tests |
| Search | 45/45 tests |
| Timeline | 3/3 tests |
| Geospatial | 7/7 tests |
| Provenance | 6/6 tests |
| Investigation Workspace | 18/18 tests |
| RBAC | 64/64 tests |
| Audit Logging | 15/15 tests |
| Security | 143/143 tests |
| Performance | 4/4 tests; quick bench p95: 2-hop 63.19 ms, path 28.72 ms, geo 9.87 ms |
| Synthetic Data | counts={'locations': 500, 'persons': 1000, 'kyc_records': 70, 'organizations': 200, 'accounts': 2000, 'devices': 1000, 'transactions': 10000, 'events': 5000, 'shipments': 150} deterministic=True |

Steps executed: synthetic data generation (counts + byte-for-byte determinism) · backend pytest (unit, integration incl. migration upgrade/downgrade/parity, security, performance incl. a generated 50k-entity / 250k-edge graph) · frontend `tsc`, Vitest, production build · Chromium E2E against the live API · quick graph + geospatial benchmark. Full-scale numbers: [BENCHMARKS.md](BENCHMARKS.md).

Known limitations, technical debt, performance bottlenecks, security risks and recommended next steps: [LIMITATIONS.md](LIMITATIONS.md).
