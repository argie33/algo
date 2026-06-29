#!/usr/bin/env python3
"""Advance/Decline Line Daily Loader - Breadth momentum tracking.

Computes advance-decline line from trend_template_data (which contains SMA crossovers).
Direction: "up" if more advances than declines, "down" otherwise.

This is CRITICAL data for market_exposure calculation (6 points).

Run: python3 load_ad_line_daily.py [--backfill-days N]
"""

import logging
import sys
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast

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

        Computes from trend_template_data SMA crossovers.

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

                # Validate that trend_template_data has content for this date range
                cur.execute(
                    "SELECT COUNT(*) FROM trend_template_data WHERE date >= %s AND date <= %s",
                    (start, end),
                )
                row = cur.fetchone()
                if not row or row[0] == 0:
                    logger.warning(
                        f"[AD_LINE] trend_template_data is empty for {start} to {end}. "
                        f"Signal score computation may not have completed yet."
                    )
                    raise RuntimeError(
                        f"[AD_LINE CRITICAL] No trend data available for {start} to {end}. "
                        f"trend_template_data must be populated by signal score loader first."
                    )

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
                    logger.error(
                        f"[AD_LINE] No advance-decline aggregates computed for {start} to {end}. "
                        f"Check that trend_template_data has both advances and declines."
                    )
                    raise RuntimeError(
                        f"[AD_LINE CRITICAL] Cannot compute advance-decline line for {start} to {end}. "
                        f"Aggregation returned no results."
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
            logger.error(
                f"[AD_LINE] Database error during computation: {e.__class__.__name__}: {e}. "
                f"Cannot compute advance-decline line."
            )
            raise RuntimeError(
                f"[AD_LINE] Database error: {e}. Cannot compute advance-decline line without trend_template_data."
            ) from e

    def run(
        self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None
    ) -> dict[str, Any]:
        """Not applicable for market-wide loader. Use load_global() instead."""
        raise NotImplementedError("AD_LINE loader is market-wide only. Use load_global().")

    def _get_start_date(self, cur: Any) -> date:
        """Get start date from watermark or default to recent backfill.

        Raises:
            RuntimeError: If watermark query fails and we cannot proceed.
        """
        try:
            cur.execute("SELECT MAX(date) FROM ad_line_daily")
            row = cur.fetchone()
            if row and row[0] is not None:
                # Start one day after last record
                start_date = cast(date, row[0]) + timedelta(days=1)
                logger.info(f"[AD_LINE] Watermark found: resuming from {start_date}")
                return start_date

            # Table is empty, use default backfill
            default_start = date.today() - timedelta(days=30)
            logger.info(f"[AD_LINE] No watermark found, starting backfill from {default_start}")
            return default_start

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(
                f"[AD_LINE] Cannot retrieve watermark from ad_line_daily: {e}. Cannot determine safe restart point."
            )
            raise RuntimeError(f"[AD_LINE] Failed to get watermark for restart: {e}") from e

    def _get_end_date(self) -> date:
        """Get end date (latest trading day in ET).

        Walks backward from today until finding a trading day.

        Raises:
            RuntimeError: If no trading day found within lookback window.
        """
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(EASTERN_TZ)
        end = now_et.date()

        try:
            from algo.infrastructure import MarketCalendar
        except ImportError as e:
            logger.error(f"[AD_LINE] Cannot import MarketCalendar: {e}")
            raise RuntimeError(f"[AD_LINE] Missing MarketCalendar dependency: {e}") from e

        max_iterations = 365
        iterations = 0
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end) and iterations < max_iterations:
            end = end - timedelta(days=1)
            iterations += 1

        if iterations >= max_iterations:
            logger.error(
                f"[AD_LINE] Cannot find trading day within {max_iterations} days. "
                f"Last checked: {end}. Possible calendar outage."
            )
            raise RuntimeError(f"[AD_LINE] No trading day found within {max_iterations} days lookback")

        logger.debug(f"[AD_LINE] End date (latest trading day): {end}")
        return end


if __name__ == "__main__":
    sys.exit(run_loader(ADLineDailyLoader, description="Advance-decline line loader", global_mode=True))
