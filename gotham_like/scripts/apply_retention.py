#!/usr/bin/env python3
"""Redact raw source-record payloads older than each source's retention period."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import session_scope  # noqa: E402
from app.privacy.retention import apply_retention  # noqa: E402

with session_scope() as db:
    print(json.dumps(apply_retention(db), indent=2))
