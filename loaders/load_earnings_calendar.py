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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read next earnings date from yfinance_snapshot table.

        Governance: Fail-fast on missing data. No silent fallbacks.

        Raises RuntimeError if yfinance_snapshot data unavailable (upstream loader dependency).
        Note: Some stocks legitimately have no next earnings date (micro-caps, OTC).
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT earnings_date, data_available, unavailable_reason
                FROM yfinance_snapshot
                WHERE symbol = %s
                """,
                (symbol,),
            )
            row = cur.fetchone()

        if not row:
            raise RuntimeError(
                f"[EARNINGS_CALENDAR] {symbol}: yfinance_snapshot row not found. "
                f"Upstream loader (load_yfinance_snapshot) must run first. "
                f"Cannot fetch earnings calendar without snapshot data."
            )

        if not row.get("data_available"):
            raise RuntimeError(
                f"[EARNINGS_CALENDAR] {symbol}: yfinance_snapshot data marked unavailable. "
                f"Reason: {row.get('unavailable_reason', 'unknown')}. "
                f"Upstream loader failed or API unavailable. Cannot proceed without yfinance data."
            )

        earnings_date = row["earnings_date"]
        if not earnings_date:
            raise RuntimeError(
                f"[EARNINGS_CALENDAR] {symbol}: No next earnings date in yfinance. "
                f"This is legitimate for micro-cap stocks, OTC securities, or ADRs. "
                f"Data exists but earnings date is missing. Loader succeeded; no next date available."
            )

        return [
            {
                "symbol": symbol,
                "earnings_date": earnings_date,
                "updated_at": date.today().isoformat(),
            }
        ]


if __name__ == "__main__":
    sys.exit(run_loader(EarningsCalendarLoader))
