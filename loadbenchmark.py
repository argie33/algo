#!/usr/bin/env python3
"""
Benchmark & Market Index Data Loader
Fetches benchmark indices (SPY, QQQ, IWM, etc.) for Beta/Correlation calculations
Uses yfinance for reliable market data access
"""

import sys
import logging
import os
import time
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from db_helper import get_db_connection
from yfinance_helper import fetch_ticker_history

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

SCRIPT_NAME = "loadbenchmark.py"

# Benchmark symbols to load
BENCHMARK_SYMBOLS = ['SPY', 'QQQ', 'IWM', 'DIA', 'VTI']

def fetch_benchmark_data(symbol, lookback_days=365, max_retries=5):
    """Fetch benchmark historical data from yfinance with smart retry logic"""
    # Clean symbol
    clean_symbol = symbol.replace(".", "-").replace("$", "-").upper()

    # Convert days to period string
    period_map = {
        365: "1y",
        730: "2y",
        1095: "3y",
        1825: "5y",
    }
    period = period_map.get(lookback_days, "max")

    logger.info(f"📊 Fetching {symbol} data from yfinance (period: {period})...")

    # Use the yfinance helper with better rate limit handling
    hist = fetch_ticker_history(
        clean_symbol,
        period=period,
        max_retries=max_retries,
        min_rows=0
    )

    if hist is not None:
        logger.info(f"✅ Retrieved {len(hist)} {symbol} bars from yfinance")
    else:
        logger.warning(f"⚠️  No data retrieved for {symbol}")

    return hist

def insert_benchmark_data(conn, symbol, hist):
    """Insert benchmark bars into price_daily table"""
    if hist is None or hist.empty:
        logger.warning(f"⚠️  No {symbol} data to insert")
        return 0

    try:
        cur = conn.cursor()

        # Prepare data for insertion
        records = []
        for date, row in hist.iterrows():
            records.append((
                symbol,  # symbol
                date.date(),  # date
                float(row['Open']) if pd.notna(row['Open']) else None,  # open
                float(row['High']) if pd.notna(row['High']) else None,  # high
                float(row['Low']) if pd.notna(row['Low']) else None,    # low
                float(row['Close']) if pd.notna(row['Close']) else None,  # close
                None,  # adj_close
                int(row['Volume']) if pd.notna(row['Volume']) else 0,    # volume
                None,  # dividends
                None   # stock_splits
            ))

        # Insert with ON CONFLICT to upsert data
        if records:
            query = """
                INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, dividends, stock_splits)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    adj_close = EXCLUDED.adj_close,
                    volume = EXCLUDED.volume,
                    dividends = EXCLUDED.dividends,
                    stock_splits = EXCLUDED.stock_splits
            """

            execute_values(cur, query, records)
        conn.commit()

        logger.info(f"✅ Inserted/updated {len(records)} {symbol} price records")
        cur.close()
        return len(records)
    except psycopg2.Error as e:
        logger.error(f"❌ Database error inserting {symbol} data: {e}")
        # Don't rollback - let the loader continue with next symbol
        return 0

def main():
    """Main execution"""
    logger.info("🚀 Starting Benchmark Data Loader")
    logger.info(f"📊 Loading benchmarks: {', '.join(BENCHMARK_SYMBOLS)}")

    # Connect to database
    conn = get_db_connection(SCRIPT_NAME)
    if not conn:
        logger.error("❌ Failed to connect to database")
        sys.exit(1)

    total_inserted = 0
    for i, symbol in enumerate(BENCHMARK_SYMBOLS):
        # Add longer delay between benchmark fetches to avoid rate limiting
        if i > 0:
            delay = 15  # Increased from 5s to 15s for better rate limit handling
            logger.info(f"⏳ Waiting {delay}s before fetching next benchmark (rate limit avoidance)...")
            time.sleep(delay)

        # Fetch benchmark data from yfinance
        hist = fetch_benchmark_data(symbol, lookback_days=365)

        if hist is not None:
            # Insert into database
            inserted = insert_benchmark_data(conn, symbol, hist)
            total_inserted += inserted
        else:
            logger.warning(f"⚠️  Skipped {symbol} due to fetch failure")

    conn.close()

    if total_inserted > 0:
        logger.info(f"✅ Benchmark data loaded successfully ({total_inserted} total records)")
        logger.info("📊 Beta and Correlation calculations will now work")
        sys.exit(0)
    else:
        logger.error("❌ Failed to load benchmark data")
        sys.exit(1)

if __name__ == '__main__':
    main()
