#!/usr/bin/env python3
"""
Monthly Price Loader - Cloud-Native with Smart Incremental Loading
Uses DatabaseHelper for automatic S3 or standard inserts
"""

import sys
import time
import logging
import os
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import List, Tuple

import psycopg2
import boto3
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv

from db_helper import DatabaseHelper

# Load environment variables
env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

PRICE_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "adj_close", "volume", "dividends", "stock_splits"]

def get_db_config() -> dict:
    """Get database config from Secrets Manager or env vars"""
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if aws_region and db_secret_arn:
        try:
            secret = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )
            creds = json.loads(secret["SecretString"])
            logger.info("Loaded credentials from AWS Secrets Manager")
            return {
                "host": creds["host"],
                "port": int(creds.get("port", 5432)),
                "user": creds["username"],
                "password": creds["password"],
                "dbname": creds["dbname"]
            }
        except Exception as e:
            logger.warning(f"Secrets Manager failed: {e}, using env vars")

    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

def fetch_symbol_data(symbol: str, period: str = "max") -> List[Tuple]:
    """Fetch monthly price data for one symbol"""
    try:
        ticker = yf.Ticker(symbol.replace(".", "-").upper())
        hist = ticker.history(period=period, interval="1mo")

        if hist.empty:
            return []

        rows = []
        for idx, row in hist.iterrows():
            try:
                volume = None if pd.isna(row.get("Volume")) else int(row.get("Volume", 0))
                if volume is None or volume == 0:
                    continue

                rows.append((
                    symbol,
                    idx.date(),
                    float(row["Open"]) if pd.notna(row["Open"]) else None,
                    float(row["High"]) if pd.notna(row["High"]) else None,
                    float(row["Low"]) if pd.notna(row["Low"]) else None,
                    float(row["Close"]) if pd.notna(row["Close"]) else None,
                    float(row.get("Adj Close", row.get("Close"))) if pd.notna(row.get("Adj Close", row.get("Close"))) else None,
                    volume,
                    float(row.get("Dividends", 0.0)) if pd.notna(row.get("Dividends", 0.0)) else 0.0,
                    float(row.get("Stock Splits", 0.0)) if pd.notna(row.get("Stock Splits", 0.0)) else 0.0
                ))
            except Exception as e:
                logger.debug(f"{symbol} row parse error: {e}")
                continue

        logger.debug(f"✓ {symbol}: {len(rows)} rows")
        return rows

    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {e}")
        return []

def load_table(db: DatabaseHelper, table_name: str, symbols: List[str]) -> Tuple[int, int]:
    """Load monthly price data for all symbols. Returns (total_symbols, inserted_rows)"""
    if not symbols:
        logger.info(f"{table_name}: No symbols to load")
        return 0, 0

    logger.info(f"{table_name}: Loading {len(symbols)} symbols")
    all_rows = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_symbol_data, s, "3mo"): s for s in symbols}
        for future in as_completed(futures):
            try:
                rows = future.result()
                all_rows.extend(rows)
            except Exception as e:
                logger.error(f"Task error: {e}")

    if all_rows:
        inserted = db.insert(table_name, PRICE_COLUMNS, all_rows)
        logger.info(f"{table_name}: Inserted {inserted}/{len(all_rows)} rows")
        return len(symbols), inserted
    else:
        logger.warning(f"{table_name}: No data to insert")
        return len(symbols), 0

def main():
    logger.info("Starting loadpricemonthly (Cloud-Native)")

    db_config = get_db_config()

    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Ensure tables exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS price_monthly (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                date DATE NOT NULL,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                adj_close DOUBLE PRECISION,
                volume BIGINT,
                dividends DOUBLE PRECISION,
                stock_splits DOUBLE PRECISION,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_price_monthly_symbol ON price_monthly(symbol)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS etf_price_monthly (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                date DATE NOT NULL,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                adj_close DOUBLE PRECISION,
                volume BIGINT,
                dividends DOUBLE PRECISION,
                stock_splits DOUBLE PRECISION,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_etf_price_monthly_symbol ON etf_price_monthly(symbol)")

        conn.commit()

        # Load symbols
        cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
        stock_syms = [row[0] for row in cur.fetchall()]
        logger.info(f"Found {len(stock_syms)} stocks")

        try:
            cur.execute("SELECT symbol FROM etf_symbols ORDER BY symbol")
            etf_syms = [row[0] for row in cur.fetchall()]
            logger.info(f"Found {len(etf_syms)} ETFs")
        except psycopg2.errors.UndefinedTable:
            logger.warning("etf_symbols table not found - skipping ETFs")
            etf_syms = []

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return False

    db = DatabaseHelper(db_config)
    start_time = time.time()

    total_stocks, stocks_inserted = load_table(db, "price_monthly", stock_syms)
    total_etfs, etfs_inserted = load_table(db, "etf_price_monthly", etf_syms)

    db.close()

    elapsed = time.time() - start_time
    logger.info(f"✅ Completed in {elapsed:.1f}s")
    logger.info(f"Stocks: {total_stocks} total, {stocks_inserted} inserted")
    logger.info(f"ETFs: {total_etfs} total, {etfs_inserted} inserted")

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
