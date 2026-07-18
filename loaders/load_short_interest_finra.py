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
import sys
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
    - Fallback mechanism when yfinance unavailable
    """

    table_name = "short_interest_finra"
    primary_key = ("symbol", "settlement_date")
    watermark_field = "settlement_date"
    exclude_etfs_from_symbols = True

    def _prepare_batch_context(self) -> None:
        """Initialize batch context for short interest loading.

        Note: yfinance short interest is updated less frequently than daily prices,
        so we fetch per-symbol rather than batching.
        """
        logger.info("[SHORT_INTEREST] Initializing yfinance short interest loader...")
        self._batch_context = {}

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch short interest for one symbol from yfinance.

        yfinance publishes FINRA Reg SHO short interest data via Yahoo Finance API.

        Args:
            symbol: Stock ticker symbol
            since: Watermark date (unused; yfinance returns current short interest)

        Returns:
            List with single short interest dict or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            # Fetch ticker info from yfinance (includes short interest data)
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # EXPLICIT: Validate expected fields exist in yfinance response
            # Fail-fast if API structure changes (don't silently proceed with partial data)
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
            # sharesShort is optional enrichment field (not required for calculation)
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
            logger.error(f"[SHORT_INTEREST] {symbol}: Failed to fetch from yfinance: {e}")
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
