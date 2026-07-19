#!/usr/bin/env python3
"""Sector Performance Loader - Calculate daily sector returns.

Market-wide computation (not per-symbol). Calculates daily percentage returns for each
sector based on weighted average of constituent stock prices.

Schedule: Daily after market close
Cost: ~$0.01/run (single query)
"""

import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import psycopg2

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


def main() -> int:
    """Calculate sector performance for latest trading date.

    Exit codes: 0=success, 1=error
    """
    table_name = "sector_performance"

    try:
        # Mark as RUNNING
        with DatabaseContext("write") as cur:
            cur.execute(
                "UPDATE data_loader_status SET status=%s, last_updated=NOW(), execution_started=NOW() WHERE table_name=%s",
                ("RUNNING", table_name),
            )
            if cur.rowcount == 0:
                cur.execute(
                    "INSERT INTO data_loader_status (table_name, status, last_updated, execution_started) VALUES (%s, %s, NOW(), NOW())",
                    (table_name, "RUNNING"),
                )

        target_date = date.today()
        prev_date = target_date - timedelta(days=1)

        # CRITICAL: Only calculate for trading days (Monday-Friday, market open)
        # Skip weekends and holidays automatically when no price data exists
        with DatabaseContext("write") as cur:
            cur.execute(
                """
                WITH daily_changes AS (
                    SELECT
                        cp.sector,
                        pd_today.symbol,
                        (pd_today.close - pd_prev.close) / NULLIF(pd_prev.close, 0) as daily_return,
                        pd_today.close as market_cap_proxy
                    FROM price_daily pd_today
                    INNER JOIN price_daily pd_prev
                        ON pd_today.symbol = pd_prev.symbol
                        AND pd_prev.date = %s
                    INNER JOIN company_profile cp ON pd_today.symbol = cp.symbol
                    WHERE pd_today.date = %s
                        AND cp.sector IS NOT NULL
                        AND cp.sector != ''
                ),
                sector_weighted_avg AS (
                    SELECT
                        sector,
                        SUM(daily_return * market_cap_proxy) / NULLIF(SUM(market_cap_proxy), 0) as return_pct,
                        COUNT(DISTINCT symbol) as stock_count
                    FROM daily_changes
                    GROUP BY sector
                )
                INSERT INTO sector_performance (sector, date, return_pct, relative_strength, created_at, updated_at)
                SELECT
                    sector,
                    %s as date,
                    return_pct,
                    1.0 as relative_strength,
                    NOW() as created_at,
                    NOW() as updated_at
                FROM sector_weighted_avg
                WHERE return_pct IS NOT NULL
                ON CONFLICT (sector, date) DO UPDATE SET
                    return_pct = EXCLUDED.return_pct,
                    updated_at = NOW()
            """,
                (prev_date, target_date, target_date),
            )

            rows = cur.rowcount
            if rows <= 0:
                logger.warning(f"[SECTOR_PERFORMANCE] No data for {target_date} (may be weekend/missing data)")
                rows_str = "0"
            else:
                logger.info(f"[SECTOR_PERFORMANCE] Loaded {rows} sector records for {target_date}")
                rows_str = str(rows)

            # Mark as COMPLETED
            cur.execute(
                "UPDATE data_loader_status SET status=%s, latest_date=%s, last_updated=NOW(), execution_completed=NOW() WHERE table_name=%s",
                ("COMPLETED", target_date, table_name),
            )

        logger.info(f"[SECTOR_PERFORMANCE] Completed successfully ({rows_str} rows)")
        return 0

    except Exception as e:
        logger.error(f"[SECTOR_PERFORMANCE] Failed: {type(e).__name__}: {e}", exc_info=True)
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE data_loader_status SET status=%s, last_updated=NOW(), execution_completed=NOW(), error_message=%s WHERE table_name=%s",
                    ("FAILED", str(e)[:500], table_name),
                )
        except Exception as update_err:
            logger.error(f"[SECTOR_PERFORMANCE] Failed to update status: {update_err}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
