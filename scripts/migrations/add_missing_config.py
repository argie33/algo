#!/usr/bin/env python3
"""Add missing config keys to the database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from utils.db.context import DatabaseContext

# Missing config keys with sensible defaults based on loader thresholds
missing_config = {
    "price_daily_coverage_threshold_pct": "95",  # Typical loader completeness threshold
    "technical_daily_coverage_threshold_pct": "95",
    "buy_sell_daily_coverage_threshold_pct": "90",  # Slightly more lenient for signals
}

print("Adding missing config keys...")
print("=" * 100)

with DatabaseContext("write") as cur:
    for key, value in missing_config.items():
        cur.execute(
            """
            INSERT INTO algo_config (key, value, updated_at, updated_by)
            VALUES (%s, %s, NOW(), 'claude-code-fix')
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = NOW(), updated_by = 'claude-code-fix'
        """,
            (key, value),
        )
        print(f"[OK] {key} = {value}")

print("\n[OK] All missing config keys added successfully")
