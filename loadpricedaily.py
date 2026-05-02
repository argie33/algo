#!/usr/bin/env python3
# TRIGGER: 20260502_203400 - Phase A: Price loader test with S3 staging
"""
Daily Price Loader - Cloud-Native with Smart Incremental Loading
Uses DatabaseHelper for automatic S3 or standard inserts
Smart mode: queries max(date) per symbol, downloads only missing data

Phase A enabled: USE_S3_STAGING=true, Fargate Spot 80%, max-parallel=10
"""

import sys
import time
import logging
import os
import json
import gc
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta
from typing import List, Tuple, Dict

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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

SCRIPT_NAME = "loadpricedaily.py"
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
            logger.info(f"Loaded credentials from AWS Secrets Manager")
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
    """Fetch daily price data for one symbol (with timeout protection)
    Wave 1: Includes 30s timeout, batch optimization (1000 rows), progress logging"""
    try:
        ticker = yf.Ticker(symbol.replace(".", "-").upper())
        # Add timeout protection - yfinance has no native timeout, so we catch hangs
        hist = ticker.history(period=period, timeout=30)

        if hist.empty:
            return []

        rows = []
        for idx, row in hist.iterrows():
            try:
                volume = None if pd.isna(row.get("Volume")) else int(row.get("Volume", 0))
                # Skip zero-volume records (non-trading days)
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

def load_table(db: DatabaseHelper, table_name: str, symbols: List[str], use_smart: bool = True) -> Tuple[int, int]:
    """Load price data for all symbols. Returns (total_symbols, inserted_rows)"""
    if not symbols:
        logger.info(f"{table_name}: No symbols to load")
        return 0, 0

    logger.info(f"{table_name}: Loading {len(symbols)} symbols")
    all_rows = []
    failed = []

    # Smart incremental mode: only fetch missing data
    if use_smart:
        logger.info(f"{table_name}: Using smart incremental mode")
        conn = psycopg2.connect(**db.db_config)
        cur = conn.cursor()

        try:
            # Get max(date) for each symbol
            cur.execute(f"SELECT symbol, MAX(date) AS last_date FROM {table_name} WHERE symbol = ANY(%s) GROUP BY symbol", (symbols,))
            existing = {row[0]: row[1] for row in cur.fetchall()}
            logger.info(f"{table_name}: {len(existing)}/{len(symbols)} symbols already have data")

            today = date.today()
            need_full = [s for s in symbols if s not in existing]
            need_incr = [s for s in symbols if s in existing and existing[s] < today]

            logger.info(f"{table_name}: full={len(need_full)}, incremental={len(need_incr)}")

            # Fetch data for symbols needing full history
            processed = 0
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(fetch_symbol_data, s, "max"): s for s in need_full}
                for future in as_completed(futures):
                    try:
                        rows = future.result()
                        all_rows.extend(rows)
                        processed += 1
                        if processed % 50 == 0:
                            logger.info(f"{table_name}: Progress {processed}/{len(need_full)} symbols")
                    except Exception as e:
                        logger.error(f"Task error: {e}")

            # Fetch incremental data for existing symbols
            processed_incr = 0
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(fetch_symbol_data, s, "3mo"): s for s in need_incr}
                for future in as_completed(futures):
                    try:
                        rows = future.result()
                        all_rows.extend(rows)
                        processed_incr += 1
                        if processed_incr % 50 == 0:
                            logger.info(f"{table_name}: Incremental progress {processed_incr}/{len(need_incr)} symbols")
                    except Exception as e:
                        logger.error(f"Task error: {e}")

        finally:
            cur.close()
            conn.close()
    else:
        # Simple mode: parallel fetch for all symbols
        logger.info(f"{table_name}: Using standard parallel fetch mode (3 months)")
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
    logger.info("Starting loadpricedaily (Cloud-Native with Smart Incremental)")

    db_config = get_db_config()

    # Get database connection to fetch symbol lists
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Ensure tables exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS price_daily (
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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_price_daily_symbol ON price_daily(symbol)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS etf_price_daily (
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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_etf_price_daily_symbol ON etf_price_daily(symbol)")

        conn.commit()

        # Load stock symbols
        cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
        stock_syms = [row[0] for row in cur.fetchall()]
        logger.info(f"Found {len(stock_syms)} stocks")

        # Load ETF symbols
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

    # Load data using DatabaseHelper
    db = DatabaseHelper(db_config)

    start_time = time.time()

    total_stocks, stocks_inserted = load_table(db, "price_daily", stock_syms, use_smart=True)
    total_etfs, etfs_inserted = load_table(db, "etf_price_daily", etf_syms, use_smart=True)

    db.close()

    elapsed = time.time() - start_time
    logger.info(f"✅ Completed in {elapsed:.1f}s")
    logger.info(f"Stocks: {total_stocks} total, {stocks_inserted} inserted")
    logger.info(f"ETFs: {total_etfs} total, {etfs_inserted} inserted")

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
