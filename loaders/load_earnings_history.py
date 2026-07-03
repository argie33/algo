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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read earnings dates from yfinance_snapshot table.

        Governance: Fail-fast on missing data. No silent fallbacks.

        Raises RuntimeError if yfinance_snapshot data unavailable (upstream loader dependency).
        Note: Some stocks legitimately have no earnings history (micro-caps, OTC).
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT earnings_dates, data_available, unavailable_reason
                FROM yfinance_snapshot
                WHERE symbol = %s
                """,
                (symbol,),
            )
            row = cur.fetchone()

        if not row:
            raise RuntimeError(
                f"[EARNINGS_HISTORY] {symbol}: yfinance_snapshot row not found. "
                f"Upstream loader (load_yfinance_snapshot) must run first. "
                f"Cannot fetch earnings history without snapshot data."
            )

        if not row.get("data_available"):
            raise RuntimeError(
                f"[EARNINGS_HISTORY] {symbol}: yfinance_snapshot data marked unavailable. "
                f"Reason: {row.get('unavailable_reason', 'unknown')}. "
                f"Upstream loader failed or API unavailable. Cannot proceed without yfinance data."
            )

        earnings_dates = row["earnings_dates"]
        if not earnings_dates:
            raise RuntimeError(
                f"[EARNINGS_HISTORY] {symbol}: No historical earnings dates in yfinance. "
                f"This is legitimate for micro-cap stocks, OTC securities, or newly public companies. "
                f"Data exists but no earnings history available. Cannot compute earnings analysis."
            )

        return [
            {
                "symbol": symbol,
                "earnings_dates": earnings_dates,
                "updated_at": date.today().isoformat(),
            }
        ]


if __name__ == "__main__":
    sys.exit(run_loader(EarningsHistoryLoader))
