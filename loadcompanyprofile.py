#!/usr/bin/env python3
"""
Company Profile Loader — Sector, industry, and company info from yfinance.

Populates company_profile table with fundamental company data.
Sources: yfinance Ticker.info, local stock_symbols table.

Run:
    python3 loadcompanyprofile.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from credential_helper import get_db_password

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = Path(__file__).parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass

from optimal_loader import OptimalLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

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


def get_active_symbols() -> List[str]:
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=get_db_password(),
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
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
