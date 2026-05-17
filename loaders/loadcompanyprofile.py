#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Company Profile Loader — Sector, industry, and company info from yfinance.

Populates company_profile table with fundamental company data.
Sources: yfinance Ticker.info, local stock_symbols table.

Run:
    python3 loadcompanyprofile.py [--symbols AAPL,MSFT] [--parallelism 8]
"""
from utils.logging_setup import get_logger

import argparse
import logging
logger = get_logger(__name__)
import os
from datetime import date
from typing import List, Optional

from config.credential_helper import get_db_password
from config.env_loader import load_env
from utils.loader_helpers import get_active_symbols

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from utils.optimal_loader import OptimalLoader


log = logging.getLogger(__name__)


class CompanyProfileLoader(OptimalLoader):
    table_name = "company_profile"
    primary_key = ("ticker",)
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch company profile from yfinance."""
        try:
            import yfinance as yf
        except ImportError:
            log.warning("yfinance not installed")
            return None

        try:
            ticker_obj = yf.Ticker(symbol)
            info = ticker_obj.info or {}

            if not info:
                log.debug(f"No info for {symbol}")
                return None

            profile = {
                "ticker": symbol,
                "symbol": symbol,
                "short_name": info.get("shortName") or symbol,
                "long_name": info.get("longName") or info.get("shortName") or symbol,
                "display_name": info.get("shortName") or symbol,
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "exchange": info.get("exchange"),
                "website": info.get("website"),
                "employees": info.get("fullTimeEmployees"),
                "currency_code": info.get("currency"),
            }

            # Filter out None values except for optional fields
            return [profile]
        except Exception as e:
            log.debug(f"Error fetching profile for {symbol}: {e}")
            return None

    def transform(self, rows):
        return rows



def main():
    load_env()
    load_env()
    parser = argparse.ArgumentParser(description="Company profile loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    parser.add_argument("--parallelism", type=int, default=8)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = CompanyProfileLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
