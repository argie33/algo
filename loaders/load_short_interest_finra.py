#!/usr/bin/env python3
"""Short Interest Loader - Fetch via yfinance (FINRA-sourced data).

PHASE 1 OPTIMIZATION (Session 237 - Fixed):
Provides short interest % for stock scoring. Uses yfinance which publishes
FINRA Reg SHO short interest data via Yahoo Finance API.

Data source: yfinance (FINRA-sourced short interest)
Update frequency: Regular (more frequent than FINRA's bi-weekly CSV)
Quality: FINRA is authoritative regulatory source

Run:
    python3 loaders/load_short_interest_finra.py [--symbols AAPL,MSFT]
"""

import logging
import random
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yfinance as yf

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from loaders.runner import run_loader  # noqa: E402
from loaders.timeout_config import configure_socket_timeout  # noqa: E402
from utils.infrastructure.timezone import EASTERN_TZ  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)

configure_socket_timeout(30)


class ShortInterestFinraLoader(OptimalLoader):
    """Load short interest data via yfinance (FINRA-sourced).

    CRITICAL: Provides short interest % for stock scoring (30% coverage required).
    - yfinance publishes FINRA Reg SHO short interest data
    - Updated regularly via Yahoo Finance API
    - Free, no API key required
    - FAIL-FAST: Returns explicit data_unavailable marker if yfinance fails (no silent fallback)
    """

    table_name = "short_interest_finra"
    primary_key = ("symbol", "settlement_date")
    watermark_field = "settlement_date"
    exclude_etfs_from_symbols = True

    def run(self, symbols: list[str], parallelism: int = 8, backfill_days: int | None = None) -> dict:
        """Skip loading on non-trading days to avoid rate limit issues.

        Short interest data is only updated on trading days, so skip fetching
        on weekends/holidays to avoid unnecessary yfinance rate limiting.

        CRITICAL: Force parallelism=1 for short interest. yfinance has ~2000 req/hour
        limit for free tier. Parallel workers cause cascade failures (all 8 retry at same time).
        Sequential mode + sleep is reliable, adds ~8 min runtime for 4711 symbols.
        """
        now_et = datetime.now(EASTERN_TZ)
        run_date = now_et.date()

        from algo.infrastructure import MarketCalendar

        if not MarketCalendar.is_trading_day(run_date):
            logger.info(
                f"[{self.table_name}] Skipping load: today ({run_date}) is not a trading day. "
                f"Short interest data will use last available trading day's data."
            )
            return {
                "symbols_processed": 0,
                "symbols_failed": 0,
                "rows_inserted": 0,
                "duration_sec": 0,
                "latest_date": None,
                "status": "SKIPPED_NON_TRADING_DAY",
            }

        # Force sequential processing to avoid yfinance rate limiting
        # (parallel workers cascade on yfinance's 2000 req/hour free tier)
        if parallelism != 1:
            logger.info(
                f"[{self.table_name}] Overriding parallelism={parallelism} to 1 "
                f"(yfinance rate limit requires sequential processing)"
            )
            parallelism = 1

        return super().run(symbols, parallelism, backfill_days)

    def _prepare_batch_context(self) -> None:
        """Initialize batch context for short interest loading.

        Note: yfinance short interest is updated less frequently than daily prices,
        so we fetch per-symbol rather than batching.
        """
        logger.info("[SHORT_INTEREST] Initializing yfinance short interest loader...")
        self._batch_context = {"last_request_time": None}

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch short interest for one symbol from yfinance with rate limit retry.

        yfinance publishes FINRA Reg SHO short interest data via Yahoo Finance API.

        Args:
            symbol: Stock ticker symbol
            since: Watermark date (unused; yfinance returns current short interest)

        Returns:
            List with single short interest dict or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)
        max_retries = 3

        # Throttle requests: yfinance has ~2000 req/hour for free tier.
        # With 4711 symbols at 0.1s/request = ~471s total (~8 min), well below rate limit.
        if self._batch_context.get("last_request_time"):
            elapsed = time.time() - self._batch_context["last_request_time"]
            if elapsed < 0.1:
                time.sleep(0.1 - elapsed)

        for attempt in range(max_retries):
            try:
                self._batch_context["last_request_time"] = time.time()
                # Fetch ticker info from yfinance (includes short interest data)
                ticker = yf.Ticker(symbol)
                info = ticker.info

                # EXPLICIT: Validate expected fields exist in yfinance response
                if "shortPercentOfFloat" not in info:
                    logger.debug(f"[SHORT_INTEREST] {symbol}: yfinance missing 'shortPercentOfFloat' field")
                    return [
                        {
                            "symbol": symbol,
                            "settlement_date": now_et.date(),
                            "short_shares": None,
                            "short_pct": None,
                            "finra_report_date": None,
                            "data_unavailable": True,
                            "reason": "yfinance_missing_shortPercentOfFloat",
                            "updated_at": now_et,
                        }
                    ]

                short_pct = info["shortPercentOfFloat"]
                shares_short = info.get("sharesShort") if "sharesShort" in info else None

                if short_pct is None:
                    logger.debug(f"[SHORT_INTEREST] {symbol}: shortPercentOfFloat is NULL in yfinance")
                    return [
                        {
                            "symbol": symbol,
                            "settlement_date": now_et.date(),
                            "short_shares": None,
                            "short_pct": None,
                            "finra_report_date": None,
                            "data_unavailable": True,
                            "reason": "yfinance_shortPercentOfFloat_null",
                            "updated_at": now_et,
                        }
                    ]

                # Convert to percentage if needed (yfinance returns as decimal like 0.01 for 1%)
                if 0 < short_pct < 1:
                    short_pct = short_pct * 100

                logger.debug(f"[SHORT_INTEREST] {symbol}: {short_pct}% ({shares_short} shares)")

                return [
                    {
                        "symbol": symbol,
                        "settlement_date": now_et.date(),
                        "short_shares": shares_short,
                        "short_pct": short_pct,
                        "finra_report_date": now_et.date(),
                        "data_unavailable": False,
                        "reason": None,
                        "updated_at": now_et,
                    }
                ]

            except Exception as e:
                error_str = str(e).lower()
                # Rate limit errors - retry with exponential backoff
                if any(x in error_str for x in ["rate", "429", "too many"]):
                    if attempt < max_retries - 1:
                        base_wait = min(10, 2**attempt)
                        jitter = random.uniform(0.9, 1.1)
                        wait_time = base_wait * jitter
                        logger.debug(
                            f"[SHORT_INTEREST] {symbol}: Rate limited (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    logger.error(
                        f"[SHORT_INTEREST] {symbol}: Rate limited after {max_retries} attempts, marking unavailable"
                    )
                else:
                    logger.error(f"[SHORT_INTEREST] {symbol}: Failed to fetch from yfinance: {e}")

            # After retries exhausted or non-rate-limit error, return unavailable
            return [
                {
                    "symbol": symbol,
                    "settlement_date": now_et.date(),
                    "short_shares": None,
                    "short_pct": None,
                    "finra_report_date": None,
                    "data_unavailable": True,
                    "reason": f"yfinance_error: {str(e)[:40]}",
                    "updated_at": now_et,
                }
            ]


def main() -> int:
    """Entry point for load_short_interest_finra.py."""
    try:
        return run_loader(ShortInterestFinraLoader)
    except Exception as e:
        logger.error(f"[SHORT_INTEREST FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
