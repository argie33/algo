#!/usr/bin/env python3
"""Advance/Decline Line Daily Loader - Breadth momentum tracking.

Computes advance-decline line from trend_template_data (which contains SMA crossovers).
Direction: "up" if more advances than declines, "down" otherwise.

This is CRITICAL data for market_exposure calculation (6 points).

Run: python3 load_ad_line_daily.py [--backfill-days N]
"""

import logging
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg2

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class ADLineDailyLoader(OptimalLoader):
    """Advance/Decline Line loader - compute breadth direction."""

    table_name = "ad_line_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def load_global(self) -> int:
        """Load advance-decline line direction (market-wide, not per-symbol).

        Raises:
            RuntimeError: If underlying data unavailable or computation fails.
        """
        try:
            with DatabaseContext("write") as cur:
                start = self._get_start_date(cur)
                end = self._get_end_date()

                if start > end:
                    logger.info(f"[AD_LINE] No backfill needed (watermark {start} >= end {end})")
                    return 0

                logger.info(f"[AD_LINE] Computing advance-decline line from {start} to {end}")

                # Get advance/decline counts from trend_template_data
                cur.execute(
                    """
                    WITH ad_counts AS (
                        SELECT
                            date,
                            COUNT(*) FILTER (WHERE price_above_sma50 = true) AS advances,
                            COUNT(*) FILTER (WHERE price_above_sma50 = false) AS declines
                        FROM trend_template_data
                        WHERE date >= %s AND date <= %s
                        GROUP BY date
                        ORDER BY date ASC
                    )
                    SELECT
                        date,
                        advances,
                        declines,
                        CASE WHEN advances > declines THEN 'up' ELSE 'down' END AS direction,
                        CASE WHEN (advances + declines) > 0
                            THEN advances::NUMERIC / (advances + declines)
                            ELSE NULL
                        END AS advance_decline_ratio
                    FROM ad_counts
                    """,
                    (start, end),
                )

                rows = cur.fetchall()
                if not rows or len(rows) == 0:
                    raise RuntimeError(
                        f"[AD_LINE CRITICAL] No advance-decline data available for {start} to {end}. "
                        f"Check trend_template_data population (requires signal score computation)."
                    )

                # Upsert into ad_line_daily
                inserted = 0
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO ad_line_daily (date, advances, declines, direction, advance_decline_ratio, updated_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (date)
                        DO UPDATE SET
                            advances = EXCLUDED.advances,
                            declines = EXCLUDED.declines,
                            direction = EXCLUDED.direction,
                            advance_decline_ratio = EXCLUDED.advance_decline_ratio,
                            updated_at = NOW()
                        """,
                        (row[0], row[1], row[2], row[3], row[4]),
                    )
                    inserted += 1

                cur.connection.commit()
                logger.info(f"[AD_LINE] ✓ Loaded {inserted} advance-decline line records")
                return inserted

        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[AD_LINE] Database error: {e}. "
                f"Cannot compute advance-decline line without trend_template_data."
            ) from e

    def run(self, symbols: list[str], **kwargs: Any) -> dict[str, Any]:
        """Not applicable for market-wide loader. Use load_global() instead."""
        raise NotImplementedError("AD_LINE loader is market-wide only. Use load_global().")

    def _get_start_date(self, cur: Any) -> date:
        """Get start date from watermark or default to recent backfill."""
        try:
            cur.execute("SELECT MAX(date) FROM ad_line_daily")
            row = cur.fetchone()
            if row and row[0] is not None:
                # Start one day after last record
                return row[0] + timedelta(days=1)
        except (psycopg2.DatabaseError, psycopg2.OperationalError):
            pass

        # Default: last 30 days if table is empty
        return date.today() - timedelta(days=30)

    def _get_end_date(self) -> date:
        """Get end date (latest trading day in ET)."""
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(EASTERN_TZ)
        end = now_et.date()

        from algo.infrastructure import MarketCalendar

        max_iterations = 365
        iterations = 0
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end) and iterations < max_iterations:
            end = end - timedelta(days=1)
            iterations += 1

        return end


if __name__ == "__main__":
    sys.exit(run_loader(ADLineDailyLoader, description="Advance-decline line loader", global_mode=True))
