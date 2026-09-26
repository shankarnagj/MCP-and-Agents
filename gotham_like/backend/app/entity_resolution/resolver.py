"""Deterministic, explainable entity resolution.

No machine-learned or LLM components: every decision is a pure function of the
two records, the ontology, and the (versioned) weights below, and exposes the
evidence that produced it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.entity_resolution import normalize as N
from app.entity_resolution.similarity import levenshtein_similarity, name_similarity, token_overlap
from app.models.common import ResolutionDecision
from app.ontology import Ontology

RESOLVER_VERSION = "er-1.2.1"

# Identifier kinds a single entity can legitimately have many of: a mismatch is not evidence against.
MULTI_VALUED = {"email", "phone", "ip", "domain", "device_fp"}
IDENTIFIER_WEIGHTS = {
    "email": 0.35, "phone": 0.25, "national_id": 0.45, "org_reg": 0.45, "account": 0.5,
    "device": 0.5, "imo": 0.5, "plate": 0.4, "sha256": 0.6,
}
SIMILARITY_WEIGHTS = {"name": 0.30, "org_name": 0.40, "address": 0.15, "dob": 0.20}

MATCH_THRESHOLD = 0.85
POSSIBLE_THRESHOLD = 0.65


@dataclass
class Evidence:
    signal: str
    method: str
    score: float
    weight: float
    detail: str
    counted: bool = True


@dataclass
class MatchResult:
    decision: ResolutionDecision
    score: float
    evidence: list[Evidence] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    resolver_version: str = RESOLVER_VERSION

    def reasons(self) -> list[str]:
        return [e.detail for e in self.evidence]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "score": round(self.score, 4),
            "evidence": [asdict(e) for e in self.evidence],
            "conflicts": self.conflicts,
            "resolver_version": self.resolver_version,
        }

    def explain(self) -> str:
        lines = [f"{self.decision.value} SCORE: {self.score:.2f}", "", "Evidence:"]
        lines += [f"  {e.detail}" for e in self.evidence]
        if self.conflicts:
            lines += ["", "Conflicts:"] + [f"  {c}" for c in self.conflicts]
        return "\n".join(lines)


def compare(ontology: Ontology, entity_type: str, a: dict[str, Any], b: dict[str, Any]) -> MatchResult:
    tdef = ontology.entity_type(entity_type)
    evidence: list[Evidence] = []
    conflicts: list[str] = []
    strong_exact = 0
    name_score: float | None = None

    for prop, pdef in tdef.properties.items():
        va, vb = a.get(prop), b.get(prop)
        if va in (None, "") or vb in (None, ""):
            continue
        if pdef.identifier:
            kind = pdef.identifier
            na, nb = N.normalize_identifier(kind, va), N.normalize_identifier(kind, vb)
            if not na or not nb:
                continue
            weight = IDENTIFIER_WEIGHTS.get(kind, 0.3)
            if na == nb:
                strong_exact += 1
                evidence.append(Evidence(prop, "exact", 1.0, weight, f"{prop} exact match"))
            elif kind in MULTI_VALUED:
                evidence.append(
                    Evidence(prop, "exact", 0.0, weight, f"{prop} differs (multi-valued identifier; not counted)", counted=False)
                )
            else:
                conflicts.append(f"{prop} conflict")
                evidence.append(Evidence(prop, "exact", 0.0, weight, f"{prop} conflict: distinct identifiers"))
            continue
        kind = pdef.resolution
        if kind in ("name", "org_name"):
            norm = N.person_name if kind == "name" else N.org_name
            na, nb = norm(va), norm(vb)
            if not na or not nb:
                continue
            s = name_similarity(na, nb)
            name_score = s
            evidence.append(Evidence(prop, "jaro_winkler(token_sorted)", s, SIMILARITY_WEIGHTS[kind], f"name similarity: {s:.2f}"))
        elif kind == "address":
            na, nb = N.address(va), N.address(vb)
            if not na or not nb:
                continue
            s = max(token_overlap(na, nb), levenshtein_similarity(na, nb))
            evidence.append(
                Evidence(prop, "max(token_overlap, levenshtein)", s, SIMILARITY_WEIGHTS["address"], f"address similarity: {s:.2f}")
            )
        elif kind == "dob":
            na, nb = N.date(va), N.date(vb)
            if not na or not nb:
                continue
            if na == nb:
                evidence.append(Evidence(prop, "exact", 1.0, SIMILARITY_WEIGHTS["dob"], f"{prop} exact match"))
            else:
                conflicts.append(f"{prop} conflict")
                # never embed raw values in evidence text: it is shown to roles that may not see the field
                evidence.append(Evidence(prop, "exact", 0.0, SIMILARITY_WEIGHTS["dob"], f"{prop} conflict: values differ"))

    counted = [e for e in evidence if e.counted]
    total_w = sum(e.weight for e in counted)
    score = sum(e.weight * e.score for e in counted) / total_w if total_w else 0.0
    only_names = all(e.method.startswith("jaro") for e in counted)

    if not counted:
        decision = ResolutionDecision.NO_MATCH
    elif conflicts:
        # Hard conflicts on single-valued identifiers block automatic merges. A near-identical
        # name is still surfaced for human review (e.g. relatives, data-entry errors in DOB).
        strong_name = (name_score or 0) >= 0.95
        decision = ResolutionDecision.POSSIBLE_MATCH if (score >= POSSIBLE_THRESHOLD or strong_name) else ResolutionDecision.NO_MATCH
    elif only_names:
        # A name alone is never sufficient for an automatic merge.
        decision = ResolutionDecision.POSSIBLE_MATCH if (name_score or 0) >= 0.92 else ResolutionDecision.NO_MATCH
    elif score >= MATCH_THRESHOLD and (strong_exact >= 2 or (strong_exact >= 1 and (name_score is None or name_score >= 0.85))):
        decision = ResolutionDecision.MATCH
    elif score >= POSSIBLE_THRESHOLD:
        decision = ResolutionDecision.POSSIBLE_MATCH
    else:
        decision = ResolutionDecision.NO_MATCH
    return MatchResult(decision, score, evidence, conflicts)


def blocking_keys(ontology: Ontology, entity_type: str, props: dict[str, Any]) -> set[str]:
    """Cheap keys used to generate candidate pairs (avoids O(n²) comparison)."""
    keys: set[str] = set()
    tdef = ontology.entity_type(entity_type)
    for prop, pdef in tdef.properties.items():
        v = props.get(prop)
        if v in (None, ""):
            continue
        if pdef.identifier:
            n = N.normalize_identifier(pdef.identifier, v)
            if n:
                keys.add(f"id:{pdef.identifier}:{n}")
        elif pdef.resolution in ("name", "org_name"):
            norm = N.person_name if pdef.resolution == "name" else N.org_name
            tokens = sorted(norm(v).split())
            if tokens:
                # sorted-token prefix key tolerates word order changes & typos after 3 chars
                keys.add("nm:" + "|".join(t[:3] for t in tokens))
                # per-token keys catch a typo in one token; oversized blocks are skipped by the caller
                keys.update(f"tk:{t[:4]}" for t in tokens if len(t) >= 3)
    return keys
