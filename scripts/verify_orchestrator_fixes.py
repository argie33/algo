#!/usr/bin/env python3
"""
Quick verification script - run this after 9:30 AM market open.
Checks if the latest orchestrator run succeeded without the 4 known errors.
"""

import psycopg2
from datetime import datetime, timedelta
import sys

def main():
    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cur = conn.cursor()

    # Get latest orchestrator run
    cur.execute('''
    SELECT
      run_id,
      started_at,
      overall_status,
      halt_reason,
      execution_time_seconds
    FROM algo_orchestrator_runs
    ORDER BY started_at DESC
    LIMIT 1
    ''')

    row = cur.fetchone()
    if not row:
        print("ERROR: No orchestrator runs found in database")
        conn.close()
        return 1

    run_id, started_at, status, halt_reason, duration = row

    print("=== LATEST ORCHESTRATOR RUN ===\n")
    print(f"Run ID:     {run_id}")
    print(f"Time:       {started_at}")
    print(f"Status:     {status}")
    print(f"Duration:   {duration:.1f}s")
    print()

    # Check for the 4 known errors
    known_errors = [
        "Expectancy calculation failed",
        "position price updates failed",
        "Cannot calculate win rate",
        "Daily report generation fail",
    ]

    if halt_reason:
        print(f"Halt Reason: {halt_reason}\n")

        for err in known_errors:
            if err.lower() in halt_reason.lower():
                print(f"FAILED: Found known error '{err}' in halt reason")
                print("Fixes did not work - need investigation")
                conn.close()
                return 1

    # Check status
    if status == "success":
        print("SUCCESS: Orchestrator run succeeded without known errors!")
        print("Fixes are working - system ready for trading")
        conn.close()
        return 0
    elif status == "error":
        print("ERROR: Run failed with an error")
        print(f"Reason: {halt_reason}")
        conn.close()
        return 1
    elif status == "halted":
        print("HALTED: Run halted (may be legitimate portfolio rule)")
        print(f"Reason: {halt_reason}")
        if any(err.lower() in (halt_reason or "").lower() for err in known_errors):
            print("ERROR: This is one of the known errors that should be fixed")
            conn.close()
            return 1
        print("This halt is likely legitimate (portfolio rules, market hours, etc)")
        conn.close()
        return 0
    elif status == "degraded":
        print("DEGRADED: Run completed but in degraded mode")
        print(f"Reason: {halt_reason}")
        print("Check if this is expected (dry-run, market hours guard, etc)")
        if any(err.lower() in (halt_reason or "").lower() for err in known_errors):
            print("ERROR: Known error found - fixes not working")
            conn.close()
            return 1
        conn.close()
        return 0

    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
