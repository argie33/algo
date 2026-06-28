#!/usr/bin/env python3
"""Check actual columns in tables."""

from utils.db import DatabaseContext

def main():
    """Check columns in key tables."""
    tables_to_check = [
        'algo_performance_daily',
        'algo_trades',
        'algo_positions',
        'circuit_breaker_status',
        'algo_portfolio_snapshots',
    ]

    with DatabaseContext("read") as cur:
        for table_name in tables_to_check:
            print(f"\n{'='*70}")
            print(f"TABLE: {table_name}")
            print('='*70)

            try:
                cur.execute(f"""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))

                columns = cur.fetchall()
                if columns:
                    for col_name, col_type in columns:
                        print(f"  {col_name:<30} {col_type}")
                else:
                    print(f"  [Table not found or no columns]")

                # Show sample data
                try:
                    cur.execute(f"SELECT COUNT(*) as row_count FROM {table_name}")
                    count_row = cur.fetchone()
                    count = count_row[0] if isinstance(count_row, tuple) else count_row.get('row_count', 0)
                    print(f"\n  Rows: {count}")
                except Exception as e:
                    print(f"  Rows: [Error: {e}]")

            except Exception as e:
                print(f"  ERROR: {e}")

if __name__ == "__main__":
    main()
