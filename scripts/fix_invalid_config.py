#!/usr/bin/env python3
"""Fix invalid config values in algo_config table.

This script corrects values that are outside their allowed ranges or have type mismatches.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import DatabaseContext

# Fixes to apply: (key, new_value, reason)
FIXES = [
    (
        "pyramid_split_pct",
        "50.0",
        "Type mismatch: was '50,33,17' (string), should be 50.0 (float)",
    ),
    (
        "patrol_high_volume_threshold",
        "10000000",
        "Out of range: was 100000000 (exceeds max 10000000)",
    ),
    (
        "patrol_price_daily_14d_min",
        "5000",
        "Out of range: was 40000 (exceeds max 10000)",
    ),
    (
        "data_staleness_stale_days_monday",
        "1",
        "Out of range: was 10 (exceeds max 2)",
    ),
    (
        "data_staleness_stale_days_other",
        "0",
        "Out of range: was 3 (exceeds max 1)",
    ),
]


def fix_config() -> None:
    """Apply all config fixes to database."""
    with DatabaseContext("write") as cur:
        for key, new_value, reason in FIXES:
            print(f"\n[FIX] {key}")
            print(f"  Reason: {reason}")
            print(f"  New value: {new_value}")

            # Check current value
            cur.execute("SELECT value FROM algo_config WHERE key = %s", (key,))
            row = cur.fetchone()
            if row:
                old_value = row[0]
                print(f"  Old value: {old_value}")
                cur.execute("UPDATE algo_config SET value = %s WHERE key = %s", (new_value, key))
                print("  [OK] Updated")
            else:
                print("  [WARN] Key not found in database, skipping")


if __name__ == "__main__":
    try:
        fix_config()
        print("\n[OK] All config fixes applied successfully")
    except Exception as e:
        print(f"\n[ERROR] Config fix failed: {e}")
        sys.exit(1)
