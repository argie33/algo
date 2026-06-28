#!/usr/bin/env python3
"""Check all orchestrator runs."""

from utils.db import DatabaseContext


def main():
    """Check orchestrator runs."""
    with DatabaseContext("read") as cur:
        # Count runs
        cur.execute("SELECT COUNT(*) as cnt FROM algo_orchestrator_runs")
        count = cur.fetchone()[0]
        print(f"\nTotal orchestrator runs: {count}\n")

        if count == 0:
            print("No runs found. System may not have been triggered yet.")
            return

        # Get all runs
        cur.execute("""
            SELECT run_id, run_date, overall_status, halt_reason, completed_at
            FROM algo_orchestrator_runs
            ORDER BY completed_at DESC
        """)

        print("="*100)
        print("ALL ORCHESTRATOR RUNS")
        print("="*100)

        for row in cur.fetchall():
            print(f"\nRun ID: {row[0]}")
            print(f"  Date: {row[1]}")
            print(f"  Status: {row[2]}")
            if row[3]:
                print(f"  Halt Reason: {row[3][:200]}")
            print(f"  Completed: {row[4]}")

if __name__ == "__main__":
    main()
