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

        Governance: Mark unavailable data explicitly. No silent fallbacks or exceptions.
        Returns data_unavailable marker instead of raising exceptions per GOVERNANCE.md.

        Note: Some stocks legitimately have no next earnings date (micro-caps, OTC).
        Returns:
            list[dict]: Either earnings calendar data or data_unavailable marker
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
            # yfinance_snapshot row not found — upstream loader dependency missing
            logger.debug(f"[EARNINGS_CALENDAR] {symbol}: yfinance_snapshot row not found (upstream dependency)")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "yfinance_snapshot_missing",
                    "updated_at": date.today().isoformat(),
                }
            ]

        if not row.get("data_available"):
            # yfinance data explicitly marked unavailable
            reason = row.get("unavailable_reason", "yfinance_api_unavailable")
            logger.debug(f"[EARNINGS_CALENDAR] {symbol}: yfinance_snapshot marked unavailable ({reason})")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"yfinance_snapshot_unavailable:{reason}",
                    "updated_at": date.today().isoformat(),
                }
            ]

        # earnings_date can be NULL legitimately (micro-caps, OTC, ADRs)
        earnings_date = row["earnings_date"]
        if not earnings_date:
            logger.debug(f"[EARNINGS_CALENDAR] {symbol}: No next earnings date (micro-cap/OTC/ADR)")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "no_earnings_date_available",
                    "updated_at": date.today().isoformat(),
                }
            ]

        # Data available — return real earnings calendar data
        return [
            {
                "symbol": symbol,
                "earnings_date": earnings_date,
                "data_unavailable": False,
                "updated_at": date.today().isoformat(),
            }
        ]


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    try:
        return run_loader(EarningsCalendarLoader)
    except Exception as e:
        logger.error(f"[EARNINGS_CALENDAR FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        # Mark data unavailable for all symbols
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute("""
                        INSERT INTO earnings_calendar (symbol, data_unavailable, reason, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT (symbol) DO UPDATE SET
                          data_unavailable = TRUE,
                          reason = EXCLUDED.reason,
                          updated_at = NOW()
                    """, (symbol, f"loader_crash:{type(e).__name__}"))
        except Exception as mark_err:
            logger.error(f"Failed to mark earnings_calendar data unavailable: {mark_err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
