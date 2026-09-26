#!/usr/bin/env python3
"""Write the OpenAPI specification to docs/openapi.json."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.main import app  # noqa: E402

(ROOT / "docs" / "openapi.json").write_text(json.dumps(app.openapi(), indent=1))
print(f"{len(app.openapi()['paths'])} paths written to docs/openapi.json")
