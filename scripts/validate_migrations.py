#!/usr/bin/env python3
"""Validate database migration files have required migration functions."""

import sys
from pathlib import Path


migrations_dir = Path("migrations/versions")
if migrations_dir.exists():
    for mig in sorted(migrations_dir.glob("*.py")):
        if mig.name.startswith("_"):
            continue
        try:
            content = mig.read_text(encoding="utf-8")
            has_migration_fn = "def up():" in content or "def upgrade():" in content
            if not has_migration_fn:
                print(f"ERROR: {mig.name} missing migration function (up or upgrade)")
                sys.exit(1)
            print(f"OK: {mig.name}")
        except Exception as e:
            print(f"ERROR: {mig.name}: {e}")
            sys.exit(1)

print("OK: All database migrations validated")
