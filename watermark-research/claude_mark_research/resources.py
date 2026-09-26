"""Loading of the static lexical resources (substitution and phrase tables)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


def _read(path: str | Path | None, default_name: str) -> tuple[str, str]:
    if path:
        p = Path(path)
        return p.read_text(encoding="utf-8"), str(p)
    ref = resources.files("claude_mark_research") / "data" / default_name
    return ref.read_text(encoding="utf-8"), f"builtin:{default_name}"


@dataclass
class Dictionary:
    entries: dict[str, list[str]]
    version: str
    source: str
    sha256: str
    tiers: list[str]

    def info(self) -> dict:
        return {"version": self.version, "source": self.source, "sha256": self.sha256,
                "tiers": self.tiers, "entries": len(self.entries)}


def load_substitutions(path: str | Path | None = None, tiers: list[str] | None = None) -> Dictionary:
    """Load a substitution table.

    Accepts either the structured format (``{"_meta":..., "substitutions": {...},
    "extended": {...}}``) or a plain ``{"word": ["alt", ...]}`` mapping.
    """
    raw, source = _read(path, "substitutions.json")
    data = json.loads(raw)
    tiers = tiers or ["conservative"]
    meta = data.get("_meta", {}) if isinstance(data.get("_meta"), dict) else {}
    if "substitutions" in data:
        tables = {"conservative": data["substitutions"], "extended": data.get("extended", {})}
    else:
        tables = {"conservative": {k: v for k, v in data.items() if not k.startswith("_")}}
    entries: dict[str, list[str]] = {}
    for tier in tiers:
        for word, alts in tables.get(tier, {}).items():
            if isinstance(alts, str):
                alts = [alts]
            entries.setdefault(word.lower(), [])
            entries[word.lower()] += [a for a in alts if a.lower() != word.lower()]
    return Dictionary(entries, meta.get("version", "unversioned"), source,
                      hashlib.sha256(raw.encode()).hexdigest(), list(tiers))


def load_phrases(path: str | Path | None = None) -> Dictionary:
    raw, source = _read(path, "phrases.json")
    data = json.loads(raw)
    meta = data.get("_meta", {}) if isinstance(data.get("_meta"), dict) else {}
    table = data.get("phrases", {k: v for k, v in data.items() if not k.startswith("_")})
    entries = {k.lower(): ([v] if isinstance(v, str) else list(v)) for k, v in table.items()}
    return Dictionary(entries, meta.get("version", "unversioned"), source,
                      hashlib.sha256(raw.encode()).hexdigest(), ["phrases"])


def stable_hash(*parts: object) -> int:
    """Deterministic hash (unlike Python's salted hash())."""
    h = hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")
