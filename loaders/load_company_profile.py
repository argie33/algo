#!/usr/bin/env python3
"""Company Profile Loader - populate from yfinance with sector/industry enrichment."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date
from typing import Optional, List

import yfinance as yf

from utils.optimal_loader import OptimalLoader
from utils.loader_helpers import get_active_symbols

logger = logging.getLogger(__name__)


class CompanyProfileLoader(OptimalLoader):
    """Load company profiles with sector and industry from yfinance."""

    table_name = "company_profile"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch company info from yfinance for a symbol."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            return [{
                'symbol': symbol,
                'ticker': symbol,
                'short_name': info.get('longName', ''),
                'long_name': info.get('longName', ''),
                'display_name': info.get('longName', ''),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'exchange': info.get('exchange', ''),
                'website': info.get('website'),
                'employees': info.get('fullTimeEmployees'),
            }]
        except Exception as e:
            logger.debug(f"Could not fetch yfinance data for {symbol}: {e}")
            return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Company Profile Loader')
    parser.add_argument('--symbols', type=str, help='Comma-separated symbols, or blank for all active')
    parser.add_argument('--parallelism', type=int, default=2, help='Number of parallel workers')
    args = parser.parse_args()

    loader = CompanyProfileLoader()

    if args.symbols:
        symbols = args.symbols.split(',')
    else:
        symbols = get_active_symbols()

    result = loader.run(symbols, parallelism=args.parallelism)

    if result["rows_inserted"] > 0:
        logger.info(f"SUCCESS: {result['rows_inserted']} company profiles loaded")
        return 0
    else:
        logger.warning(f"COMPLETED: No profiles loaded (rows_fetched={result['rows_fetched']})")
        return 0


if __name__ == '__main__':
    sys.exit(main())
