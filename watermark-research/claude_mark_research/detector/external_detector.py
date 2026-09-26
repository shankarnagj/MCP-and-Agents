"""Adapters for a user-supplied, authorised detector.

Two integration styles are supported:

1. Python plugin: ``--detector-plugin path/to/file.py:ClassName`` or
   ``--detector-plugin package.module:ClassName``. The class is instantiated
   with no arguments (or with ``**options`` from ``--detector-option k=v``) and
   must provide ``detect(text) -> DetectionResult | dict``.

2. Command: ``--detector-cmd "my-detector --json"``. The text is written to the
   command's stdin; the command must print one JSON object with the keys
   ``detected``, ``score``, ``p_value``, ``confidence`` (any may be null),
   optional ``detector_name`` and ``metadata``.

This module performs no network access itself; whatever the supplied
detector does is the user's responsibility and is recorded as such.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .base import DetectionResult, WatermarkDetector


def _load_class(spec: str):
    target, _, cls_name = spec.rpartition(":")
    if not target or not cls_name:
        raise ValueError("detector plugin must look like 'path/to/file.py:ClassName' or 'module:ClassName'")
    if target.endswith(".py") or Path(target).exists():
        path = Path(target).resolve()
        mod_spec = importlib.util.spec_from_file_location(f"_cmr_plugin_{path.stem}", path)
        if mod_spec is None or mod_spec.loader is None:
            raise ImportError(f"cannot load detector plugin {path}")
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)
    else:
        module = importlib.import_module(target)
    return getattr(module, cls_name)


class ExternalDetector(WatermarkDetector):
    name = "external"
    authoritative = True  # asserted by the user who supplies it

    def __init__(self, plugin: str | None = None, command: str | None = None,
                 options: dict[str, Any] | None = None, timeout: float = 120.0) -> None:
        if bool(plugin) == bool(command):
            raise ValueError("external detector needs exactly one of --detector-plugin or --detector-cmd")
        self.plugin_spec, self.command, self.timeout = plugin, command, timeout
        self._impl = _load_class(plugin)(**(options or {})) if plugin else None

    def detect(self, text: str) -> DetectionResult:
        if self._impl is not None:
            raw = self._impl.detect(text)
            if isinstance(raw, DetectionResult):
                res = raw
            elif isinstance(raw, dict):
                res = DetectionResult.from_mapping(raw, f"external:{self.plugin_spec}")
            else:  # duck-typed object
                res = DetectionResult.from_mapping(vars(raw), f"external:{self.plugin_spec}")
        else:
            proc = subprocess.run(shlex.split(self.command), input=text, capture_output=True,
                                  text=True, timeout=self.timeout, check=False)
            if proc.returncode != 0:
                raise RuntimeError(f"detector command failed ({proc.returncode}): {proc.stderr.strip()[:500]}")
            res = DetectionResult.from_mapping(json.loads(proc.stdout), f"external-cmd:{self.command}")
        res.metadata.setdefault("source", "user-supplied external detector")
        return res

    def describe(self):
        return {**super().describe(), "plugin": self.plugin_spec, "command": self.command,
                "note": "Authorisation and correctness of this detector are asserted by the user."}
