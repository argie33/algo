#!/usr/bin/env python3
"""
Benchmark & Market Index Data Loader
Fetches benchmark indices (SPY, QQQ, IWM, etc.) for Beta/Correlation calculations
Uses yfinance for reliable market data access
"""

import sys
import logging
import os
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'stocks')

# Benchmark symbols to load
BENCHMARK_SYMBOLS = ['SPY', 'QQQ', 'IWM', 'DIA', 'VTI']

def get_db_connection():
    """Create PostgreSQL database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        logger.info(f"✅ Connected to database: {DB_NAME}")
        return conn
    except psycopg2.Error as e:
        logger.error(f"❌ Database connection failed: {e}")
        sys.exit(1)

def fetch_benchmark_data(symbol, lookback_days=365):
    """Fetch benchmark historical data from yfinance"""
    try:
        logger.info(f"📊 Fetching {symbol} data from yfinance (last {lookback_days} days)...")

        hist = yf.Ticker(symbol.replace(".", "-").replace("$", "-").upper()).history(period=f"{lookback_days}d")

        if hist.empty:
            logger.warning(f"⚠️  No historical data for {symbol}")
            return None

        logger.info(f"✅ Retrieved {len(hist)} {symbol} bars from yfinance")
        return hist
    except Exception as e:
        logger.error(f"❌ Failed to fetch {symbol} data: {e}")
        return None

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

        # Delete existing data for this symbol first
        if records:
            start_date = records[0][1]
            end_date = records[-1][1]
            cur.execute(
                f"DELETE FROM price_daily WHERE symbol = %s AND date BETWEEN %s AND %s",
                (symbol, start_date, end_date)
            )
            deleted_count = cur.rowcount
            logger.info(f"Cleared {deleted_count} existing {symbol} records")

        # Insert new data (already deleted old records above)
        query = """
            INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, dividends, stock_splits)
            VALUES %s
        """

        execute_values(cur, query, records)
        conn.commit()

        logger.info(f"✅ Inserted/updated {len(records)} {symbol} price records")
        cur.close()
        return len(records)
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"❌ Database error inserting {symbol} data: {e}")
        return 0

def main():
    """Main execution"""
    logger.info("🚀 Starting Benchmark Data Loader")
    logger.info(f"📊 Loading benchmarks: {', '.join(BENCHMARK_SYMBOLS)}")

    # Connect to database
    conn = get_db_connection()

    total_inserted = 0
    for symbol in BENCHMARK_SYMBOLS:
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
