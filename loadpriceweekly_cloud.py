#!/usr/bin/env python3
"""
Cloud-Native Price Weekly Loader - AWS Best Practices
Uses S3 staging + PostgreSQL COPY FROM S3 for 1000x faster bulk loading
"""

import sys
import time
import logging
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from datetime import datetime

import psycopg2
import boto3
import yfinance as yf
import pandas as pd
import requests

from s3_bulk_insert import S3BulkInsert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_config():
    """Get RDS config from Secrets Manager (AWS best practice)"""
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
                "connect_timeout": 10
            }
        except Exception as e:
            logging.warning(f"Secrets Manager failed: {e}, falling back to env vars")

    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks"),
        "connect_timeout": 10
    }

def get_rds_s3_role():
    return os.environ.get(
        "RDS_S3_ROLE_ARN",
        "arn:aws:iam::626216981288:role/RDSBulkInsertRole"
    )

def load_symbol_data(symbol: str) -> List[tuple]:
    """Fetch weekly price data for one symbol"""
    try:
        ticker = yf.Ticker(symbol.replace(".", "-").upper())
        hist = ticker.history(period="max", interval="1wk")

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

        logging.debug(f"[OK] {symbol}: {len(rows)} weekly rows")
        return rows

    except Exception as e:
        logging.error(f"Error loading {symbol}: {e}")
        return []

def main():
    logging.info("Starting loadpriceweekly_cloud (PARALLEL + S3 BULK)")
    logging.info("Expected time: 5-20 minutes (vs 30-60 minutes with standard inserts)")

    db_config = get_db_config()
    rds_role = get_rds_s3_role()
    s3_bucket = os.environ.get("S3_STAGING_BUCKET", "stocks-app-data")

    # Connect to get symbols
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
    logging.info(f"Loading weekly prices for {total_symbols} stocks...")

    # Parallel fetch + bulk S3 load
    all_rows = []
    successful = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_symbol = {
            executor.submit(load_symbol_data, symbol): symbol
            for symbol in symbols
        }

        completed = 0
        start_time = time.time()

        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            completed += 1

            try:
                rows = future.result()
                if rows:
                    all_rows.extend(rows)
                    successful += 1
                else:
                    failed += 1

                if completed % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (total_symbols - completed) / rate if rate > 0 else 0
                    logging.info(
                        f"Progress: {completed}/{total_symbols} "
                        f"({rate:.1f}/sec, ~{remaining:.0f}s remaining, {len(all_rows)} rows)"
                    )

            except Exception as e:
                failed += 1
                logging.error(f"Error with {symbol}: {e}")

    # Bulk insert all rows via S3 in one operation
    if all_rows:
        try:
            logging.info(f"Bulk inserting {len(all_rows)} rows via S3...")
            bulk_inserter = S3BulkInsert(s3_bucket, db_config)
            columns = ["symbol", "date", "open", "high", "low", "close", "volume", "updated_at"]
            inserted = bulk_inserter.insert_bulk("price_weekly", columns, all_rows, rds_role)

            elapsed = time.time() - start_time
            logging.info(
                f"[OK] Completed: {inserted} rows inserted, "
                f"{successful} successful, {failed} failed "
                f"in {elapsed:.1f}s ({elapsed/60:.1f}m)"
            )
            return True

        except Exception as e:
            logging.error(f"Bulk insert failed: {e}")
            return False
    else:
        logging.warning("No data to insert")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
