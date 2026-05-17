#!/usr/bin/env python3
"""
Load value metrics (PE, PB, PS ratios) from yfinance for all tradeable symbols.

This loader:
1. Gets all symbols with price_daily data
2. Fetches PE, PB, PS, dividend yield from yfinance
3. INSERTs records (if not exist) or UPDATEs (if exist)
4. Handles errors gracefully

USAGE:
    python3 load_value_metrics_from_yfinance.py                 # all symbols with prices
    python3 load_value_metrics_from_yfinance.py --symbols SPY,AAPL,MSFT
    python3 load_value_metrics_from_yfinance.py --limit 100     # first 100 symbols
"""

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import psycopg2
import yfinance as yf
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
env_file = Path(__file__).parent / '.env.local'
if not env_file.exists():
    env_file = Path(__file__).parent.parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

try:
    from config.credential_helper import get_db_password
except ImportError:
    def get_db_password():
        return os.getenv("DB_PASSWORD", "")


def get_db_conn():
    """Get database connection."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=get_db_password(),
        database=os.getenv('DB_NAME', 'stocks'),
    )


def get_tradeable_symbols(limit: Optional[int] = None) -> List[str]:
    """Get all symbols that have price data."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        query = "SELECT DISTINCT symbol FROM price_daily ORDER BY symbol"
        if limit:
            query += f" LIMIT {limit}"
        cur.execute(query)
        symbols = [row[0] for row in cur.fetchall()]
        return symbols
    finally:
        conn.close()


def fetch_metrics_from_yfinance(symbol: str) -> Optional[Dict]:
    """Fetch value metrics from yfinance."""
    try:
        tick = yf.Ticker(symbol)
        info = tick.info

        # Extract metrics
        market_cap = info.get('marketCap')
        pe_ratio = info.get('trailingPE')
        pb_ratio = info.get('priceToBook')
        ps_ratio = info.get('priceToSalesTrailing12Months')
        dividend_yield = info.get('dividendYield')

        return {
            'symbol': symbol,
            'market_cap': float(market_cap) if market_cap else None,
            'pe_ratio': float(pe_ratio) if pe_ratio and pe_ratio > 0 else None,
            'pb_ratio': float(pb_ratio) if pb_ratio and pb_ratio > 0 else None,
            'ps_ratio': float(ps_ratio) if ps_ratio and ps_ratio > 0 else None,
            'peg_ratio': None,  # Not available from yfinance
            'dividend_yield': float(dividend_yield) if dividend_yield else None,
            'fcf_yield': None,  # Not available from yfinance
        }
    except Exception as e:
        logger.debug(f"Error fetching {symbol}: {e}")
        return None


def ensure_value_metrics_record(conn, symbol: str):
    """Ensure a record exists in value_metrics for the symbol."""
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO value_metrics (symbol, created_at)
            VALUES (%s, NOW())
            ON CONFLICT (symbol) DO NOTHING
        """, (symbol,))
        conn.commit()
    except Exception as e:
        logger.warning(f"Could not ensure record for {symbol}: {e}")


def update_value_metrics(metrics_list: List[Dict]):
    """Update value_metrics with fetched data."""
    if not metrics_list:
        return 0

    conn = get_db_conn()
    try:
        cur = conn.cursor()

        for m in metrics_list:
            try:
                # First ensure record exists
                ensure_value_metrics_record(conn, m['symbol'])

                # Update with new data
                cur.execute("""
                    UPDATE value_metrics
                    SET pe_ratio = %s,
                        pb_ratio = %s,
                        ps_ratio = %s,
                        dividend_yield = %s,
                        updated_at = NOW()
                    WHERE symbol = %s
                """, (
                    m['pe_ratio'],
                    m['pb_ratio'],
                    m['ps_ratio'],
                    m['dividend_yield'],
                    m['symbol']
                ))

            except Exception as e:
                logger.warning(f"Failed to update {m['symbol']}: {e}")

        conn.commit()
        logger.info(f"Updated {cur.rowcount} symbols in value_metrics")
        return cur.rowcount

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Load value metrics from yfinance")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols (e.g. SPY,AAPL)")
    parser.add_argument("--limit", type=int, help="Load only first N symbols")
    parser.add_argument("--parallelism", type=int, default=8, help="Parallel workers")
    args = parser.parse_args()

    # Get symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_tradeable_symbols(limit=args.limit)

    logger.info(f"Loading value metrics for {len(symbols)} symbols")

    # Fetch in parallel
    metrics_list = []
    with ThreadPoolExecutor(max_workers=args.parallelism) as executor:
        futures = {executor.submit(fetch_metrics_from_yfinance, sym): sym for sym in symbols}
        completed = 0

        for future in as_completed(futures):
            completed += 1
            symbol = futures[future]

            try:
                result = future.result()
                if result:
                    metrics_list.append(result)
            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")

            if completed % 100 == 0:
                logger.info(f"Progress: {completed}/{len(symbols)} symbols fetched")

    logger.info(f"Successfully fetched metrics for {len(metrics_list)} symbols")

    # Update database
    if metrics_list:
        updated = update_value_metrics(metrics_list)
        logger.info(f"Value metrics load complete: {updated} symbols updated")
        return 0
    else:
        logger.warning("No metrics were fetched")
        return 1


if __name__ == '__main__':
    sys.exit(main())
