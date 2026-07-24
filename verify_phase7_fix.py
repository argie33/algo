#!/usr/bin/env python3
"""Verify Phase 7 fix by checking latest run logs."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext

try:
    with DatabaseContext("read") as cur:
        # Get the most recent orchestrator run
        cur.execute(
            """
            SELECT run_id, started_at, overall_status
            FROM algo_orchestrator_runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
        latest_run = cur.fetchone()
        if not latest_run:
            print("No orchestrator runs found")
            sys.exit(1)

        run_id, started_at, overall_status = latest_run
        print(f"\n{'='*80}")
        print(f"PHASE 7 FIX VERIFICATION")
        print(f"{'='*80}\n")
        print(f"Latest run: {run_id}")
        print(f"Started: {started_at}")
        print(f"Status: {overall_status}\n")

        # Get Phase 7 logs
        print("PHASE 7 LOGS:")
        print("-" * 80)

        cur.execute(
            """
            SELECT created_at, action_type, status, details->>'summary' as summary
            FROM algo_audit_log
            WHERE action_type LIKE 'phase_7%'
            AND details @> %s
            ORDER BY created_at ASC
            """,
            (json.dumps({"run_id": run_id}),),
        )

        phase7_logs = cur.fetchall()
        if phase7_logs:
            for created_at, action_type, status, summary in phase7_logs:
                icon = "✓" if status in ("success", "ok") else "⚠" if status == "warn" else "✗"
                print(f"{icon} [{created_at.strftime('%H:%M:%S')}] {action_type:50s} {status:10s}")
                if summary:
                    print(f"  {summary[:80]}")
        else:
            print("No Phase 7 logs found!")

        # Check for NOEM error specifically
        print("\n\nSEARCHING FOR NOEM ERRORS IN RECENT LOGS:")
        print("-" * 80)

        cur.execute(
            """
            SELECT created_at, action_type, details->>'summary' as summary
            FROM algo_audit_log
            WHERE created_at > NOW() - INTERVAL '2 hours'
            AND details->>'summary' ILIKE '%NOEM%'
            """
        )

        noem_errors = cur.fetchall()
        if noem_errors:
            print(f"⚠️ Found {len(noem_errors)} NOEM errors in last 2 hours:")
            for created_at, action_type, summary in noem_errors:
                print(f"  [{created_at}] {action_type}")
                if summary:
                    print(f"    {summary[:100]}")
        else:
            print("✅ No NOEM errors found in last 2 hours!")
            print("✅ PHASE 7 FIX APPEARS SUCCESSFUL!")

except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
