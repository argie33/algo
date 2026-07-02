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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:  # noqa: C901
        """Fetch earnings dates from yfinance for a symbol with graceful degradation.

        Keeps historical earnings (past 60 days) to properly gate blackout windows.
        Future earnings ensure new earnings surprises are caught before trading.

        Gracefully handles missing/unavailable earnings data by skipping the symbol
        (earnings calendar is optional enrichment, not critical trading data).

        Args:
            symbol: Stock ticker symbol
            since: Optional date to start from (unused, for OptimalLoader interface compatibility)

        Returns:
            list[dict[str, Any]]: List of earnings records with dates and estimates.
                Empty list if earnings data unavailable (graceful skip).
        """
        import pandas as pd

        from utils.external.yfinance import get_ticker

        max_retries = 3
        base_delay = 2.0

        for attempt in range(max_retries):
            try:
                ticker = get_ticker(symbol)
                if not ticker:
                    logger.debug(
                        f"[EARNINGS_CALENDAR] {symbol}: Failed to create ticker object "
                        f"(attempt {attempt + 1}/{max_retries}). Skipping symbol."
                    )
                    if attempt < max_retries - 1:
                        time.sleep(base_delay * (2**attempt))
                    raise RuntimeError(f"[EARNINGS_CALENDAR] {symbol}: Failed to fetch after {max_retries} retries")

                try:
                    cal = ticker.calendar
                    if not cal or not isinstance(cal, dict):
                        logger.warning(
                            f"[EARNINGS_CALENDAR] {symbol}: Calendar unavailable from yfinance. "
                            "Skipping symbol (no earnings data available)."
                        )
                        raise RuntimeError(f"[EARNINGS_CALENDAR] {symbol}: Calendar unavailable")

                    if "Earnings Date" not in cal:
                        logger.warning(
                            f"[EARNINGS_CALENDAR] {symbol}: Missing Earnings Date in calendar. "
                            "Skipping symbol (no earnings data available)."
                        )
                        raise RuntimeError(f"[EARNINGS_CALENDAR] {symbol}: Missing Earnings Date in calendar")

                    earnings_date_raw = cal["Earnings Date"]
                    cutoff_date = date.today() - timedelta(days=60)
                    # yfinance may return a list [start, end] or a single date/Timestamp
                    if isinstance(earnings_date_raw, list):
                        earnings_dates = earnings_date_raw
                    else:
                        earnings_dates = [earnings_date_raw]

                    results = []
                    for ed in earnings_dates:
                        if ed is None:
                            logger.debug(f"[EARNINGS_CALENDAR] {symbol}: Null earnings date. Skipping entry.")
                            continue
                        try:
                            ed_date = ed if isinstance(ed, date) else pd.Timestamp(ed).date()
                        except Exception as e:
                            logger.debug(
                                f"[EARNINGS_CALENDAR] {symbol}: Failed to parse earnings date {ed!r}: {e}. "
                                "Skipping entry."
                            )
                            continue

                        if ed_date >= cutoff_date:
                            # Optional fields: skip gracefully if conversion fails
                            eps_estimate = None
                            eps_avg_raw = cal.get("Earnings Average")
                            if eps_avg_raw is not None:
                                try:
                                    eps_estimate = float(eps_avg_raw)
                                except (ValueError, TypeError):
                                    logger.debug(
                                        f"[EARNINGS_CALENDAR] {symbol}: Could not convert EPS estimate. "
                                        "Recording without estimate."
                                    )

                            revenue_estimate = None
                            rev_avg_raw = cal.get("Revenue Average")
                            if rev_avg_raw is not None:
                                try:
                                    revenue_estimate = int(rev_avg_raw)
                                except (ValueError, TypeError):
                                    logger.debug(
                                        f"[EARNINGS_CALENDAR] {symbol}: Could not convert revenue estimate. "
                                        "Recording without estimate."
                                    )

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
                                f"[EARNINGS_CALENDAR] {symbol}: Found earnings date {ed_date} "
                                f"with EPS={eps_estimate}, Revenue={revenue_estimate}"
                            )

                    if not results:
                        logger.debug(
                            f"[EARNINGS_CALENDAR] {symbol}: No earnings within retention window. Skipping symbol."
                        )
                    return results

                except requests.exceptions.HTTPError as e:
                    logger.debug(
                        f"[EARNINGS_CALENDAR] {symbol}: HTTP error (attempt {attempt + 1}/{max_retries}): {e}. "
                        "Skipping symbol."
                    )
                    if attempt < max_retries - 1:
                        time.sleep(base_delay * (2**attempt))
                    raise RuntimeError(f"[EARNINGS_CALENDAR] {symbol}: Error parsing calendar after retry {attempt + 1}")
                except (KeyError, ValueError, TypeError) as e:
                    logger.warning(
                        f"[EARNINGS_CALENDAR] {symbol}: Error parsing calendar (attempt {attempt + 1}/{max_retries}): {e}. "
                        "Retrying."
                    )
                    if attempt < max_retries - 1:
                        time.sleep(base_delay * (2**attempt))
                    elif attempt == max_retries - 1:
                        raise RuntimeError(f"[EARNINGS_CALENDAR] {symbol}: Failed to parse calendar after {max_retries} retries") from e

            except (ConnectionError, TimeoutError) as e:
                error_type = "timeout" if isinstance(e, TimeoutError) else "connection"
                logger.warning(
                    f"[EARNINGS_CALENDAR] {symbol}: {error_type.upper()} (attempt {attempt + 1}/{max_retries}): {e}. "
                    "Retrying."
                )
                if attempt < max_retries - 1:
                    time.sleep(base_delay * (2**attempt))
                elif attempt == max_retries - 1:
                    raise RuntimeError(f"[EARNINGS_CALENDAR] {symbol}: Connection/timeout after {max_retries} retries") from e

        # Unreachable - loop with retries should raise or return by now
        logger.error(f"[EARNINGS_CALENDAR] {symbol}: Unexpected exit from retry loop")
        raise RuntimeError(f"[EARNINGS_CALENDAR] {symbol}: Retry loop exhausted without result")


if __name__ == "__main__":
    sys.exit(run_loader(EarningsCalendarLoader))
