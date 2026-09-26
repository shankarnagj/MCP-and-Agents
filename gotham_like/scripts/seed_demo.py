#!/usr/bin/env python3
"""Create schema, demo users, load SYNTHETIC / DEMONSTRATION DATA, run ER, rules and alerts.

    python scripts/seed_demo.py            # uses TESSERA_DATABASE_URL
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import SessionLocal  # noqa: E402
from app.services.demo_loader import load_demo  # noqa: E402
from app.services.seed import demo_password, migrate, seed_geofence, seed_rules_and_signals, seed_users  # noqa: E402


def main() -> None:
    t0 = time.time()
    migrate()
    with SessionLocal() as db:
        created = seed_users(db)
        seed_geofence(db)
        db.commit()
        report = load_demo(db)
        results = report.pop("results")
        rules = seed_rules_and_signals(db, results)
        db.commit()
    print(json.dumps({"users_created": created, "demo_password": demo_password() if created else "(unchanged)",
                      "ingestion": [{k: r[k] for k in ("source_id", "records_seen", "records_new", "records_changed", "error_count")} for r in report["ingestion"]],
                      "entity_resolution": [{k: v for k, v in r.items() if k != "merge_examples"} for r in report["entity_resolution"]],
                      "rules": rules, "seconds": round(time.time() - t0, 1)}, indent=2))


if __name__ == "__main__":
    main()
