#!/usr/bin/env python3
"""Check stock_scores table and loader status."""

import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent / "api-pkg"))

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_stock_scores_status():
    """Check stock_scores loader status and table stats."""
    with DatabaseContext("read") as cursor:
        # Query 1: Check loader status
        print("\n=== LOADER STATUS ===")
        cursor.execute(
            """
            SELECT status, completion_pct, error_message, last_updated
            FROM data_loader_status
            WHERE table_name = 'stock_scores'
            """
        )
        loader_row = cursor.fetchone()
        if loader_row:
            status, completion_pct, error_msg, last_updated = loader_row
            print(f"Status: {status}")
            print(f"Completion: {completion_pct}%")
            print(f"Error Message: {error_msg}")
            print(f"Last Updated: {last_updated}")
        else:
            print("No loader status found for stock_scores")

        # Query 2: Check if stuck in RUNNING
        print("\n=== RUNNING STATE CHECK ===")
        cursor.execute(
            """
            SELECT status, completion_pct
            FROM data_loader_status
            WHERE table_name = 'stock_scores' AND status = 'RUNNING'
            """
        )
        running_row = cursor.fetchone()
        if running_row:
            print(f"WARNING: STUCK IN RUNNING STATE: {running_row[0]} at {running_row[1]}%")
        else:
            print("OK: Not stuck in RUNNING state")

        # Query 3: Total stocks and growth_score coverage
        print("\n=== STOCK SCORES COVERAGE ===")
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_stocks,
                SUM(CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END) as with_growth_score,
                SUM(CASE WHEN composite_score IS NOT NULL THEN 1 ELSE 0 END) as with_composite_score,
                SUM(CASE WHEN growth_score IS NULL THEN 1 ELSE 0 END) as null_growth_score
            FROM stock_scores
            """
        )
        row = cursor.fetchone()
        if row:
            total, with_growth, with_composite, null_growth = row
            growth_pct = (with_growth / total * 100) if total else 0
            composite_pct = (with_composite / total * 100) if total else 0
            print(f"Total stocks: {total}")
            print(f"With growth_score: {with_growth} ({growth_pct:.1f}%)")
            print(f"With composite_score: {with_composite} ({composite_pct:.1f}%)")
            print(f"NULL growth_score: {null_growth} ({100-growth_pct:.1f}%)")

        # Query 4: Check for exclusions/patterns
        print("\n=== EXCLUSION PATTERNS ===")
        cursor.execute(
            """
            SELECT
                symbol,
                COUNT(*) as occurrences,
                MAX(growth_score) as max_growth_score
            FROM stock_scores
            WHERE growth_score IS NULL
            GROUP BY symbol
            ORDER BY occurrences DESC
            LIMIT 10
            """
        )
        print("Top 10 stocks WITHOUT growth_score:")
        for symbol, count, max_score in cursor.fetchall():
            print(f"  {symbol}: {count} entries, max_growth_score={max_score}")

        # Query 5: Check for recent data
        print("\n=== RECENCY CHECK ===")
        cursor.execute(
            """
            SELECT
                MAX(created_at)::date as latest_date,
                MIN(created_at)::date as earliest_date,
                COUNT(DISTINCT DATE(created_at)) as distinct_dates
            FROM stock_scores
            """
        )
        latest, earliest, distinct_dates = cursor.fetchone()
        print(f"Latest data: {latest}")
        print(f"Earliest data: {earliest}")
        print(f"Distinct dates: {distinct_dates}")

        # Query 6: Check error logs
        print("\n=== ERROR LOGS (last 5) ===")
        try:
            cursor.execute(
                """
                SELECT timestamp, level, message
                FROM data_loader_logs
                WHERE table_name = 'stock_scores'
                ORDER BY timestamp DESC
                LIMIT 5
                """
            )
            error_logs = cursor.fetchall()
            if error_logs:
                for ts, level, msg in error_logs:
                    print(f"[{ts}] {level}: {msg}")
            else:
                print("No error logs found")
        except Exception as e:
            print(f"Error log table not available: {type(e).__name__}")

if __name__ == "__main__":
    try:
        check_stock_scores_status()
    except Exception as e:
        logger.error(f"Error checking stock_scores: {e}", exc_info=True)
        sys.exit(1)
