#!/usr/bin/env python3
"""Drop 22 orphaned empty tables from database.

These tables were created for features that were never fully implemented
and remain empty (0 rows) after all prior consolidations.

Run: python3 scripts/cleanup_orphaned_tables.py

Safe to run multiple times (DROP TABLE IF EXISTS).
"""

import psycopg2
import sys

# Tables to drop: all have 0 rows, not used by any loader or application
ORPHANED_TABLES = [
    'analyst_sentiment',
    'can_slim_metrics',
    'commodity_price_history', 'commodity_prices', 'commodity_technicals',
    'earnings_estimate_revisions', 'earnings_estimate_trends', 'earnings_estimates',
    'earnings_metrics', 'earnings_surprise',
    'factor_metrics', 'index_metrics',
    'institutional_positioning',
    'loader_execution_metrics',
    'market_data', 'market_overview',
    'price_targets',
    'sentiment', 'sentiment_aggregate',
    'swing_trader_scores',
    'technical_data_monthly', 'technical_data_weekly',
]


def cleanup_orphaned_tables():
    """Drop all orphaned tables."""
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cur = conn.cursor()

        print("CLEANING UP ORPHANED TABLES")
        print("=" * 80)
        print(f"Dropping {len(ORPHANED_TABLES)} tables with 0 rows...\n")

        dropped = 0
        for table in ORPHANED_TABLES:
            try:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
                dropped += 1
                print(f"  [OK] {table}")
            except Exception as e:
                print(f"  [ERROR] {table}: {e}")

        conn.commit()
        cur.close()
        conn.close()

        print(f"\n{'=' * 80}")
        print(f"Successfully dropped {dropped}/{len(ORPHANED_TABLES)} tables")
        return 0

    except Exception as e:
        print(f"Database error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(cleanup_orphaned_tables())
