#!/usr/bin/env python3
"""Check orchestrator runs table schema."""

from utils.db import DatabaseContext

def main():
    """Check orchestrator runs table."""
    with DatabaseContext("read") as cur:
        # Get columns
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'algo_orchestrator_runs'
            ORDER BY ordinal_position
        """)

        columns = cur.fetchall()

        print("\n" + "="*70)
        print("TABLE: algo_orchestrator_runs")
        print("="*70)

        for col_name, col_type in columns:
            print(f"  {col_name:<30} {col_type}")

        # Get recent runs
        print(f"\n" + "="*70)
        print("RECENT RUNS")
        print("="*70 + "\n")

        cur.execute("""
            SELECT run_id, run_date, overall_status, halt_reason, completed_at
            FROM algo_orchestrator_runs
            ORDER BY completed_at DESC
            LIMIT 5
        """)

        for row in cur.fetchall():
            print(f"Run ID: {row[0]}")
            print(f"  Date: {row[1]}")
            print(f"  Status: {row[2]}")
            if row[3]:
                print(f"  Halt Reason: {row[3][:150]}")
            print(f"  Completed: {row[4]}\n")

if __name__ == "__main__":
    main()
