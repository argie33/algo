#!/usr/bin/env python3
"""
Simple Earnings Estimates Loader - Fixed version
Only loads S&P 500, skips timeouts gracefully
"""

import logging
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from datetime import datetime
import yfinance as yf
from loader_utils import LoaderHelper

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


def load_earnings_for_symbol(symbol: str) -> dict:
    """Load earnings estimates for a single symbol"""
    try:
        # Get ticker with timeout
        ticker = yf.Ticker(symbol)

        # Try to get info with a thread-based timeout
        info = ticker.info if ticker else None
        if not info:
            return None

        # Extract earnings estimates data
        next_earnings = info.get('nextEarningsDate')
        earnings_estimate = info.get('epsTrailingTwelveMonths')

        if not (next_earnings or earnings_estimate):
            return None  # Skip if no data

        return {
            'symbol': symbol,
            'next_earnings_date': next_earnings,
            'eps_estimate': earnings_estimate,
            'number_of_analysts': info.get('numberOfAnalysts', 0),
            'target_price': info.get('targetMeanPrice', 0),
            'loaded_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.debug(f"[{symbol}] Error: {str(e)[:50]}")
        return None


def main():
    helper = LoaderHelper(max_workers=4)

    # Get all symbols
    symbols = helper.get_sp500_symbols()
    logger.info(f"Loading earnings for {len(symbols)} symbols")

    # Check which ones we already have
    conn = helper.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM earnings_estimates")
    existing = set(row[0] for row in cur.fetchall())
    cur.close()
    conn.close()

    # Only load missing ones
    to_load = [s for s in symbols if s not in existing]
    logger.info(f"  Already have: {len(existing)}")
    logger.info(f"  Need to load: {len(to_load)}")

    # Process in parallel
    results = helper.process_symbols_parallel(to_load, load_earnings_for_symbol)

    # Insert into database
    if results['results']:
        inserted = helper.batch_insert(
            'earnings_estimates',
            results['results'],
            ['symbol', 'next_earnings_date', 'eps_estimate', 'number_of_analysts', 'target_price', 'loaded_at']
        )
        logger.info(f"Inserted {inserted} rows")

    helper.report("EARNINGS LOADER")


if __name__ == '__main__':
    main()
