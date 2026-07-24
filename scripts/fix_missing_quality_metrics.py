#!/usr/bin/env python3
"""Fix missing quality metrics for stocks without SEC data.

Problem: stock_scores has 5474 rows, but quality_metrics only has 5076 rows.
Result: 398 stocks show NULL quality_score ("No Data") on the dashboard.

Solution: Create placeholder metric rows for stocks with missing data_unavailable markers.

THIS IS A DATA REPAIR SCRIPT - must be run once to backfill missing rows.
After running, metrics loaders will maintain these rows going forward.
"""

import logging
import sys
from datetime import datetime, timezone

sys.path.insert(0, '/c/Users/arger/code/algo')

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_missing_metric_rows() -> dict[str, int]:
    """Create placeholder metric rows for stocks without complete data.

    Fixes missing rows in: quality_metrics, value_metrics, growth_metrics,
    positioning_metrics, stability_metrics.
    """

    results = {
        "quality_metrics": 0,
        "value_metrics": 0,
        "growth_metrics": 0,
        "positioning_metrics": 0,
        "stability_metrics": 0,
    }

    with DatabaseContext("write") as cur:
        now = datetime.now(timezone.utc)

        # Define metrics to fix
        metrics_to_fix = [
            ("quality_metrics", """
                INSERT INTO quality_metrics (
                    symbol, roe, roa, debt_to_equity, current_ratio, quick_ratio,
                    operating_margin, net_margin, interest_coverage, debt_to_assets,
                    data_unavailable, reason, updated_at
                )
                VALUES (%s, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, TRUE, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, updated_at = EXCLUDED.updated_at
            """),
            ("value_metrics", """
                INSERT INTO value_metrics (
                    symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, fcf_yield, dividend_yield,
                    held_percent_insiders, held_percent_institutions,
                    data_unavailable, reason, updated_at
                )
                VALUES (%s, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, TRUE, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, updated_at = EXCLUDED.updated_at
            """),
            ("growth_metrics", """
                INSERT INTO growth_metrics (
                    symbol, revenue_growth_1y, eps_growth_1y, revenue_growth_3y, eps_growth_3y,
                    revenue_growth_5y, eps_growth_5y,
                    data_unavailable, reason, updated_at
                )
                VALUES (%s, NULL, NULL, NULL, NULL, NULL, NULL, TRUE, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, updated_at = EXCLUDED.updated_at
            """),
            ("positioning_metrics", """
                INSERT INTO positioning_metrics (
                    symbol, institutional_ownership_pct, insider_ownership_pct, short_interest_pct,
                    data_unavailable, reason, updated_at
                )
                VALUES (%s, NULL, NULL, NULL, TRUE, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, updated_at = EXCLUDED.updated_at
            """),
            ("stability_metrics", """
                INSERT INTO stability_metrics (
                    symbol, beta, volatility_252d, volatility_60d, volatility_30d,
                    data_unavailable, reason, updated_at
                )
                VALUES (%s, NULL, NULL, NULL, NULL, TRUE, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, updated_at = EXCLUDED.updated_at
            """),
        ]

        # Process each metrics table
        for table_name, insert_sql in metrics_to_fix:
            logger.info(f"Fixing {table_name}...")

            # Find stocks with missing rows in this table
            cur.execute(f"""
            SELECT s.symbol
            FROM stock_scores s
            LEFT JOIN {table_name} m ON m.symbol = s.symbol
            WHERE m.symbol IS NULL
            ORDER BY s.symbol
            """)

            missing_symbols = [row[0] for row in cur.fetchall()]
            logger.info(f"  Found {len(missing_symbols)} missing rows in {table_name}")

            # Create placeholder rows
            created = 0
            for symbol in missing_symbols:
                try:
                    cur.execute(insert_sql, (symbol, "No data available", now))
                    created += 1
                    if created % 50 == 0:
                        logger.info(f"    Created {created}/{len(missing_symbols)} rows...")
                except Exception as e:
                    logger.error(f"    Failed for {symbol}: {e}")

            results[table_name] = created
            logger.info(f"  ✓ Created {created} rows in {table_name}")

        # Verify the fix
        logger.info("\nVerifying fix...")
        for table_name, _ in metrics_to_fix:
            cur.execute(f"""
            SELECT COUNT(*)
            FROM stock_scores s
            LEFT JOIN {table_name} m ON m.symbol = s.symbol
            WHERE m.symbol IS NULL
            """)
            remaining = cur.fetchone()[0]
            if remaining == 0:
                logger.info(f"  ✓ {table_name}: Complete ({5474} rows)")
            else:
                logger.error(f"  ✗ {table_name}: Still missing {remaining} rows")

    return results


def fix_missing_quality_metrics() -> dict[str, int]:
    """Deprecated - use fix_missing_metric_rows instead."""
    return fix_missing_metric_rows()


if __name__ == "__main__":
    try:
        result = fix_missing_metric_rows()
        total_created = sum(result.values())
        logger.info(f"\n✓ Fix complete: Created {total_created} total placeholder rows")
        for table, count in result.items():
            logger.info(f"  {table}: {count}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"✗ Fix failed: {e}", exc_info=True)
        sys.exit(1)
