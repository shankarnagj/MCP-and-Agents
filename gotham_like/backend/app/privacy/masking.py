"""Field-level access control and masking driven by ontology sensitivity levels."""

from __future__ import annotations

from typing import Any

from app.auth.rbac import P_PII, P_RESTRICTED, has_permission
from app.ontology import Ontology

RESTRICTED_PLACEHOLDER = "[RESTRICTED]"


def mask_value(value: Any) -> str:
    s = str(value)
    if "@" in s:
        local, _, domain = s.partition("@")
        return f"{local[:1]}***@{domain}"
    if len(s) <= 4:
        return "****"
    if any(c.isdigit() for c in s) and sum(c.isdigit() for c in s) >= len(s) // 2:
        return "•" * (len(s) - 4) + s[-4:]
    parts = s.split()
    return " ".join(p[:1] + "*" * max(len(p) - 1, 2) for p in parts)


def can_view(role: str, sensitivity: str) -> bool:
    if sensitivity == "restricted":
        return has_permission(role, P_RESTRICTED)
    if sensitivity == "pii":
        return has_permission(role, P_PII)
    return True


def mask_properties(ontology: Ontology, entity_type: str, props: dict[str, Any], role: str) -> tuple[dict[str, Any], list[str]]:
    """Return (visible properties, list of masked property names)."""
    out: dict[str, Any] = {}
    masked: list[str] = []
    for key, value in props.items():
        if key == "_alternates":
            alt, alt_masked = mask_properties(ontology, entity_type, {k: v for k, v in value.items()}, role)
            out[key] = alt
            masked += [f"_alternates.{m}" for m in alt_masked]
            continue
        if key == "_extra":
            # unmapped fields carry unknown sensitivity: treat as PII
            if can_view(role, "pii"):
                out[key] = value
            else:
                masked.append(key)
            continue
        sens = ontology.sensitivity(entity_type, key)
        if can_view(role, sens):
            out[key] = value
        elif sens == "restricted":
            out[key] = RESTRICTED_PLACEHOLDER
            masked.append(key)
        else:
            out[key] = [mask_value(v) for v in value] if isinstance(value, list) else mask_value(value)
            masked.append(key)
    return out, masked


def mask_label(ontology: Ontology, entity_type: str, label: str, role: str) -> str:
    et = ontology.entity_types.get(entity_type)
    if not et:
        return label
    sens = ontology.sensitivity(entity_type, et.label)
    if can_view(role, sens):
        return label
    return RESTRICTED_PLACEHOLDER if sens == "restricted" else mask_value(label)
