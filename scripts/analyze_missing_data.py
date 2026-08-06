#!/usr/bin/env python3
"""Analyze which data fields have high NULL rates or missing data.

This helps identify which loaders or fields need work to complete data coverage.
"""

import sys
sys.path.insert(0, '.')

from utils.db.connection import get_db_connection

def analyze_table_nulls(table_name: str, limit_cols: int = 20) -> None:
    """Analyze NULL rates for all columns in a table."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Get column info
        cur.execute(f'''
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        ''', (table_name,))

        cols = cur.fetchall()
        if not cols:
            print(f"Table {table_name} not found")
            return

        print(f"\n{'='*80}")
        print(f"Analyzing {table_name} ({len(cols)} columns)")
        print(f"{'='*80}")

        # Sample query to get NULL rates
        col_list = [f"'{col[0]}'" for col in cols]
        cols_str = ', '.join(col_list)

        # Build CASE statements to count NULLs
        null_counts = []
        for col_name, _ in cols[:limit_cols]:
            null_counts.append(f"COUNT(CASE WHEN {col_name} IS NULL THEN 1 END) as null_{col_name}")

        if not null_counts:
            print("No columns to analyze")
            return

        query = f'''
            SELECT
                COUNT(*) as total_rows,
                {', '.join(null_counts)}
            FROM {table_name}
        '''

        cur.execute(query)
        result = cur.fetchone()

        if not result:
            print(f"No data in {table_name}")
            cur.close()
            conn.close()
            return

        total_rows = result[0]
        print(f"Total rows: {total_rows:,}")

        if total_rows == 0:
            print("[NO DATA IN TABLE]")
            cur.close()
            conn.close()
            return

        # Print NULL rates
        print(f"\n{'Column':<40} {'NULL Count':>12} {'NULL %':>10} Status")
        print("-" * 75)

        for i, (col_name, _) in enumerate(cols[:limit_cols]):
            null_count = result[i + 1]
            null_pct = (null_count / total_rows * 100) if total_rows > 0 else 0

            if null_pct > 50:
                marker = "[HIGH]"
            elif null_pct > 25:
                marker = "[MED]"
            elif null_pct > 0:
                marker = "[SOME]"
            else:
                marker = "[OK]"

            print(f"{col_name:<40} {null_count:>12,} {null_pct:>9.1f}% {marker}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error analyzing {table_name}: {e}")
        cur.close()
        conn.close()

def main():
    """Analyze key data tables for missing data."""
    tables = [
        'price_daily',
        'buy_sell_daily',
        'stock_scores',
        'value_quality_growth_metrics',
        'technical_data_daily',
        'financial_data',
        'analyst_estimates',
        'earnings_calendar',
        'economic_indicators',
        'sector_industry_daily',
    ]

    print("\n" + "="*80)
    print("DATA COMPLETENESS ANALYSIS")
    print("="*80)
    print("\nScanning for fields with high NULL rates...")

    for table in tables:
        try:
            analyze_table_nulls(table)
        except Exception as e:
            print(f"Skipping {table}: {e}")

if __name__ == "__main__":
    main()
