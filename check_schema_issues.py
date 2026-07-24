#!/usr/bin/env python3
"""Check schema issues in key tables."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext


def check_schemas():
    """Check actual table schemas."""
    print("\n" + "="*80)
    print("CHECKING TABLE SCHEMAS")
    print("="*80 + "\n")

    try:
        with DatabaseContext("read") as cur:
            # Check signal_quality_scores table
            print("1. signal_quality_scores table")
            print("-" * 80)

            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'signal_quality_scores'
                ORDER BY ordinal_position
                """
            )

            columns = cur.fetchall()
            if columns:
                print(f"Found {len(columns)} columns:")
                for col_name, data_type in columns:
                    print(f"  {col_name:40s} {data_type}")
            else:
                print("Table not found or has no columns!")

            # Check buy_sell_daily table
            print("\n2. buy_sell_daily table")
            print("-" * 80)

            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'buy_sell_daily'
                ORDER BY ordinal_position
                """
            )

            columns = cur.fetchall()
            if columns:
                print(f"Found {len(columns)} columns:")
                for col_name, data_type in columns:
                    print(f"  {col_name:40s} {data_type}")

                # Check for signal_quality_score
                if any(c[0] == 'signal_quality_score' for c in columns):
                    print("  ✓ signal_quality_score column EXISTS")
                else:
                    print("  ✗ signal_quality_score column NOT FOUND")

            # Check algo_trades table
            print("\n3. algo_trades table")
            print("-" * 80)

            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'algo_trades'
                ORDER BY ordinal_position
                """
            )

            columns = cur.fetchall()
            if columns:
                print(f"Found {len(columns)} columns:")
                for col_name, data_type in columns:
                    print(f"  {col_name:40s} {data_type}")

            # Check table sizes
            print("\n4. TABLE SIZES & DATA")
            print("-" * 80)

            tables_to_check = [
                ("signal_quality_scores", "SELECT COUNT(*) FROM signal_quality_scores"),
                ("buy_sell_daily", "SELECT COUNT(*) FROM buy_sell_daily"),
                ("algo_trades", "SELECT COUNT(*) FROM algo_trades"),
            ]

            for table_name, count_query in tables_to_check:
                try:
                    cur.execute(count_query)
                    count = cur.fetchone()[0]
                    print(f"  {table_name:30s}: {count:,} rows")
                except Exception as e:
                    print(f"  {table_name:30s}: ERROR - {e}")

            # Check for recent buy_sell_daily with signal_quality_score
            print("\n5. RECENT buy_sell_daily SAMPLE")
            print("-" * 80)

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'buy_sell_daily'
                ORDER BY ordinal_position
                LIMIT 1
                """
            )

            first_col = cur.fetchone()
            if first_col:
                col_name = first_col[0]
                cur.execute(
                    f"""
                    SELECT *
                    FROM buy_sell_daily
                    ORDER BY signal_date DESC
                    LIMIT 1
                    """
                )

                row = cur.fetchone()
                if row:
                    col_names = [desc[0] for desc in cur.description]
                    print(f"Latest buy_sell_daily row ({len(col_names)} columns):")
                    for i, (name, value) in enumerate(zip(col_names, row)):
                        if i < 10:  # Show first 10 columns
                            val_str = str(value)[:40] if value else "NULL"
                            print(f"  {i+1:2d}. {name:40s}: {val_str}")
                    if len(col_names) > 10:
                        print(f"  ... and {len(col_names) - 10} more columns")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(check_schemas())
