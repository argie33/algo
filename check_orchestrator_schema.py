#!/usr/bin/env python3
"""Check the actual schema of algo_orchestrator_runs table."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext


def check_schema():
    """Check actual columns in algo_orchestrator_runs table."""
    print("\n" + "="*80)
    print("CHECKING algo_orchestrator_runs TABLE SCHEMA")
    print("="*80 + "\n")

    try:
        with DatabaseContext("read") as cur:
            # Get column information
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'algo_orchestrator_runs'
                ORDER BY ordinal_position
                """
            )

            columns = cur.fetchall()
            print(f"Found {len(columns)} columns:\n")

            for col_name, data_type, is_nullable in columns:
                nullable = "NULL" if is_nullable == "YES" else "NOT NULL"
                print(f"  {col_name:40s} {data_type:20s} {nullable}")

            # Get a sample row to see data
            print("\n" + "="*80)
            print("SAMPLE DATA (Last run)")
            print("="*80 + "\n")

            cur.execute(
                """
                SELECT *
                FROM algo_orchestrator_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )

            sample = cur.fetchone()
            if sample:
                # Get column names from cursor description
                col_names = [desc[0] for desc in cur.description]
                for name, value in zip(col_names, sample):
                    if value is None:
                        print(f"  {name:40s}: NULL")
                    elif isinstance(value, (int, float, bool)):
                        print(f"  {name:40s}: {value}")
                    else:
                        val_str = str(value)[:60]
                        print(f"  {name:40s}: {val_str}")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(check_schema())
