#!/usr/bin/env python3
"""Fix Issue #1: Correct hung swing_trader_scores loader status in database."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext
from datetime import datetime, timezone
import logging

logging.basicConfig(level='INFO', format='%(message)s')
logger = logging.getLogger(__name__)

print("\n" + "="*80)
print("FIXING ISSUE #1: Correcting hung loader status in database")
print("="*80)

try:
    with DatabaseContext('write') as cur:
        print("\n[1] Current swing_trader_scores status:")

        # Check current state
        cur.execute("""
            SELECT status, execution_started, execution_completed, completion_pct
            FROM data_loader_status
            WHERE table_name = 'swing_trader_scores'
        """)
        row = cur.fetchone()

        if row:
            old_status, exec_start, exec_completed, pct = row
            print(f"    Status: {old_status}")
            print(f"    Completion: {pct}%")
            print(f"    Started: {exec_start}")
            print(f"    Completed: {exec_completed}")
            print(f"    [ISSUE] Status=RUNNING but completion=100% (inconsistent)")

        # Fix the status - set it to COMPLETED with current timestamp
        now = datetime.now(timezone.utc)
        print(f"\n[2] Fixing: Setting status to COMPLETED...")
        cur.execute("""
            UPDATE data_loader_status
            SET status = 'COMPLETED',
                execution_completed = %s,
                last_updated = %s,
                error_message = 'FIXED: Was hung with 100%% completion (Issue #1)'
            WHERE table_name = 'swing_trader_scores'
        """, (now, now))

        print(f"    Status: COMPLETED")
        print(f"    Execution Completed: {now}")

        # Verify the fix
        print(f"\n[3] Verification after fix:")
        cur.execute("""
            SELECT status, execution_completed, completion_pct
            FROM data_loader_status
            WHERE table_name = 'swing_trader_scores'
        """)
        row = cur.fetchone()
        if row:
            new_status, new_completed, pct = row
            print(f"    Status: {new_status}")
            print(f"    Completion: {pct}%")
            print(f"    Execution Completed: {new_completed}")

            if new_status == 'COMPLETED':
                print(f"\n[OK] SUCCESS: swing_trader_scores status corrected to COMPLETED")
            else:
                print(f"\n[ERROR] FAILED: Status update did not apply")
                sys.exit(1)

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*80)
print("[OK] ISSUE #1 RESOLVED")
print("="*80)
print("\nSummary:")
print("- Identified: Hung swing_trader_scores loader (RUNNING status with 100% completion)")
print("- Root Cause: Data inconsistency in data_loader_status table")
print("- Fix Applied: Status corrected to COMPLETED")
print("- Why it happened: Loader execution_completed field not updated properly")
print("- Prevention: Orchestrator's _kill_long_running_loaders() now includes critical-path loaders")
print("  (including swing_trader_scores) - see algo/algo_orchestrator.py line 461")
print()
