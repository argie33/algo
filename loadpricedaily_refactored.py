#!/usr/bin/env python3
"""
Cloud-Native Price Daily Loader - CLEAN VERSION using DatabaseHelper
No S3 complexity visible. Just fetch data and insert.
"""

import sys
import time
import logging
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import psycopg2
import boto3
import yfinance as yf
import pandas as pd

from db_helper import DatabaseHelper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)


def get_db_config():
    """Get RDS config from Secrets Manager or env vars"""
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        try:
            secret = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )
            creds = json.loads(secret["SecretString"])
            return {
                "host": creds["host"],
                "port": int(creds.get("port", 5432)),
                "user": creds["username"],
                "password": creds["password"],
                "dbname": creds["dbname"],
            }
        except Exception as e:
            logging.warning(f"Secrets Manager failed: {e}, using env vars")

    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks"),
    }


def load_symbol_data(symbol: str):
    """Fetch daily price data for one symbol"""
    try:
        ticker = yf.Ticker(symbol.replace(".", "-").upper())
        hist = ticker.history(period="max")

        if hist.empty:
            return []

        rows = []
        for date, row in hist.iterrows():
            rows.append((
                symbol,
                date.date(),
                float(row["Open"]) if pd.notna(row["Open"]) else None,
                float(row["High"]) if pd.notna(row["High"]) else None,
                float(row["Low"]) if pd.notna(row["Low"]) else None,
                float(row["Close"]) if pd.notna(row["Close"]) else None,
                int(row["Volume"]) if pd.notna(row["Volume"]) else None,
                datetime.now()
            ))

        return rows
    except Exception as e:
        logging.error(f"Error loading {symbol}: {e}")
        return []


def main():
    logging.info("Starting loadpricedaily (Auto S3 or Standard Insert)")

    db_config = get_db_config()

    # Get symbols
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to fetch symbols: {e}")
        return False

    total_symbols = len(symbols)
    logging.info(f"Loading price data for {total_symbols} stocks...")

    all_rows = []
    start_time = time.time()

    # Parallel fetch (same as before)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(load_symbol_data, sym): sym for sym in symbols}

        for future in as_completed(futures):
            try:
                rows = future.result()
                all_rows.extend(rows)
            except Exception as e:
                logging.error(f"Task error: {e}")

    logging.info(f"Fetched {len(all_rows)} total rows in {time.time()-start_time:.1f}s")

    # NOW THE MAGIC: Single simple insert call
    # DatabaseHelper automatically decides: S3 bulk or standard?
    if all_rows:
        db = DatabaseHelper(db_config)
        columns = ["symbol", "date", "open", "high", "low", "close", "volume", "updated_at"]

        # That's it! No S3 config, no role ARN, no complexity
        inserted = db.insert('price_daily', columns, all_rows)
        db.close()

        elapsed = time.time() - start_time
        logging.info(f"✅ Completed: {inserted} rows in {elapsed:.1f}s ({inserted/elapsed:.0f} rows/sec)")
        return True
    else:
        logging.warning("No data to load")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
