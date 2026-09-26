"""Cryptographic verification via the official ``c2pa-python`` SDK, if installed.

Remote manifest fetching and OCSP fetching are disabled so that inspection
never touches the network; a remote-only manifest is reported as unverifiable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_OFFLINE_SETTINGS = {"verify": {"remote_manifest_fetch": False, "ocsp_fetch": False}}


def sdk_available() -> bool:
    try:
        import c2pa  # noqa: F401
    except Exception:
        return False
    return True


def _reader(c2pa, path: Path):
    try:
        settings = c2pa.Settings.from_dict(_OFFLINE_SETTINGS)
        ctx = c2pa.Context(settings)
        return c2pa.Reader(str(path), context=ctx)
    except TypeError:
        return c2pa.Reader(str(path))


def verify(path: str | Path) -> dict[str, Any]:
    """Return {"sdk": ..., "manifest_store": ..., "validation_state": ..., "error": ...}."""
    if not sdk_available():
        return {"sdk": None, "error": "c2pa-python not installed; cryptographic verification unavailable"}
    import c2pa

    out: dict[str, Any] = {"sdk": f"c2pa-python (c2pa-rs {c2pa.sdk_version()})"}
    try:
        reader = _reader(c2pa, Path(path))
    except Exception as exc:  # the SDK raises typed C2paError subclasses
        out["error_type"] = type(exc).__name__.lstrip("_")
        out["error"] = str(exc)
        return out
    try:
        out["manifest_store"] = json.loads(reader.json())
        try:
            out["validation_state"] = reader.get_validation_state()
        except Exception:
            out["validation_state"] = out["manifest_store"].get("validation_state")
        try:
            out["is_embedded"] = reader.is_embedded()
        except Exception:
            pass
    finally:
        try:
            reader.close()
        except Exception:
            pass
    return out
