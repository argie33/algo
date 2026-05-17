#!/usr/bin/env python3
"""
Fix value_metrics by fetching from yfinance.
This is a one-time script to populate PE, PB, PS ratios from yfinance.
"""
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Load environment and add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
env_file = Path(__file__).parent.parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

import psycopg2
import yfinance as yf

s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from config.credential_helper import get_db_password

def get_db_conn():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=get_db_password(),
        database=os.getenv('DB_NAME', 'stocks'),
    )

def get_symbols_with_prices() -> list:
    """Get all symbols that have price data."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT symbol FROM price_daily ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]
        return symbols
    finally:
        conn.close()

def fetch_metrics_from_yfinance(symbol: str) -> Optional[Dict]:
    """Fetch value metrics from yfinance for a single symbol."""
    try:
        tick = yf.Ticker(symbol)
        info = tick.info

        # Extract metrics (yfinance may return None if not available)
        market_cap = info.get('marketCap')
        pe_ratio = info.get('trailingPE')
        pb_ratio = info.get('priceToBook')
        ps_ratio = info.get('priceToSalesTrailing12Months')
        dividend_yield = info.get('dividendYield')

        # Only return if we got at least PE or market cap
        if not pe_ratio and not market_cap:
            return None

        return {
            'symbol': symbol,
            'market_cap': float(market_cap) if market_cap else None,
            'pe_ratio': float(pe_ratio) if pe_ratio else None,
            'pb_ratio': float(pb_ratio) if pb_ratio else None,
            'ps_ratio': float(ps_ratio) if ps_ratio else None,
            'dividend_yield': float(dividend_yield) if dividend_yield else None,
        }
    except Exception as e:
        logger.debug(f"Error fetching metrics for {symbol}: {e}")
        return None

def update_value_metrics(metrics_list: list):
    """Update value_metrics table with fetched data."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()

        for m in metrics_list:
            if not m:
                continue

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

        conn.commit()
        logger.info(f"Updated {cur.rowcount} symbols in value_metrics")
    finally:
        conn.close()

def main():
    logger.info("Starting value_metrics fix from yfinance")

    # Get all symbols with price data
    symbols = get_symbols_with_prices()
    logger.info(f"Found {len(symbols)} symbols with price data")

    # Fetch metrics in parallel
    metrics_list = []
    with ThreadPoolExecutor(max_workers=8) as executor:
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
                logger.info(f"Progress: {completed}/{len(symbols)} symbols")

    logger.info(f"Successfully fetched metrics for {len(metrics_list)} symbols")

    # Update database
    if metrics_list:
        update_value_metrics(metrics_list)
        logger.info("Value metrics update complete")
    else:
        logger.warning("No metrics were fetched")
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(main())
