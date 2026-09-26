# Security & privacy

Tessera handles data that may be sensitive. This document describes the controls that are
implemented, how they are tested, and the residual risks an operator must manage.

## 1. Threat model (summary)

| Threat | Control | Test |
|---|---|---|
| Credential stuffing / brute force | per-IP+username login rate limit; 5-failure lockout (15 min); constant-time unknown-user path; identical error for unknown user / bad password | `security/test_auth_sessions.py`, `test_login_rate_limit` |
| Token theft / replay | short-lived JWT (60 min) bound to a **server-side session** (`sid`) that is revocable, expires, and has an idle timeout (120 min); logout revokes | `test_logout_revokes_session`, `test_idle_session_expires` |
| Privilege escalation via token claims | role is **re-read from the database** on every request; the token's `role` claim is ignored | `test_token_for_valid_session_but_escalated_role_claim_is_ignored` |
| Forged / `alg=none` tokens | HS256 only, `iss`, `exp`, `sub`, `sid` required | `unit/test_security_primitives.py` |
| Broken access control | explicit permission per endpoint (`require(P_…)`), investigation-level write checks (owner, collaborators, INVESTIGATOR/ADMIN) | `security/test_rbac_matrix.py` (15 endpoints × 4 roles) |
| SQL injection | SQLAlchemy expressions with bound parameters only; dynamic identifiers (rules, connector tables) come from whitelists / `^[A-Za-z_][A-Za-z0-9_]{0,62}$`; query-builder types/properties validated against the ontology | `security/test_injection_validation.py` (10 payloads × search, path/query params, query builder, graph, geo) |
| Malformed / hostile input | Pydantic validation with bounds (depth ≤ 5, radius ≤ 500 km, limits), GeoJSON structural validation before PostGIS, NUL-byte rejection, 12 MB body limit, upload media-type allow-list + 10 MB cap, content-addressed upload storage (client filename never touches the filesystem) | `test_input_validation`, `test_oversized_body_rejected`, geo tests |
| Information leakage in errors | global handler returns `{"detail":"internal error"}`; no SQL or stack traces to clients | `test_errors_do_not_leak_internals` |
| Clickjacking / MIME sniffing / XSS | CSP, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, `no-store`; React escapes by default; map popups escape HTML | `test_security_headers` |
| Secrets exposure | source DSNs / API tokens stored Fernet-encrypted, never returned (`has_secret` only), secret-looking keys refused in plain config; dev secrets refused when `TESSERA_ENV=production` | `test_secret_like_config_rejected_and_secrets_encrypted`, `test_production_rejects_dev_secrets` |
| Abuse / DoS | per-IP rate limit (Redis fixed window, in-process fallback), graph node budgets and fan-out caps, query result limits, statement timing metrics | `test_rate_limiting`, performance tests |
| Repudiation / tampering | append-only audit log (DB trigger blocks UPDATE/DELETE/TRUNCATE) + SHA-256 hash chain verifiable via `GET /api/audit/verify` | `security/test_audit_privacy.py` |
| Over-collection / misuse of personal data | field-level masking, filter-on-protected-field refusal, PII access logging, retention, four-eyes erasure | `security/test_audit_privacy.py` |

## 2. Authentication & sessions

* Passwords: bcrypt (cost 12) over a SHA-256 pre-hash (keeps full entropy beyond bcrypt's
  72-byte limit). Policy: ≥ 12 characters, ≥ 3 character classes.
* `POST /api/auth/login` → `access_token` (JWT: `sub`, `sid`, `iat`, `exp`, `jti`, `iss`).
* Each request validates the JWT **and** the `user_sessions` row (not revoked, not expired,
  idle < `TESSERA_SESSION_IDLE_MINUTES`), and that the user is still active.
* Disabling a user revokes all of their sessions.
* The WebSocket authenticates with the token in the **first frame**, never in the URL (URLs
  end up in proxy logs).
* The SPA stores the token in `sessionStorage` (cleared with the tab). For deployments that
  prefer cookies, put the API behind the same origin and switch to `HttpOnly; SameSite=Strict`
  cookies — the server-side session model already supports it.

## 3. Authorization (RBAC)

| Permission | VIEWER | ANALYST | INVESTIGATOR | ADMIN |
|---|:-:|:-:|:-:|:-:|
| read entities / search / graph / timeline / map / provenance | ✓ | ✓ | ✓ | ✓ |
| view `pii` fields (unmasked) | | ✓ | ✓ | ✓ |
| view `restricted` fields | | | ✓ | ✓ |
| create/edit investigations, notes, citations, saved queries | | ✓ | ✓ | ✓ |
| create analyst assertions (hypotheses) | | ✓ | ✓ | ✓ |
| export data / reports | | ✓ | ✓ | ✓ |
| manage alerts, run rules | | ✓ | ✓ | ✓ |
| verify / dispute relationships, review ER candidates (merge / unmerge) | | | ✓ | ✓ |
| request data deletion | | | ✓ | ✓ |
| audit log, users, ontology, rules definitions, sources/ingestion, approve deletion | | | | ✓ |

Every denial is itself audited (`access_denied`).

## 4. Audit logging

Recorded actions: `login`, `login_failed`, `logout`, `search`, `query`, `entity_view`,
`pii_access`, `graph_operation`, `timeline_query`, `geo_query`, `provenance_view`,
`data_export`, `investigation_create`, `investigation_update`, `analyst_assertion`,
`relationship_verify`, `er_review`, `rule_change`, `alert_update`, `ingestion`, `user_admin`,
`ontology_change`, `deletion_request`, `deletion_approve`, `access_denied`.

Each row: `user`, `action`, `ts`, `object_type/object_id`, `previous_value`, `new_value`,
`details`, `request_id`, `ip`, `prev_hash`, `hash`.

* **Append-only**: migration `0002` installs triggers raising on UPDATE/DELETE/TRUNCATE.
* **Tamper-evident**: `hash = SHA256(prev_hash ‖ canonical_json(row))`, serialised with an
  advisory lock. `GET /api/audit/verify` recomputes the chain; the test suite simulates an
  out-of-band edit (with triggers bypassed) and asserts detection.
* **Retention**: audit rows are kept for `TESSERA_RETENTION_DAYS_AUDIT` (default ~7 years).
  Purging requires a DBA role that explicitly disables the trigger in a controlled change —
  deliberately not possible from the application.

## 5. Privacy controls

* **Data minimisation**: mappings choose which source fields become properties; unmapped
  fields are kept only under `_extra` and treated as PII.
* **Field-level access control & masking**: ontology `sensitivity` (`public|pii|restricted`)
  drives masking in every serialiser (entity cards, search results, graph nodes, exports,
  reports). Masked field names are returned (`masked_fields`) so users know data is withheld.
  Raw source payloads are shown only to `pii:view` roles.
* **Inference protection**: search / query-builder filters on fields the caller may not see
  are refused or ignored with a warning (prevents learning values by probing filters).
* **Access logging**: viewing an entity with non-public fields by a cleared user writes
  `pii_access` with the field names.
* **Retention**: per-source `retention_days`; `GET /api/privacy/retention` reports expired raw
  records; `scripts/apply_retention.py` redacts them.
* **Deletion (erasure) workflow**: `POST /api/privacy/deletion-requests` (INVESTIGATOR/ADMIN)
  → approval by a *different* ADMIN (four-eyes) → properties, label, identifiers, coordinates
  and search text erased; source records where the entity was the primary subject redacted;
  graph structure kept as a tombstone (it may concern other parties); audit retained.
* **Synthetic data**: every demo record is labelled `SYNTHETIC / DEMONSTRATION DATA`; names
  are built from invented syllables; e-mails use reserved example domains; IPs come from
  RFC 5737 documentation ranges or private ranges.

## 6. Analytical-integrity safeguards

* No UI or API text states that a person or organisation *is* fraudulent / guilty / malicious;
  a frontend unit test scans the UI source for such phrases, and backend tests scan reports and
  alert summaries.
* Rule definitions containing conclusion words are rejected.
* Scores are documented as rule-specific magnitudes, not probabilities.
* Path results state that connectivity is not intent; truncated searches say that absence of a
  path is not evidence of no connection.

## 7. Operating in production — checklist

1. Set `TESSERA_ENV=production`, unique `TESSERA_SECRET_KEY` (≥ 32 chars) and
   `TESSERA_ENCRYPTION_KEY` (`scripts/gen_secrets.py`). Startup refuses the dev defaults.
2. Terminate TLS in front of the API/SPA (nginx config in `docker/`), enable HSTS there.
3. Do **not** seed demo users (`scripts/seed_demo.py`) in production; create users via
   `POST /api/users` with strong passwords; consider SSO/MFA at the reverse proxy.
4. Run PostgreSQL with a least-privilege application role (no superuser; the audit trigger is
   owned by a separate role), encrypted storage and backups.
5. Restrict `TESSERA_CORS_ORIGINS` to the SPA origin.
6. Ship `/metrics` and logs to your monitoring stack; alert on `tessera_errors_total`,
   `login_failed` spikes and `access_denied` spikes.
7. Schedule `scripts/apply_retention.py` and periodic `GET /api/audit/verify`.

## 8. Known residual risks

* The in-process rate-limit fallback is per worker; use Redis in multi-worker deployments.
* JWT revocation is immediate only because every request checks the session row (one indexed
  lookup per request); caching that lookup would reintroduce a revocation window.
* Fuzzy search over `search_text` can reveal that a *masked* entity matches a name typed by a
  VIEWER (existence disclosure). Deployments that need to prevent this should exclude PII
  properties from `search_text` for low-privilege roles (ontology `searchable: false`).
* Signal explanations reference entity **ids** rather than labels so that stored text never
  contains PII; the UI resolves labels with masking.
* Uploaded documents are stored content-addressed but not malware-scanned.
* The platform relies on PostgreSQL for data-at-rest encryption and on the operator for TLS.
