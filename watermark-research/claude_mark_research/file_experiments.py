"""Metadata persistence experiments for image files.

These experiments record how ordinary file operations (re-save, format
conversion, pixel-only re-encode) affect *file metadata* and C2PA manifests.
They say nothing about Claude's statistical text watermark.

Outputs are new files in the output directory; the input is never modified.
No manifest is created, altered or forged: the operations are standard
Pillow saves, and the resulting C2PA status is only *observed*.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .c2pa import inspect_file

LABEL = "metadata persistence experiment (file metadata / C2PA only - not the text watermark)"


def _meta_summary(r: dict[str, Any]) -> dict[str, Any]:
    return {"format": r["container"]["format"], "metadata": r["container"]["metadata"],
            "c2pa_status": r["status"], "c2pa_reason": r["reason"]}


def run(path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:  # optional dependency
        raise RuntimeError("metadata experiments need Pillow (pip install Pillow)") from exc
    src = Path(path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    before = inspect_file(src)
    img = Image.open(src)
    img.load()
    rgb = img.convert("RGB")
    ops: list[tuple[str, Path, Any]] = []
    stem = src.stem
    fmt = (img.format or "").upper()
    if fmt == "PNG":
        ops.append(("png_resave", out / f"{stem}.resave.png", lambda p: img.save(p, "PNG")))
        ops.append(("png_to_jpeg", out / f"{stem}.to.jpg", lambda p: rgb.save(p, "JPEG", quality=95)))
    elif fmt == "JPEG":
        ops.append(("jpeg_resave", out / f"{stem}.resave.jpg", lambda p: rgb.save(p, "JPEG", quality=95)))
        ops.append(("jpeg_to_png", out / f"{stem}.to.png", lambda p: rgb.save(p, "PNG")))
    else:
        ops.append(("to_png", out / f"{stem}.to.png", lambda p: rgb.save(p, "PNG")))

    def pixel_only(p: Path) -> None:
        # Simulates a screenshot: only decoded pixels survive.
        Image.frombytes("RGB", rgb.size, rgb.tobytes()).save(p, "PNG")

    ops.append(("pixel_only_reencode (screenshot simulation)", out / f"{stem}.pixels.png", pixel_only))

    results = []
    for name, dest, fn in ops:
        fn(dest)
        after = inspect_file(dest)
        results.append({"operation": name, "output": str(dest),
                        "metadata_before": _meta_summary(before)["metadata"],
                        "metadata_after": _meta_summary(after)["metadata"],
                        "C2PA_before": before["status"], "C2PA_after": after["status"],
                        "c2pa_reason_after": after["reason"]})
    return {"label": LABEL, "input": str(src), "input_inspection": before, "experiments": results}
