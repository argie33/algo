#!/usr/bin/env python3
"""
Load Historical Index Data into Database
Well-Architected Best Practice: Store all data locally for efficient access

This script loads historical price data for major indices into the price_daily table.
Once loaded, all other scripts can query from the database instead of external APIs.

Author: Financial Dashboard System
Updated: 2025-01-16
"""

import logging
import os
import sys
from datetime import datetime

import pandas as pd
import psycopg2
import yfinance as yf
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def get_db_config():
    """Get database configuration"""
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "password"),
        "dbname": os.environ.get("DB_NAME", "stocks"),
    }


def load_index_historical_data(conn, cur, symbol: str, name: str, years: int = 2):
    """
    Load historical data for an index from yfinance into price_daily table

    Args:
        conn: Database connection
        cur: Database cursor
        symbol: Index symbol (e.g., ^GSPC)
        name: Index name (e.g., S&P 500)
        years: Number of years of historical data to load
    """
    try:
        logging.info(f"Loading historical data for {name} ({symbol})...")

        # Fetch data from yfinance (one-time load)
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=f"{years}y")

        if hist.empty:
            logging.warning(f"No historical data available for {symbol}")
            return 0

        logging.info(f"  Fetched {len(hist)} days of historical data")

        # Prepare data for insertion
        insert_data = []
        for date, row in hist.iterrows():
            insert_data.append((
                symbol,
                date.date(),
                float(row['Open']) if 'Open' in row and pd.notna(row['Open']) else None,
                float(row['High']) if 'High' in row and pd.notna(row['High']) else None,
                float(row['Low']) if 'Low' in row and pd.notna(row['Low']) else None,
                float(row['Close']) if 'Close' in row and pd.notna(row['Close']) else None,
                int(row['Volume']) if 'Volume' in row and pd.notna(row['Volume']) else 0,
            ))

        # First, delete existing data for this symbol to avoid duplicates
        cur.execute("DELETE FROM price_daily WHERE symbol = %s", (symbol,))

        # Insert into price_daily table
        insert_query = """
            INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
            VALUES %s
        """

        execute_values(cur, insert_query, insert_data)
        conn.commit()

        logging.info(f"  ✅ Inserted {len(insert_data)} days of data for {symbol}")
        return len(insert_data)

    except Exception as e:
        logging.error(f"Error loading data for {symbol}: {e}")
        conn.rollback()
        return 0


def main():
    """Main execution function"""
    logging.info("=" * 60)
    logging.info("Historical Index Data Loader")
    logging.info("Loading index data into price_daily table")
    logging.info("=" * 60)

    # Major indices to load
    major_indices = {
        "^GSPC": "S&P 500",
        "^IXIC": "NASDAQ Composite",
        "^DJI": "Dow Jones Industrial Average",
    }

    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
    )
    conn.autocommit = False
    cur = conn.cursor()

    # Load historical data for each index
    total_loaded = 0
    for symbol, name in major_indices.items():
        loaded = load_index_historical_data(conn, cur, symbol, name, years=2)
        total_loaded += loaded

    # Verify data was loaded
    logging.info("\n" + "=" * 60)
    logging.info("Verification - Data in price_daily table")
    logging.info("=" * 60)

    for symbol, name in major_indices.items():
        cur.execute(
            """
            SELECT COUNT(*) as count,
                   MIN(date) as oldest,
                   MAX(date) as newest
            FROM price_daily
            WHERE symbol = %s
            """,
            (symbol,),
        )
        result = cur.fetchone()
        if result and result[0] > 0:
            logging.info(
                f"{name} ({symbol}): {result[0]} days "
                f"({result[1]} to {result[2]})"
            )
        else:
            logging.warning(f"{name} ({symbol}): No data found")

    cur.close()
    conn.close()

    logging.info(f"\n✅ Historical index data loading complete!")
    logging.info(f"Total days loaded: {total_loaded}")
    logging.info("Data source: yfinance (one-time load)")
    logging.info("Future access: price_daily table (local database)")


if __name__ == "__main__":
    main()
