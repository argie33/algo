#!/usr/bin/env python3
"""Sector Performance Loader - Calculate daily sector returns.

Calculates daily percentage returns for each sector based on weighted average
of constituent stock prices. Updates sector_performance table with latest data.

Schedule: Daily after market close
Cost: ~$0.01/run (single query)
"""

from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.errors

sys.path.insert(0, str(Path(__file__).parent.parent))

from loaders.runner import run_loader
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class SectorPerformanceLoader:
    """Load daily sector performance (return %) from stock prices."""

    table_name = "sector_performance"

    @staticmethod
    def load_symbol(symbol: str, since: date | None = None) -> list[dict[str, Any]]:
        """Not used for sector performance (global computation, not per-symbol)."""
        return []

    @staticmethod
    def load_global() -> int:
        """Calculate sector performance from daily price changes.

        Uses weighted average approach:
        1. Get all stocks with prices for target_date and previous day
        2. Calculate daily return % for each stock
        3. Group by sector and weight by market cap (using current price as proxy)
        4. Upsert into sector_performance table

        Args:
            target_date: Date to calculate performance for

        Returns:
            Number of records inserted/updated
        """
        prev_date = target_date - timedelta(days=1)

        # CRITICAL: Only calculate for trading days (Monday-Friday, market open)
        # Skip weekends and holidays automatically when no price data exists
        self.cur.execute(
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
                return_pct,  -- CRITICAL: Do NOT default missing returns to 0%
                1.0 as relative_strength,
                NOW() as created_at,
                NOW() as updated_at
            FROM sector_weighted_avg
            WHERE return_pct IS NOT NULL  -- CRITICAL: Skip sectors with missing/incomplete data
            ON CONFLICT (sector, date) DO UPDATE SET
                return_pct = EXCLUDED.return_pct,
                updated_at = NOW()
        """,
            (prev_date, target_date, target_date),
        )

        rows = self.cur.rowcount
        if rows <= 0:
            logger.warning(
                f"[{self.name}] No sector performance data calculated for {target_date} "
                "(may be weekend or missing price data)"
            )
            return 0

        # CRITICAL: Log if any sectors had missing/incomplete data
        # (These are skipped by WHERE return_pct IS NOT NULL clause)
        self.cur.execute(
            """
            WITH sector_calc AS (
                SELECT
                    sector,
                    SUM(daily_return * market_cap_proxy) / NULLIF(SUM(market_cap_proxy), 0) as return_pct
                FROM (
                    SELECT
                        cp.sector,
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
                ) daily_changes
                GROUP BY sector
            )
            SELECT sector FROM sector_calc WHERE return_pct IS NULL
            """,
            (prev_date, target_date),
        )
        missing_sectors = [row[0] for row in self.cur.fetchall()]
        if missing_sectors:
            logger.warning(
                f"[{self.name}] Sectors with missing/incomplete data (skipped): {missing_sectors}. "
                f"Possible causes: sector has no stocks with prices, missing price data"
            )

        self.cur.connection.commit()
        logger.info(f"[{self.name}] Loaded/updated {rows} sector performance records for {target_date}")
        return int(rows)


def run(cur: cursor) -> dict[str, Any]:
    """Entry point for orchestrator."""
    loader = SectorPerformanceLoader(cur)
    rows = loader.load()
    return {"status": "success", "rows_loaded": rows}
