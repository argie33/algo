#!/usr/bin/env python3
"""Company Profile Loader — fetches sector, industry, employees, etc. from yfinance.

Table: company_profile (symbol, short_name, long_name, sector, industry, exchange,
                        website, employees, currency_code)
Primary key: symbol (one row per company, upserted)

Run: python3 loaders/loadcompanyprofile.py [--symbols AAPL,MSFT] [--parallelism 4]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date
from typing import List, Optional

from utils.yfinance_wrapper import get_ticker

from config.env_loader import load_env
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

log = logging.getLogger(__name__)

class CompanyProfileLoader(OptimalLoader):
    table_name = "company_profile"
    primary_key = ("ticker",)
    watermark_field = None  # No date watermark — upsert on every run

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        try:
            yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol
            ticker = get_ticker(yf_symbol)
            info = ticker.info
            if not info or not info.get("symbol"):
                return None

            employees = info.get("fullTimeEmployees")
            if employees is not None:
                try:
                    employees = int(employees)
                except (TypeError, ValueError):
                    employees = None

            row = {
                "symbol": symbol,
                "ticker": symbol,
                "short_name": (info.get("shortName") or "")[:100],
                "long_name": (info.get("longName") or "")[:200],
                "display_name": (info.get("displayName") or info.get("shortName") or "")[:200],
                "sector": (info.get("sector") or "")[:100],
                "industry": (info.get("industry") or "")[:150],
                "exchange": (info.get("exchange") or "")[:20],
                "website": (info.get("website") or "")[:200],
                "employees": employees,
                "currency_code": (info.get("currency") or "USD")[:10],
            }
            return [row]
        except Exception as e:
            log.debug("Company profile error for %s: %s", symbol, e)
            return None

    def transform(self, rows):
        return rows

    def _get_or_create_watermark(self, symbol: str) -> Optional[date]:
        return None  # Always refetch — profiles change

    def _save_watermark(self, symbol: str, new_watermark) -> None:
        pass  # No watermark for profiles

def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=4)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = CompanyProfileLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
        if fail_rate > 0.05:
            logger.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
            return 1
        return 0

if __name__ == "__main__":
    sys.exit(main())
