#!/usr/bin/env python3
"""Earnings Calendar Loader - Fetches upcoming earnings dates."""

import argparse
import logging
import sys
import time
from datetime import date, timedelta

from utils.loaders.config import get_default_parallelism
from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)


class EarningsCalendarLoader(OptimalLoader):
    """Load upcoming earnings dates for all symbols."""

    table_name = "earnings_calendar"
    primary_key = ("symbol", "earnings_date")
    watermark_field = "updated_at"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._failed_symbols: dict[str, int] = {}
        self._failed_symbols_lock = __import__("threading").Lock()
        self._max_per_symbol_retries = 3

    def _track_symbol_failure(self, symbol: str) -> bool:
        """Track symbol failure and return True if we should retry."""
        with self._failed_symbols_lock:
            failures = self._failed_symbols.get(symbol, 0)
            if failures < self._max_per_symbol_retries:
                self._failed_symbols[symbol] = failures + 1
                return True
            return False

    def fetch_incremental(
        self, symbol: str, since: date | None
    ) -> list[dict] | None:
        """Fetch earnings dates from yfinance for a symbol with retry logic.

        Keeps historical earnings (past 60 days) to properly gate blackout windows.
        Future earnings ensure new earnings surprises are caught before trading.
        """
        import pandas as pd

        from utils.external.yfinance import get_ticker

        max_retries = 3
        base_delay = 2.0

        for attempt in range(max_retries):
            try:
                ticker = get_ticker(symbol)
                if not ticker:
                    logger.warning(
                        f"[{symbol}] Failed to create ticker object (attempt {attempt + 1}/{max_retries})"
                    )
                    if not self._track_symbol_failure(symbol):
                        logger.error(f"[{symbol}] Exceeded max retries for ticker creation")
                        return None
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
                    continue

                results = []
                try:
                    cal = ticker.calendar
                    if cal and isinstance(cal, dict) and "Earnings Date" in cal:
                        earnings_date = cal["Earnings Date"]
                        cutoff_date = date.today() - timedelta(days=60)
                        if earnings_date and earnings_date >= cutoff_date:
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
                                        float(eps_est)
                                        if (eps_est := cal.get("Earnings Average")) is not None
                                        else None
                                    ),
                                    "actual_eps": None,
                                    "revenue_estimate": (
                                        int(rev_est)
                                        if (rev_est := cal.get("Revenue Average")) is not None
                                        else None
                                    ),
                                    "actual_revenue": None,
                                    "fiscal_period": None,
                                }
                            )
                            logger.debug(f"[{symbol}] Found earnings date: {earnings_date}")
                            return results
                    else:
                        logger.debug(f"[{symbol}] No earnings date in calendar (within cutoff)")
                        return []

                except (KeyError, ValueError, TypeError) as e:
                    logger.warning(
                        f"[{symbol}] Error parsing earnings calendar (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    if not self._track_symbol_failure(symbol):
                        logger.error(f"[{symbol}] Exceeded max retries for calendar parsing")
                        return None
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)

            except (ConnectionError, TimeoutError) as e:
                is_timeout = isinstance(e, TimeoutError)
                error_type = "timeout" if is_timeout else "connection"
                logger.warning(
                    f"[{symbol}] {error_type.upper()} error (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if not self._track_symbol_failure(symbol):
                    logger.error(f"[{symbol}] Exceeded max retries for {error_type} errors")
                    return None
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)

            except Exception as e:
                error_msg = str(e).lower()
                is_rate_limit = "429" in error_msg or "rate" in error_msg or "too many" in error_msg
                if is_rate_limit:
                    logger.warning(
                        f"[{symbol}] Rate limit error (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    if not self._track_symbol_failure(symbol):
                        logger.error(f"[{symbol}] Exceeded max retries for rate limit errors")
                        return None
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
                else:
                    logger.error(f"[{symbol}] Unexpected error fetching earnings: {e}")
                    return None

        logger.error(f"[{symbol}] Failed to fetch earnings after {max_retries} retries")
        return None


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
