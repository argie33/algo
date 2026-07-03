#!/usr/bin/env python3
"""Earnings History Loader - reads from yfinance_snapshot table (not API).

CRITICAL FIX 2026-07-02: Consolidated yfinance calls. Reads earnings dates
from yfinance_snapshot table instead of making direct yfinance API calls.
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class EarningsHistoryLoader(OptimalLoader):
    """Read earnings history from yfinance_snapshot table."""

    table_name = "earnings_history"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 99.5

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:
        """Read earnings dates from yfinance_snapshot table."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT earnings_dates, data_available
                    FROM yfinance_snapshot
                    WHERE symbol = %s
                    """,
                    (symbol,),
                )
                row = cur.fetchone()

            if not row or not row.get("data_available"):
                logger.debug(f"[EARNINGS_HISTORY] Earnings data unavailable for {symbol}")
                return None

            earnings_dates = row["earnings_dates"]
            if not earnings_dates:
                logger.debug(f"[EARNINGS_HISTORY] No earnings dates for {symbol}")
                return None

            return [
                {
                    "symbol": symbol,
                    "earnings_dates": earnings_dates,
                    "updated_at": date.today().isoformat(),
                }
            ]

        except Exception as e:
            logger.debug(f"[EARNINGS_HISTORY] Error reading snapshot for {symbol}: {e}")
            return None


if __name__ == "__main__":
    sys.exit(run_loader(EarningsHistoryLoader))
