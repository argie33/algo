#!/usr/bin/env python3
"""
Load Market Indices Data Script

Loads historical and current price data for major US market indices:
- S&P 500 (^GSPC)
- NASDAQ Composite (^IXIC)
- Dow Jones Industrial Average (^DJI)
- Russell 2000 (^RUT)

Data Source: yfinance
"""

import sys
import os
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict

import psycopg2
from psycopg2.extras import RealDictCursor
import yfinance as yf
import pandas as pd

# Script configuration
SCRIPT_NAME = "loadmarketindices.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Market indices to load
MARKET_INDICES = {
    '^GSPC': 'S&P 500',
    '^IXIC': 'NASDAQ Composite',
    '^DJI': 'Dow Jones Industrial Average',
    '^RUT': 'Russell 2000'
}

def get_db_config() -> Dict:
    """Get database configuration from AWS Secrets Manager.

    REQUIRES AWS_REGION and DB_SECRET_ARN environment variables to be set.
    No fallbacks - fails loudly if AWS is not configured.
    """
    import boto3
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if not aws_region:
        raise EnvironmentError(
            "FATAL: AWS_REGION not set. Real data requires AWS configuration."
        )
    if not db_secret_arn:
        raise EnvironmentError(
            "FATAL: DB_SECRET_ARN not set. Real data requires AWS Secrets Manager configuration."
        )

    try:
        secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
            SecretId=db_secret_arn
        )["SecretString"]
        sec = json.loads(secret_str)
        logging.info(f"Loaded real database credentials from AWS Secrets Manager: {db_secret_arn}")
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception as e:
        raise EnvironmentError(
            f"FATAL: Cannot load database credentials from AWS Secrets Manager ({db_secret_arn}). "
            f"Error: {e.__class__.__name__}: {str(e)[:200]}\n"
            f"Ensure AWS credentials are configured and Secrets Manager is accessible.\n"
            f"Real data requires proper AWS setup - no fallbacks allowed."
        )

def safe_float(value, default=None):
    """Convert to float safely"""
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def load_index_data(symbol: str, name: str, period: str = "5y") -> Optional[int]:
    """
    Load historical price data for a market index

    Args:
        symbol: Ticker symbol (e.g., '^GSPC')
        name: Human readable name
        period: Data period to fetch

    Returns:
        Number of records inserted/updated
    """
    try:
        logging.info(f"Fetching {name} ({symbol}) data...")

        # Fetch data from yfinance
        yf_symbol = symbol.replace('^', '').upper()
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty:
            logging.warning(f"No data available for {symbol}")
            return 0

        logging.info(f"  Downloaded {len(hist)} trading days of data")

        # Connect to database
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Insert historical data
        inserted = 0
        for idx, row in hist.iterrows():
            date_val = idx.date() if hasattr(idx, 'date') else idx

            try:
                cur.execute("""
                    INSERT INTO price_daily
                    (symbol, date, open, high, low, close, adj_close, volume, fetched_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        adj_close = EXCLUDED.adj_close,
                        volume = EXCLUDED.volume,
                        fetched_at = CURRENT_TIMESTAMP
                """, (
                    symbol,
                    date_val,
                    safe_float(row.get('Open')),
                    safe_float(row.get('High')),
                    safe_float(row.get('Low')),
                    safe_float(row.get('Close')),
                    safe_float(row.get('Adj Close')),
                    int(row.get('Volume')) if row.get('Volume') and row.get('Volume') > 0 else None
                ))
                inserted += 1

            except Exception as e:
                logging.error(f"Error inserting {symbol} on {date_val}: {e}")
                conn.rollback()
                continue

        conn.commit()
        cur.close()
        conn.close()

        logging.info(f"  ✅ Inserted/updated {inserted} records for {symbol}")
        return inserted

    except Exception as e:
        logging.error(f"Error loading data for {symbol}: {e}")
        return 0

def main():
    logging.info("=" * 80)
    logging.info("MARKET INDICES DATA LOADER")
    logging.info("=" * 80)

    total_inserted = 0

    for symbol, name in MARKET_INDICES.items():
        count = load_index_data(symbol, name)
        total_inserted += count

    logging.info("\n" + "=" * 80)
    logging.info("MARKET INDICES LOADING COMPLETE")
    logging.info("=" * 80)
    logging.info(f"Total records loaded: {total_inserted}")
    logging.info("=" * 80)

if __name__ == "__main__":
    main()
