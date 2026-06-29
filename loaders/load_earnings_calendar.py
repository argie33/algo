#!/usr/bin/env python3
"""Earnings Calendar Loader - Fetches upcoming earnings dates."""

import logging
import sys
import time
from datetime import date, timedelta
from typing import Any

import requests

from loaders.runner import run_loader
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class EarningsCalendarLoader(OptimalLoader):
    """Load upcoming earnings dates for all symbols."""

    table_name = "earnings_calendar"
    primary_key = ("symbol", "earnings_date")
    watermark_field = "updated_at"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:  # noqa: C901
        """Fetch earnings dates from yfinance for a symbol with retry logic.

        Keeps historical earnings (past 60 days) to properly gate blackout windows.
        Future earnings ensure new earnings surprises are caught before trading.

        Args:
            symbol: Stock ticker symbol
            since: Optional date to start from (unused, for OptimalLoader interface compatibility)

        Returns:
            list[dict[str, Any]]: List of earnings records with dates and estimates.
                Never returns None; raises exception if data unavailable.

        Raises:
            RuntimeError: On ticker creation failure or after max retries
            ValueError: On calendar parsing or data validation failure
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
                        f"[EARNINGS_CALENDAR] {symbol}: Failed to create ticker object (attempt {attempt + 1}/{max_retries})"
                    )
                    if not self._track_symbol_failure(symbol):
                        error_msg = f"[EARNINGS_CALENDAR] {symbol}: Exceeded max retries ({max_retries}) for ticker creation. Cannot load earnings without valid ticker."
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        time.sleep(delay)
                    continue

                results = []
                try:
                    cal = ticker.calendar
                    if not cal or not isinstance(cal, dict):
                        raise ValueError(
                            f"[EARNINGS_CALENDAR] {symbol}: Calendar is {type(cal).__name__} or empty. "
                            "Cannot fetch earnings data without valid calendar dict."
                        )

                    if "Earnings Date" not in cal:
                        raise ValueError(
                            f"[EARNINGS_CALENDAR] {symbol}: Missing 'Earnings Date' key in calendar dict. "
                            "Cannot proceed without earnings dates for blackout management."
                        )

                    earnings_date_raw = cal["Earnings Date"]
                    cutoff_date = date.today() - timedelta(days=60)
                    # yfinance may return a list [start, end] or a single date/Timestamp
                    if isinstance(earnings_date_raw, list):
                        earnings_dates = earnings_date_raw
                    else:
                        earnings_dates = [earnings_date_raw]

                    for ed in earnings_dates:
                        if ed is None:
                            raise ValueError(
                                f"[EARNINGS_CALENDAR] {symbol}: Null earnings date in yfinance response. "
                                "Cannot filter earnings data with missing dates."
                            )
                        try:
                            ed_date = ed if isinstance(ed, date) else pd.Timestamp(ed).date()
                        except Exception as e:
                            error_msg = (
                                f"[EARNINGS_CALENDAR] {symbol}: Failed to parse earnings date {ed!r}. "
                                "Cannot compute earnings blackout window with unparseable dates. "
                                f"Parser error: {type(e).__name__}: {e}"
                            )
                            logger.error(error_msg)
                            raise ValueError(error_msg) from e

                        if ed_date >= cutoff_date:
                            # Validate and convert optional estimates with explicit error handling
                            eps_estimate = None
                            eps_avg_raw = cal.get("Earnings Average")
                            if eps_avg_raw is not None:
                                try:
                                    eps_estimate = float(eps_avg_raw)
                                except (ValueError, TypeError) as e:
                                    logger.error(
                                        f"[EARNINGS_CALENDAR] {symbol}: Failed to convert EPS estimate {eps_avg_raw!r} to float. "
                                        f"Conversion error: {type(e).__name__}: {e}"
                                    )
                                    raise ValueError(
                                        f"[EARNINGS_CALENDAR] {symbol}: Invalid EPS estimate format in yfinance response"
                                    ) from e

                            revenue_estimate = None
                            rev_avg_raw = cal.get("Revenue Average")
                            if rev_avg_raw is not None:
                                try:
                                    revenue_estimate = int(rev_avg_raw)
                                except (ValueError, TypeError) as e:
                                    logger.error(
                                        f"[EARNINGS_CALENDAR] {symbol}: Failed to convert revenue estimate {rev_avg_raw!r} to int. "
                                        f"Conversion error: {type(e).__name__}: {e}"
                                    )
                                    raise ValueError(
                                        f"[EARNINGS_CALENDAR] {symbol}: Invalid revenue estimate format in yfinance response"
                                    ) from e

                            results.append(
                                {
                                    "symbol": symbol,
                                    "earnings_date": ed_date,
                                    "announce_time": None,
                                    "eps_estimate": eps_estimate,
                                    "actual_eps": None,
                                    "revenue_estimate": revenue_estimate,
                                    "actual_revenue": None,
                                    "fiscal_period": None,
                                }
                            )
                            logger.debug(
                                f"[EARNINGS_CALENDAR] {symbol}: Found earnings date {ed_date} with EPS={eps_estimate}, Revenue={revenue_estimate}"
                            )

                    if not results:
                        raise ValueError(
                            f"[EARNINGS_CALENDAR] {symbol}: No earnings dates found within 60-day retention window. "
                            "Cannot load earnings data without valid dates."
                        )
                    return results

                except requests.exceptions.HTTPError:
                    raise
                except (KeyError, ValueError, TypeError) as e:
                    logger.warning(
                        f"[EARNINGS_CALENDAR] {symbol}: Error parsing earnings calendar (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    if not self._track_symbol_failure(symbol):
                        error_msg = (
                            f"[EARNINGS_CALENDAR] {symbol}: Exceeded max retries ({max_retries}) for calendar parsing. "
                            f"Cannot load earnings data without valid calendar format."
                        )
                        logger.error(error_msg)
                        raise ValueError(error_msg) from e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        time.sleep(delay)

            except (ConnectionError, TimeoutError) as e:
                is_timeout = isinstance(e, TimeoutError)
                error_type = "timeout" if is_timeout else "connection"
                logger.warning(
                    f"[EARNINGS_CALENDAR] {symbol}: {error_type.upper()} error (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if not self._track_symbol_failure(symbol):
                    error_msg = f"[EARNINGS_CALENDAR] {symbol}: Exceeded max retries ({max_retries}) for {error_type} errors. Cannot fetch earnings data."
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    time.sleep(delay)

            except (ValueError, ZeroDivisionError, TypeError) as e:
                error_msg = str(e).lower()
                is_rate_limit = "429" in error_msg or "rate" in error_msg or "too many" in error_msg
                if is_rate_limit:
                    logger.warning(
                        f"[EARNINGS_CALENDAR] {symbol}: Rate limit error (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    if not self._track_symbol_failure(symbol):
                        error_msg_str = f"[EARNINGS_CALENDAR] {symbol}: Exceeded max retries ({max_retries}) for rate limit errors. Cannot load earnings data."
                        logger.error(error_msg_str)
                        raise RuntimeError(error_msg_str) from e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        time.sleep(delay)
                else:
                    error_msg_str = f"[EARNINGS_CALENDAR] {symbol}: Unexpected error fetching earnings: {e}"
                    logger.error(error_msg_str)
                    raise ValueError(error_msg_str) from e

        error_msg = f"[EARNINGS_CALENDAR] {symbol}: Failed to fetch earnings after {max_retries} retries. Cannot load earnings data."
        logger.error(error_msg)
        raise RuntimeError(error_msg)


if __name__ == "__main__":
    sys.exit(run_loader(EarningsCalendarLoader))
