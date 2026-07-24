#!/usr/bin/env python3
"""Simple check for Phase 7 NOEM errors."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext

try:
    with DatabaseContext("read") as cur:
        # Get latest run
        cur.execute(
            """SELECT run_id, started_at, overall_status FROM algo_orchestrator_runs ORDER BY started_at DESC LIMIT 1"""
        )
        result = cur.fetchone()
        if result:
            run_id, started_at, status = result
            print(f"Latest run: {run_id} at {started_at}")
            print(f"Status: {status}\n")

        # Check for NOEM errors in Phase 7 for last 3 hours
        print("Checking for Phase 7 NOEM errors in last 3 hours...")
        cur.execute(
            """
            SELECT COUNT(*) FROM algo_audit_log
            WHERE action_type LIKE 'phase_7%'
            AND created_at > NOW() - INTERVAL '3 hours'
            """
        )
        total_p7 = cur.fetchone()[0]
        print(f"Total Phase 7 logs: {total_p7}\n")

        # Check for NOEM mentions
        cur.execute(
            """
            SELECT COUNT(*) FROM algo_audit_log
            WHERE created_at > NOW() - INTERVAL '3 hours'
            AND (action_type LIKE '%NOEM%' OR details::TEXT ILIKE '%NOEM%')
            """
        )
        noem_count = cur.fetchone()[0]

        if noem_count > 0:
            print(f"⚠️ Found {noem_count} NOEM mentions - FIX INCOMPLETE")
        else:
            print(f"✅ No NOEM errors found - PHASE 7 FIX VERIFIED!")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
