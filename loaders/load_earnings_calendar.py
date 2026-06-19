#!/usr/bin/env python3
"""Earnings Calendar Loader - Fetches upcoming earnings dates."""

import argparse
import logging
import sys
from datetime import date
from typing import List, Optional

from utils.loaders.config import get_default_parallelism
from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)


class EarningsCalendarLoader(OptimalLoader):
    """Load upcoming earnings dates for all symbols."""

    table_name = "earnings_calendar"
    primary_key = ("symbol", "earnings_date")
    watermark_field = "updated_at"

    def fetch_incremental(
        self, symbol: str, since: Optional[date]
    ) -> Optional[List[dict]]:
        """Fetch earnings dates from yfinance for a symbol."""
        try:
            import pandas as pd

            from utils.external.yfinance import get_ticker

            ticker = get_ticker(symbol)
            if not ticker:
                raise RuntimeError(
                    f"[EARNINGS_CALENDAR] Failed to fetch ticker for {symbol}. "
                    "Cannot retrieve earnings dates without valid ticker."
                )

            results = []
            try:
                cal = ticker.calendar
                if cal and isinstance(cal, dict) and "Earnings Date" in cal:
                    earnings_date = cal["Earnings Date"]
                    if earnings_date and earnings_date >= date.today():
                        results.append(
                            {
                                "symbol": symbol,
                                "earnings_date": (
                                    earnings_date
                                    if isinstance(earnings_date, date)
                                    else pd.Timestamp(earnings_date).date()
                                ),
                                "announce_time": None,
                                "eps_estimate": (
                                    float(cal.get("Earnings Average"))
                                    if cal.get("Earnings Average")
                                    else None
                                ),
                                "actual_eps": None,
                                "revenue_estimate": (
                                    int(cal.get("Revenue Average"))
                                    if cal.get("Revenue Average")
                                    else None
                                ),
                                "actual_revenue": None,
                                "fiscal_period": None,
                            }
                        )
            except Exception as e:
                logger.debug(f"[{symbol}] ticker.calendar error: {e}")

            if not results:
                raise RuntimeError(
                    f"[EARNINGS_CALENDAR] No earnings date found for {symbol}. "
                    "Cannot load earnings data without upcoming dates."
                )
            return results
        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e


def main():
    parser = argparse.ArgumentParser(description="Earnings Calendar Loader")
    parser.add_argument(
        "--symbols", type=str, help="Comma-separated symbols, or blank for all active"
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=get_default_parallelism("earnings_calendar"),
        help="Parallel workers",
    )
    args = parser.parse_args()

    loader = EarningsCalendarLoader()

    if args.symbols:
        symbols = args.symbols.split(",")
    else:
        symbols = get_active_symbols()

    result = loader.run(symbols, parallelism=args.parallelism)

    if result["rows_inserted"] > 0:
        logger.info(f"SUCCESS: {result['rows_inserted']} earnings dates loaded")
        return 0
    else:
        logger.warning(
            f"COMPLETED: No earnings loaded (rows_fetched={result['rows_fetched']})"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
