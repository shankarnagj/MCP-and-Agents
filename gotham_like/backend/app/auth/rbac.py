"""Role-based access control. Permissions are explicit strings; roles map to permission sets."""

from __future__ import annotations

from app.models import Role

P_READ = "entity:read"
P_PII = "pii:view"
P_RESTRICTED = "restricted:view"
P_GRAPH = "graph:analyze"
P_SEARCH = "search"
P_INV_READ = "investigation:read"
P_INV_WRITE = "investigation:write"
P_ASSERT = "assertion:write"
P_VERIFY = "relationship:verify"
P_ER_REVIEW = "er:review"
P_EXPORT = "data:export"
P_AUDIT = "audit:read"
P_USERS = "users:manage"
P_ONTOLOGY = "ontology:write"
P_RULES_WRITE = "rules:write"
P_RULES_RUN = "rules:run"
P_ALERTS = "alerts:manage"
P_INGEST = "ingest"
P_DELETE_REQUEST = "privacy:request_deletion"
P_DELETE_APPROVE = "privacy:approve_deletion"
P_PROVENANCE = "provenance:read"

_VIEWER = {P_READ, P_SEARCH, P_GRAPH, P_INV_READ, P_PROVENANCE}
_ANALYST = _VIEWER | {P_PII, P_INV_WRITE, P_ASSERT, P_EXPORT, P_ALERTS, P_RULES_RUN}
_INVESTIGATOR = _ANALYST | {P_RESTRICTED, P_VERIFY, P_ER_REVIEW, P_DELETE_REQUEST}
_ADMIN = _INVESTIGATOR | {P_AUDIT, P_USERS, P_ONTOLOGY, P_RULES_WRITE, P_INGEST, P_DELETE_APPROVE}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.VIEWER.value: frozenset(_VIEWER),
    Role.ANALYST.value: frozenset(_ANALYST),
    Role.INVESTIGATOR.value: frozenset(_INVESTIGATOR),
    Role.ADMIN.value: frozenset(_ADMIN),
}


def permissions_for(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for(role)
