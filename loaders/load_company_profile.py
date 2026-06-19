#!/usr/bin/env python3
"""Company Profile Loader - populate from yfinance with sector/industry enrichment."""

import logging
import sys
from datetime import date
from typing import List, Optional

from utils.external.yfinance import get_ticker
from utils.loaders.config import get_default_parallelism
from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)


class CompanyProfileLoader(OptimalLoader):
    """Load company profiles with sector and industry from yfinance."""

    table_name = "company_profile"
    primary_key = ("ticker",)
    watermark_field = "created_at"

    def fetch_incremental(
        self, symbol: str, since: date | None
    ) -> list[dict] | None:
        """Fetch company info from yfinance for a symbol."""
        ticker = get_ticker(symbol)
        if not ticker:
            raise RuntimeError(
                f"[COMPANY_PROFILE] Failed to fetch ticker for {symbol}. "
                "Cannot retrieve company profile without valid ticker."
            )
        try:
            info = ticker.info or {}
            market_cap = info.get("marketCap") or info.get("market_cap")
            return [
                {
                    "symbol": symbol,
                    "ticker": symbol,
                    "short_name": info.get("longName", ""),
                    "long_name": info.get("longName", ""),
                    "display_name": info.get("longName", ""),
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "exchange": info.get("exchange", ""),
                    "website": info.get("website"),
                    "employees": info.get("fullTimeEmployees"),
                    "market_cap": (
                        int(market_cap) if market_cap and market_cap > 0 else None
                    ),
                }
            ]
        except Exception as e:
            raise RuntimeError(
                f"[COMPANY_PROFILE] Failed to fetch profile for {symbol}: {e}. "
                "Cannot proceed without sector/industry data."
            )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Company Profile Loader")
    parser.add_argument(
        "--symbols", type=str, help="Comma-separated symbols, or blank for all active"
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=get_default_parallelism("company_profile"),
        help="Number of parallel workers",
    )
    args = parser.parse_args()

    loader = CompanyProfileLoader()

    if args.symbols:
        symbols = args.symbols.split(",")
    else:
        symbols = get_active_symbols()

    result = loader.run(symbols, parallelism=args.parallelism)

    if result["rows_inserted"] > 0:
        logger.info(f"SUCCESS: {result['rows_inserted']} company profiles loaded")
        return 0
    else:
        logger.warning(
            f"COMPLETED: No profiles loaded (rows_fetched={result['rows_fetched']})"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
