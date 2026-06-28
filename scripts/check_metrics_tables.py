#!/usr/bin/env python3
"""Check metrics tables."""

from utils.db import DatabaseContext


def main():
    """Check metrics tables."""
    tables = [
        'algo_performance_metrics',
        'algo_metrics_daily',
    ]

    with DatabaseContext("read") as cur:
        for table_name in tables:
            print(f"\n{'='*70}")
            print(f"TABLE: {table_name}")
            print('='*70)

            try:
                # Check if table exists and get columns
                cur.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                    LIMIT 15
                """, (table_name,))

                columns = cur.fetchall()
                if columns:
                    for col_name, col_type in columns:
                        print(f"  {col_name:<30} {col_type}")

                    # Count rows
                    cur.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
                    count = cur.fetchone()[0]
                    print(f"\n  Rows: {count}")

                    if count > 0:
                        # Show latest data
                        cur.execute(f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT 1")
                        row = cur.fetchone()
                        print("\n  Latest row:")
                        if row:
                            cols = [c[0] for c in cur.description]
                            for col, val in zip(cols[:5], row[:5], strict=False):
                                print(f"    {col}: {val}")
                else:
                    print("  [Table not found]")

            except Exception as e:
                print(f"  ERROR: {e}")

if __name__ == "__main__":
    main()
