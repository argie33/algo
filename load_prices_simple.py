#!/usr/bin/env python3
"""
Simple price loader using yfinance
Windows-compatible (no resource module needed)
"""
import sys
import os
from pathlib import Path
import logging
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("load_prices_simple")

# Load environment variables
env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

# Database configuration
db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', 5432),
    'user': os.getenv('DB_USER', 'stocks'),
    'password': os.getenv('DB_PASSWORD', 'bed0elAn'),
    'database': os.getenv('DB_NAME', 'stocks'),
}

def get_symbols(conn):
    """Get list of stock symbols from database"""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM stock_symbols LIMIT 50")
            symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"Loaded {len(symbols)} symbols from database")
        return symbols
    except Exception as e:
        logger.error(f"Error fetching symbols: {e}")
        return []

def create_price_table(conn):
    """Create price_daily table if it doesn't exist"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS price_daily (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    date DATE NOT NULL,
                    open FLOAT,
                    high FLOAT,
                    low FLOAT,
                    close FLOAT NOT NULL,
                    volume BIGINT,
                    adj_close FLOAT,
                    UNIQUE(symbol, date)
                );
                CREATE INDEX IF NOT EXISTS idx_price_daily_symbol ON price_daily(symbol);
                CREATE INDEX IF NOT EXISTS idx_price_daily_date ON price_daily(date);
            """)
            conn.commit()
            logger.info("Price table ensured")
    except Exception as e:
        logger.error(f"Error creating table: {e}")
        conn.rollback()

def load_prices_for_symbol(conn, symbol, days=30):
    """Load recent prices for a symbol"""
    try:
        logger.info(f"Fetching prices for {symbol}...")

        # Download data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)

        if df.empty:
            logger.warning(f"No data found for {symbol}")
            return 0

        # Reset index to make date a column
        df.reset_index(inplace=True)
        df['symbol'] = symbol
        df['date'] = df['Date'].dt.date

        # Prepare data for insertion
        records = []
        for _, row in df.iterrows():
            records.append((
                symbol,
                row['date'],
                float(row.get('Open', 0)) if pd.notna(row.get('Open')) else None,
                float(row.get('High', 0)) if pd.notna(row.get('High')) else None,
                float(row.get('Low', 0)) if pd.notna(row.get('Low')) else None,
                float(row['Close']),
                int(row['Volume']) if pd.notna(row['Volume']) else None,
                float(row.get('Adj Close', 0)) if pd.notna(row.get('Adj Close')) else None,
            ))

        # Insert into database
        with conn.cursor() as cur:
            try:
                execute_values(
                    cur,
                    "INSERT INTO price_daily (symbol, date, open, high, low, close, volume, adj_close) VALUES %s ON CONFLICT (symbol, date) DO NOTHING",
                    records,
                    page_size=1000
                )
                conn.commit()
                logger.info(f"✓ Inserted {len(records)} price records for {symbol}")
                return len(records)
            except Exception as e:
                logger.error(f"Error inserting for {symbol}: {e}")
                conn.rollback()
                return 0

    except Exception as e:
        logger.error(f"Error fetching prices for {symbol}: {e}")
        return 0

def main():
    """Main function"""
    try:
        conn = psycopg2.connect(**db_config)
        logger.info("Connected to database")

        # Create table
        create_price_table(conn)

        # Get symbols
        symbols = get_symbols(conn)
        if not symbols:
            logger.error("No symbols found in database")
            return

        # Load prices for each symbol
        total_inserted = 0
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"[{i}/{len(symbols)}] Processing {symbol}...")
            inserted = load_prices_for_symbol(conn, symbol, days=30)
            total_inserted += inserted

        logger.info(f"\n Complete! Inserted {total_inserted} total price records")

        # Show sample data
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM price_daily")
            count = cur.fetchone()[0]
            logger.info(f"Total prices in database: {count}")

            cur.execute("SELECT DISTINCT symbol FROM price_daily LIMIT 5")
            symbols_with_data = [row[0] for row in cur.fetchall()]
            logger.info(f"Sample symbols with data: {symbols_with_data}")

        conn.close()

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    import pandas as pd
    main()
