#!/usr/bin/env python3
"""Fix max_positions config - with proper verification."""

from utils.db.context import DatabaseContext
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("Step 1: Check current value...")
with DatabaseContext("read") as cur:
    cur.execute("SELECT value FROM algo_config WHERE key='max_positions'")
    before = cur.fetchone()[0]
    print(f"  Before: max_positions={before}")

print("\nStep 2: Update to 15...")
try:
    with DatabaseContext("write") as cur:
        cur.execute("UPDATE algo_config SET value='15' WHERE key='max_positions'")
        print(f"  Updated: {cur.rowcount} rows")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\nStep 3: Verify update...")
with DatabaseContext("read") as cur:
    cur.execute("SELECT value FROM algo_config WHERE key='max_positions'")
    after = cur.fetchone()[0]
    print(f"  After: max_positions={after}")

if str(after) == "15":
    print("\n✓ SUCCESS: max_positions fixed to 15")
else:
    print(f"\n✗ FAILED: max_positions is still {after}, expected 15")
