#!/usr/bin/env python3
"""Earnings Calendar Loader - reads from yfinance_snapshot table (not API).

CRITICAL FIX 2026-07-02: Consolidated yfinance calls. Reads next earnings date
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


class EarningsCalendarLoader(OptimalLoader):
    """Read earnings calendar from yfinance_snapshot table."""

    table_name = "earnings_calendar"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:
        """Read next earnings date from yfinance_snapshot table."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT earnings_date, data_available
                    FROM yfinance_snapshot
                    WHERE symbol = %s
                    """,
                    (symbol,),
                )
                row = cur.fetchone()

            if not row or not row.get("data_available"):
                logger.debug(f"[EARNINGS_CALENDAR] No calendar data for {symbol}")
                return None

            earnings_date = row["earnings_date"]
            if not earnings_date:
                logger.debug(f"[EARNINGS_CALENDAR] No next earnings date for {symbol}")
                return None

            return [
                {
                    "symbol": symbol,
                    "earnings_date": earnings_date,
                    "updated_at": date.today().isoformat(),
                }
            ]

        except Exception as e:
            logger.debug(f"[EARNINGS_CALENDAR] Error reading snapshot for {symbol}: {e}")
            return None


if __name__ == "__main__":
    sys.exit(run_loader(EarningsCalendarLoader))
