#!/usr/bin/env python3
# ETF Daily Price Data Loader - fetches OHLCV data for ETFs only
import sys
import time
import logging
import json
import os
import gc
import resource
import math
import argparse

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import pandas as pd
import yfinance as yf

# Script metadata & logging setup
SCRIPT_NAME = "loadetfpricedaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

MAX_BATCH_RETRIES = 3
RETRY_DELAY = 0.2

PRICE_COLUMNS = [
    "date","open","high","low","close",
    "adj_close","volume","dividends","stock_splits"
]
COL_LIST = ", ".join(["symbol"] + PRICE_COLUMNS)

def get_db_config():
    """Get database configuration from AWS Secrets Manager or environment variables.

    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager") \
                             .get_secret_value(SecretId=db_secret_arn)["SecretString"]
            sec = json.loads(secret_str)
            logging.info("Using AWS Secrets Manager for database config")
            return {
                "host":   sec["host"],
                "port":   int(sec.get("port", 5432)),
                "user":   sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")

    # Fall back to environment variables
    logging.info("Using environment variables for database config")
    return {
        "host":   os.environ.get("DB_HOST", "localhost"),
        "port":   int(os.environ.get("DB_PORT", 5432)),
        "user":   os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

def load_prices(table_name, symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading {table_name}: {total} symbols")
    inserted, failed = 0, []
    CHUNK_SIZE, PAUSE = 1, 2.5  # Single symbol, 3.5s pause to avoid rate limits
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    if total == 0:
        logging.info(f"No symbols to load for {table_name}")
        return 0, 0, []

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').upper() for s in batch]
        mapping = dict(zip(yq_batch, batch))

        for attempt in range(1, MAX_BATCH_RETRIES+1):
            logging.info(f"{table_name} – batch {batch_idx+1}/{batches}, attempt {attempt}")
            log_mem(f"{table_name} batch {batch_idx+1} start")
            try:
                df = yf.download(
                    tickers=yq_batch,
                    period=DATA_PERIOD,
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=False,
                    actions=True,
                    threads=True,
                    progress=False
                )
                logging.info(f"Downloaded: {df.shape if hasattr(df, 'shape') else type(df)}")
                break
            except Exception as e:
                logging.warning(f"Download failed (attempt {attempt}/{MAX_BATCH_RETRIES}): {e}")
                time.sleep(RETRY_DELAY)
                if attempt == MAX_BATCH_RETRIES:
                    df = None
        else:
            df = None

        if df is None:
            logging.info(f"Attempting per-symbol download for batch {batch_idx+1}")
            per_symbol_results = {}
            for orig_sym in batch:
                try:
                    single_df = yf.download(orig_sym, period=DATA_PERIOD, interval="1d", auto_adjust=False, actions=True, progress=False)
                    if not single_df.empty:
                        single_df.columns = [col.lower() for col in single_df.columns]
                        per_symbol_results[orig_sym] = single_df
                    else:
                        logging.warning(f"{orig_sym}: no data")
                        failed.append(orig_sym)
                except Exception as e:
                    logging.warning(f"{orig_sym}: error: {e}")
                    failed.append(orig_sym)
            if per_symbol_results:
                df = per_symbol_results
            else:
                logging.error(f"Batch {batch_idx+1} failed completely")
                failed += batch
                continue

        log_mem(f"{table_name} after download")
        cur.execute("SELECT 1;")

        gc.disable()
        try:
            for yq_sym, orig_sym in mapping.items():
                try:
                    if len(yq_batch) > 1:
                        if yq_sym in df.columns.get_level_values(0):
                            sub = df[yq_sym]
                        else:
                            logging.warning(f"No data for {orig_sym}")
                            failed.append(orig_sym)
                            continue
                    else:
                        sub = df
                except (KeyError, AttributeError) as e:
                    logging.warning(f"No data for {orig_sym}: {e}")
                    failed.append(orig_sym)
                    continue

                sub = sub.sort_index()

                # Flatten MultiIndex columns if needed
                if isinstance(sub.columns, pd.MultiIndex):
                    # Extract the data column (last level) and make lowercase
                    sub.columns = [col[-1].lower() for col in sub.columns]
                else:
                    # Regular columns - just lowercase
                    sub.columns = [str(col).lower() for col in sub.columns]

                if "open" not in sub.columns:
                    logging.warning(f"No 'open' column for {orig_sym} - have: {list(sub.columns)}")
                    failed.append(orig_sym)
                    continue

                sub = sub[sub["open"].notna()]
                if sub.empty:
                    logging.warning(f"No valid rows for {orig_sym}")
                    failed.append(orig_sym)
                    continue

                rows = []
                for idx, row in sub.iterrows():
                    rows.append([
                        orig_sym,
                        idx.date(),
                        None if math.isnan(row["open"])      else float(row["open"]),
                        None if math.isnan(row["high"])      else float(row["high"]),
                        None if math.isnan(row["low"])       else float(row["low"]),
                        None if math.isnan(row["close"])     else float(row["close"]),
                        None if math.isnan(row.get("adj close", row["close"])) else float(row.get("adj close", row["close"])),
                        None if math.isnan(row["volume"])    else int(row["volume"]),
                        0.0  if ("dividends" not in row or math.isnan(row["dividends"])) else float(row["dividends"]),
                        0.0  if ("stock splits" not in row or math.isnan(row["stock splits"])) else float(row["stock splits"])
                    ])

                if not rows:
                    logging.warning(f"{orig_sym}: no rows after cleaning")
                    failed.append(orig_sym)
                    continue

                sql = f"INSERT INTO {table_name} ({COL_LIST}) VALUES %s"
                execute_values(cur, sql, rows)
                conn.commit()
                inserted += len(rows)
                logging.info(f"{orig_sym}: inserted {len(rows)} rows")
        finally:
            gc.enable()

        del df, batch, yq_batch, mapping
        gc.collect()
        log_mem(f"{table_name} batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, inserted, failed

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Load daily price data for ETFs only')
    parser.add_argument('--historical', action='store_true', help='Load full historical data (period="max")')
    parser.add_argument('--incremental', action='store_true', help='Load recent data only (period="3mo")')
    args = parser.parse_args()

    if args.historical:
        DATA_PERIOD = "max"
        logging.info("HISTORICAL mode - full data")
    elif args.incremental:
        DATA_PERIOD = "3mo"
        logging.info("INCREMENTAL mode - 3 months")
    else:
        DATA_PERIOD = "max"
        logging.info("DEFAULT mode - full data")

    log_mem("startup")

    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"],
        connect_timeout=30,
        options='-c statement_timeout=600000'
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    logging.info("Creating etf_price_daily table…")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS etf_price_daily (
            id           SERIAL PRIMARY KEY,
            symbol       VARCHAR(10) NOT NULL,
            date         DATE         NOT NULL,
            open         DOUBLE PRECISION,
            high         DOUBLE PRECISION,
            low          DOUBLE PRECISION,
            close        DOUBLE PRECISION,
            adj_close    DOUBLE PRECISION,
            volume       BIGINT,
            dividends    DOUBLE PRECISION,
            stock_splits DOUBLE PRECISION,
            fetched_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_etf_price_daily_symbol ON etf_price_daily(symbol);")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_etf_price_daily_symbol_date ON etf_price_daily(symbol, date);")
    conn.commit()

    # Load ETF symbols from etf_symbols table
    cur.execute("SELECT symbol FROM etf_symbols;")
    all_etf_syms = [r["symbol"] for r in cur.fetchall()]

    # Get ETF symbols already in table
    cur.execute("SELECT DISTINCT symbol FROM etf_price_daily;")
    loaded_etf_syms = {r["symbol"] for r in cur.fetchall()}

    # Filter to only missing symbols
    etf_syms = [s for s in all_etf_syms if s not in loaded_etf_syms]
    logging.info(f"Total ETFs: {len(all_etf_syms)}, loaded: {len(loaded_etf_syms)}, remaining: {len(etf_syms)}")

    total, inserted, failed = load_prices("etf_price_daily", etf_syms, cur, conn)

    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"ETFs — total: {total}, inserted: {inserted}, failed: {len(failed)}")

    cur.close()
    conn.close()
    logging.info("Done.")
