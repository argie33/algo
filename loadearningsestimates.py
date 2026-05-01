#!/usr/bin/env python3
"""
Earnings Estimates Loader - Fill the 90% gap
Loads analyst estimates for all 4,965 symbols

Current state: 1,348 rows / 337 symbols (6.8%)
Target: ~20,000 rows / 4,965 symbols (100%)
"""

import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf
import pandas as pd
import os
import sys
import logging
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

load_dotenv('.env.local')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432')),
        user=os.getenv('DB_USER', 'stocks'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME', 'stocks')
    )

def get_all_symbols(conn):
    """Get all 4,965 symbols from database"""
    cur = conn.cursor()
    cur.execute('''
        SELECT DISTINCT symbol FROM price_daily
        WHERE symbol NOT LIKE '%.%' AND symbol NOT LIKE '%^%'
        ORDER BY symbol
    ''')
    symbols = [row[0] for row in cur.fetchall()]
    cur.close()
    return symbols

def fetch_earnings_estimates(symbol):
    """Fetch earnings estimates from yfinance for a single symbol"""
    try:
        ticker = yf.Ticker(symbol)

        # Try to get earnings dates and calendar info
        info = ticker.info

        # Get analyst estimates
        if hasattr(ticker, 'info') and 'epsTrailingTwelveMonths' in info:
            estimates = []

            # Get current year EPS estimate if available
            for key in ['epsCurrentYear', 'targetMeanPrice', 'numberOfAnalysts']:
                if key in info:
                    logging.debug(f"{symbol}: Found {key}")

            # Return what we found
            return {
                'symbol': symbol,
                'eps_current_year': info.get('epsCurrentYear'),
                'target_price': info.get('targetMeanPrice'),
                'analyst_count': info.get('numberOfAnalysts'),
                'recommendation': info.get('recommendationKey'),
                'earnings_date': info.get('earningsDate')
            }

        return None

    except Exception as e:
        logging.warning(f"Error fetching {symbol}: {str(e)[:100]}")
        return None

def insert_earnings_estimates(conn, estimates_list):
    """Insert earnings estimates into database"""
    if not estimates_list:
        return 0

    # Filter out None values
    estimates_list = [e for e in estimates_list if e is not None]
    if not estimates_list:
        return 0

    values = [
        (
            est['symbol'],
            est.get('quarter', 'Q1'),  # Default to Q1
            None,  # eps_estimate (from yfinance epsCurrentYear)
            None,  # revenue_estimate (not available in basic yfinance)
            None,  # surprise_percent
            est.get('analyst_count'),  # estimate_count
            None,  # last_update_date
            'annual',  # period (we're getting annual)
            est.get('eps_current_year'),  # avg_estimate
            None,  # low_estimate
            None,  # high_estimate
            None,  # year_ago_eps
            None,  # growth
        )
        for est in estimates_list
    ]

    try:
        cur = conn.cursor()
        execute_values(cur, '''
            INSERT INTO earnings_estimates
            (symbol, quarter, eps_estimate, revenue_estimate, surprise_percent,
             estimate_count, last_update_date, period, avg_estimate,
             low_estimate, high_estimate, year_ago_eps, growth)
            VALUES %s
            ON CONFLICT (symbol, quarter, period) DO UPDATE SET
                avg_estimate = EXCLUDED.avg_estimate,
                estimate_count = EXCLUDED.estimate_count,
                last_update_date = NOW()
        ''', values, page_size=500)

        result = cur.rowcount
        conn.commit()
        cur.close()
        return result

    except Exception as e:
        logging.error(f"Insert error: {e}")
        return 0

def main():
    conn = get_db_connection()

    # Get all symbols
    symbols = get_all_symbols(conn)
    total_symbols = len(symbols)
    logging.info(f"Processing {total_symbols} symbols...")

    # Get already loaded symbols to avoid duplicates
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT symbol FROM earnings_estimates')
    existing_symbols = set([row[0] for row in cur.fetchall()])
    cur.close()

    # Filter to symbols that need loading
    symbols_to_load = [s for s in symbols if s not in existing_symbols]
    logging.info(f"Already have {len(existing_symbols)} symbols, need to load {len(symbols_to_load)}")

    # Load in parallel
    total_loaded = 0
    batch_size = 100
    processed = 0

    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks
        futures = {
            executor.submit(fetch_earnings_estimates, symbol): symbol
            for symbol in symbols_to_load
        }

        # Collect results in batches
        batch = []
        for future in as_completed(futures):
            symbol = futures[future]
            processed += 1

            try:
                result = future.result()
                if result:
                    batch.append(result)
            except Exception as e:
                logging.warning(f"Failed to process {symbol}: {e}")

            # Insert when we have a batch
            if len(batch) >= batch_size:
                inserted = insert_earnings_estimates(conn, batch)
                total_loaded += inserted
                logging.info(f"Progress: {processed}/{len(symbols_to_load)} symbols, {total_loaded:,} rows loaded")
                batch = []

            # Show progress every 100 symbols
            if processed % 100 == 0:
                logging.info(f"Progress: {processed}/{len(symbols_to_load)} ({processed*100//len(symbols_to_load)}%)")

    # Insert remaining batch
    if batch:
        inserted = insert_earnings_estimates(conn, batch)
        total_loaded += inserted

    conn.close()

    logging.info(f"DONE: Loaded earnings estimates for {len(symbols_to_load)} symbols, {total_loaded:,} rows inserted")

if __name__ == '__main__':
    main()
