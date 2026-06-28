#!/usr/bin/env python3
"""Check recent orchestrator execution logs."""

from utils.db import DatabaseContext

def main():
    """Check orchestrator logs."""
    with DatabaseContext("read") as cur:
        # Get recent runs
        cur.execute("""
            SELECT
                run_id,
                run_date,
                phase_1_status,
                phase_2_status,
                phase_3_status,
                phase_4_status,
                phase_5_status,
                phase_6_status,
                phase_7_status,
                phase_8_status,
                phase_9_status,
                error_message,
                created_at
            FROM algo_orchestrator_runs
            ORDER BY created_at DESC
            LIMIT 5
        """)

        runs = cur.fetchall()

        print("\n" + "="*100)
        print("RECENT ORCHESTRATOR RUNS")
        print("="*100 + "\n")

        if not runs:
            print("No orchestrator runs found.")
            return

        for run in runs:
            print(f"Run ID: {run[0]}")
            print(f"Date: {run[1]}")
            print(f"Created: {run[12]}")

            # Check phase statuses
            phases = [
                ("Phase 1 (Loaders)", run[2]),
                ("Phase 2 (Portfolio)", run[3]),
                ("Phase 3 (Risk)", run[4]),
                ("Phase 4 (Signals)", run[5]),
                ("Phase 5 (Filter)", run[6]),
                ("Phase 6 (Rank)", run[7]),
                ("Phase 7 (Size)", run[8]),
                ("Phase 8 (Audit)", run[9]),
                ("Phase 9 (Trade)", run[10]),
            ]

            for phase_name, status in phases:
                icon = "[OK]" if status == "SUCCESS" else ("[WARN]" if status == "WARNING" else "[ERROR]" if status == "ERROR" else "[SKIP]")
                print(f"  {icon} {phase_name:<30} {status}")

            if run[11]:
                print(f"\n  Error: {run[11][:200]}")

            print()

if __name__ == "__main__":
    main()
