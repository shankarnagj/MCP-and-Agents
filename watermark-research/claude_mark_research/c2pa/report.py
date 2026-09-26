"""C2PA status classification and reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .inspect import scan_container
from .verify import verify

C2PA_PRESENT = "C2PA_PRESENT"
C2PA_ABSENT = "C2PA_ABSENT"
C2PA_INVALID = "C2PA_INVALID"
C2PA_UNVERIFIABLE = "C2PA_UNVERIFIABLE"

DISCLAIMER = ("C2PA is file-level provenance metadata. It is unrelated to Claude's statistical text "
              "watermark. This tool only reads credentials; it never creates, alters or removes them.")


def _summarise_manifest(store: dict[str, Any]) -> dict[str, Any]:
    active_id = store.get("active_manifest")
    manifests = store.get("manifests", {}) or {}
    m = manifests.get(active_id, {}) if active_id else {}
    sig = m.get("signature_info", {}) or {}
    gen = m.get("claim_generator") or ", ".join(
        f"{g.get('name', '')} {g.get('version', '')}".strip() for g in m.get("claim_generator_info", []) or [])
    return {
        "active_manifest": active_id,
        "manifest_count": len(manifests),
        "title": m.get("title"),
        "issuer": sig.get("issuer") or sig.get("common_name"),
        "signature_algorithm": sig.get("alg"),
        "signing_time": sig.get("time"),
        "cert_serial": sig.get("cert_serial_number"),
        "software": gen or None,
        "assertions": [a.get("label") for a in m.get("assertions", []) or []],
        "ingredients": [i.get("title") for i in m.get("ingredients", []) or []],
    }


def classify(scan: dict[str, Any], ver: dict[str, Any]) -> tuple[str, str]:
    if ver.get("sdk") is None:
        if scan["c2pa_bytes_found"]:
            return C2PA_UNVERIFIABLE, "JUMBF/C2PA bytes present but the c2pa SDK is not installed"
        if scan["xmp_provenance_reference"]:
            return C2PA_UNVERIFIABLE, "XMP references a remote manifest; not fetched (offline)"
        return C2PA_ABSENT, "no C2PA data found by container scan"
    if "error" in ver:
        err = ver.get("error_type", "")
        if "ManifestNotFound" in err:
            if scan["c2pa_bytes_found"]:
                return C2PA_INVALID, "C2PA-like bytes present but the SDK found no readable manifest"
            return C2PA_ABSENT, "no manifest found"
        if "RemoteManifest" in err:
            return C2PA_UNVERIFIABLE, "manifest is remote; network fetch disabled"
        if "NotSupported" in err:
            return C2PA_UNVERIFIABLE, "format not supported by the SDK"
        return C2PA_INVALID, f"SDK error: {ver.get('error')}"
    store = ver.get("manifest_store", {})
    state = (ver.get("validation_state") or store.get("validation_state") or "").lower()
    failures = [s for s in store.get("validation_status", []) or []
                if not str(s.get("code", "")).endswith(("trusted", "validated", "match", "insideValidity"))]
    if state == "invalid" or (not state and failures):
        return C2PA_INVALID, f"validation failed: {[f.get('code') for f in failures][:10]}"
    if state in ("valid", "trusted"):
        note = "signature valid and signer trusted" if state == "trusted" else \
            "manifest and signature structurally valid; signer not checked against a trust list"
        return C2PA_PRESENT, note
    return C2PA_UNVERIFIABLE, f"unrecognised validation state {state!r}"


def inspect_file(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    scan = scan_container(p)
    ver = verify(p)
    status, reason = classify(scan, ver)
    out: dict[str, Any] = {
        "file": str(p),
        "status": status,
        "reason": reason,
        "disclaimer": DISCLAIMER,
        "container": scan,
        "verification": {k: v for k, v in ver.items() if k != "manifest_store"},
    }
    store = ver.get("manifest_store")
    if store:
        out["manifest"] = _summarise_manifest(store)
        out["validation_status"] = store.get("validation_status")
    return out


def format_text(r: dict[str, Any]) -> str:
    lines = [f"File: {r['file']}", f"Status: {r['status']}  ({r['reason']})",
             f"Format: {r['container']['format']}  size={r['container']['size_bytes']} bytes",
             f"Metadata: {r['container']['metadata']}",
             f"JUMBF boxes: {r['container']['jumbf_boxes']}",
             f"Verifier: {r['verification'].get('sdk') or 'unavailable'}"]
    m = r.get("manifest")
    if m:
        lines += [f"Issuer: {m['issuer']}", f"Signing time: {m['signing_time']}",
                  f"Software: {m['software']}", f"Assertions: {m['assertions']}",
                  f"Ingredients: {m['ingredients']}"]
    lines.append(f"Note: {r['disclaimer']}")
    return "\n".join(lines)
