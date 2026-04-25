#!/usr/bin/env python3
"""
Simple Analyst Sentiment Loader - Fixed version
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


def load_sentiment_for_symbol(symbol: str) -> dict:
    """Load analyst sentiment for a single symbol"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info if ticker else None

        if not info:
            return None

        # Extract sentiment data
        recommendation = info.get('recommendationKey', '')
        rating = info.get('recommendationRating', '')
        target_price = info.get('targetMeanPrice', 0)
        current_price = info.get('currentPrice', 0)
        num_analysts = info.get('numberOfAnalysts', 0)

        if not (recommendation or rating or num_analysts > 0):
            return None  # Skip if no sentiment data

        return {
            'symbol': symbol,
            'recommendation': recommendation,
            'rating': rating,
            'target_price': target_price,
            'current_price': current_price,
            'number_of_analysts': num_analysts,
            'loaded_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.debug(f"[{symbol}] Error: {str(e)[:50]}")
        return None


def main():
    helper = LoaderHelper(max_workers=4)

    # Get all symbols
    symbols = helper.get_sp500_symbols()
    logger.info(f"Loading sentiment for {len(symbols)} symbols")

    # Check which ones we already have
    conn = helper.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM analyst_sentiment_analysis")
    existing = set(row[0] for row in cur.fetchall())
    cur.close()
    conn.close()

    # Only load missing ones
    to_load = [s for s in symbols if s not in existing]
    logger.info(f"  Already have: {len(existing)}")
    logger.info(f"  Need to load: {len(to_load)}")

    # Process in parallel
    results = helper.process_symbols_parallel(to_load, load_sentiment_for_symbol)

    # Insert into database
    if results['results']:
        inserted = helper.batch_insert(
            'analyst_sentiment_analysis',
            results['results'],
            ['symbol', 'recommendation', 'rating', 'target_price', 'current_price', 'number_of_analysts', 'loaded_at']
        )
        logger.info(f"Inserted {inserted} rows")

    helper.report("SENTIMENT LOADER")


if __name__ == '__main__':
    main()
