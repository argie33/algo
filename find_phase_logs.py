#!/usr/bin/env python3
"""Find where phase execution logs are stored."""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ


def find_phase_logs():
    """Find and analyze phase execution logs."""
    print("\n" + "="*80)
    print("FINDING PHASE EXECUTION LOGS")
    print("="*80 + "\n")

    try:
        with DatabaseContext("read") as cur:
            # Check algo_audit_log for phase information
            print("1. Checking algo_audit_log table structure...")
            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'algo_audit_log'
                ORDER BY ordinal_position
                """
            )

            columns = cur.fetchall()
            print(f"   Found {len(columns)} columns:")
            for col_name, data_type in columns:
                print(f"     - {col_name}: {data_type}")

            # Get sample phase logs
            print("\n2. Sample phase logs from last run...")
            cur.execute(
                """
                SELECT action_type, details, status, created_at
                FROM algo_audit_log
                WHERE action_type LIKE 'phase_%'
                ORDER BY created_at DESC
                LIMIT 20
                """
            )

            logs = cur.fetchall()
            if logs:
                print(f"   Found {len(logs)} phase log entries:\n")
                for action_type, details, status, created_at in logs:
                    print(f"   {created_at} | {action_type:40s} | {status:10s}")
                    if details:
                        details_str = str(details)[:80]
                        print(f"     Details: {details_str}")
            else:
                print("   No phase logs found!")

            # Check for other tables with phase info
            print("\n3. Checking for tables with 'phase' in name...")
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name LIKE '%phase%'
                AND table_schema = 'public'
                ORDER BY table_name
                """
            )

            phase_tables = cur.fetchall()
            if phase_tables:
                print("   Found phase-related tables:")
                for (table_name,) in phase_tables:
                    print(f"     - {table_name}")
            else:
                print("   No tables with 'phase' in name found")

            # Get a recent run and see what logs exist for it
            print("\n4. Analyzing recent run logs...")
            cur.execute(
                """
                SELECT run_id, started_at
                FROM algo_orchestrator_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )

            recent_run = cur.fetchone()
            if recent_run:
                run_id, started_at = recent_run
                print(f"   Recent run: {run_id} at {started_at}")

                # Find logs for this run
                cur.execute(
                    """
                    SELECT action_type, status, COUNT(*) as count
                    FROM algo_audit_log
                    WHERE details LIKE %s
                    GROUP BY action_type, status
                    ORDER BY count DESC
                    """,
                    (f"%{run_id}%",),
                )

                logs_for_run = cur.fetchall()
                if logs_for_run:
                    print(f"   Found {sum(r[2] for r in logs_for_run)} audit logs for this run:")
                    for action_type, status, count in logs_for_run:
                        print(f"     {action_type:40s} | {status:10s} | {count} entries")
                else:
                    print(f"   No audit logs found for run {run_id}")

            # Check if phase results are in separate execution table
            print("\n5. Looking for phase execution table...")
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name LIKE '%execution%' OR table_name LIKE '%orchestrat%'
                AND table_schema = 'public'
                ORDER BY table_name
                """
            )

            other_tables = cur.fetchall()
            if other_tables:
                print("   Found related tables:")
                for (table_name,) in other_tables:
                    # Get column count
                    cur.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM information_schema.columns
                        WHERE table_name = '{table_name}'
                        """
                    )
                    col_count = cur.fetchone()[0]
                    print(f"     - {table_name} ({col_count} columns)")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(find_phase_logs())
