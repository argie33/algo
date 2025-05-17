#!/usr/bin/env python3
import sys
import time
import logging
from datetime import datetime
import json
import os
import gc
import resource

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
import yfinance as yf

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadpricedaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Memory‐logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    mb = get_rss_mb()
    logging.info(f"[MEM] {stage}: {mb:.1f} MB RSS")

# -------------------------------
# Environment‐driven configuration
# -------------------------------
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]

def get_db_config():
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"]
    )

# -------------------------------
# Fetch helper: batch fetch + retry
# -------------------------------
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

def fetch_daily_data_batch(symbols, start_date, end_date):
    yf_syms = [s.replace('.', '-') for s in symbols]
    tickers_str = " ".join(yf_syms)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = yf.download(
                tickers=tickers_str,
                start=start_date,
                end=end_date,
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False
            )
            if raw is None or raw.empty:
                raise ValueError("Empty DataFrame returned")
            df_list = []
            for orig, yf_sym in zip(symbols, yf_syms):
                if isinstance(raw.columns, pd.MultiIndex):
                    if yf_sym not in raw.columns.levels[0]:
                        logging.warning(f"No data for {orig} in this batch")
                        continue
                    sub = raw[yf_sym].copy()
                else:
                    sub = raw.copy()
                sub = sub.reset_index().rename(columns={
                    'Date': 'date',
                    'Open': 'open',
                    'High': 'high',
                    'Low': 'low',
                    'Close': 'close',
                    'Volume': 'volume',
                    'Dividends': 'dividends',
                    'Stock Splits': 'stock_splits'
                })
                for col in ('dividends', 'stock_splits'):
                    if col not in sub.columns:
                        sub[col] = 0.0
                sub['symbol'] = orig
                df_list.append(sub)
            if not df_list:
                raise ValueError("No valid symbols data in batch")
            return pd.concat(df_list, ignore_index=True)
        except Exception as e:
            logging.error(f"[Batch fetch error] attempt {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    logging.error(f"Failed to fetch batch after {MAX_RETRIES} attempts.")
    return None

# -------------------------------
# Insert helper
# -------------------------------
def load_group(symbols, table_name, cursor):
    logging.info(f"Fetching batch of {len(symbols)} symbols into `{table_name}`")
    df = fetch_daily_data_batch(symbols, "1800-01-01", datetime.now().strftime("%Y-%m-%d"))
    if df is None or df.empty:
        logging.warning("Skipping batch: no data returned")
        return
    df_to_insert = df[[
        'symbol','date','open','high','low','close','volume','dividends','stock_splits'
    ]].where(pd.notnull(df), None)
    rows = list(df_to_insert.itertuples(index=False, name=None))
    sql = f"""
    INSERT INTO {table_name}
      (symbol, date, open, high, low, close, volume, dividends, stock_splits)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (symbol, date) DO NOTHING;
    """
    try:
        cursor.executemany(sql, rows)
        logging.info(f"Inserted {len(rows)} rows for {len(symbols)} symbols.")
    except Exception as e:
        logging.error(f"[DB error] batch insert into {table_name}: {e}")

# -------------------------------
# Batch processing orchestrator 
# -------------------------------
BATCH_SIZE = 10
PAUSE = 0.1  # seconds between batches

def process_in_batches(symbols, table_name, cursor):
    total = len(symbols)
    for start_idx in range(0, total, BATCH_SIZE):
        batch = symbols[start_idx:start_idx + BATCH_SIZE]
        batch_num = (start_idx // BATCH_SIZE) + 1
        logging.info(f"Starting batch {batch_num}: symbols {start_idx+1}-{start_idx+len(batch)} of {total}")
        log_mem(f"batch {batch_num} start")
        t0 = time.time()

        load_group(batch, table_name, cursor)

        # Teardown & pause
        gc.collect()
        duration = time.time() - t0
        logging.info(f"Batch {batch_num} took {duration:.1f}s")
        log_mem(f"batch {batch_num} end")
        time.sleep(PAUSE)

# -------------------------------
# Main execution
# -------------------------------
def main():
    t_start = time.time()
    log_mem("startup")
    logging.info(f"Starting {SCRIPT_NAME}")

    user, pwd, host, port, db = get_db_config()

    # Connect to PostgreSQL
    try:
        conn = psycopg2.connect(
            host=host, port=port,
            user=user, password=pwd,
            dbname=db
        )
        conn.autocommit = True
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        logging.info("Connected to PostgreSQL")
    except Exception as e:
        logging.error(f"Unable to connect to Postgres: {e}")
        sys.exit(1)

    # DDL
    logging.info("Recreating tables…")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS last_updated (
        script_name VARCHAR(255) PRIMARY KEY,
        last_run   TIMESTAMP
    );
    """)
    cursor.execute("DROP TABLE IF EXISTS price_data_daily;")
    cursor.execute("""
    CREATE TABLE price_data_daily (
        symbol       VARCHAR(20),
        date         DATE,
        open         NUMERIC(20,4),
        high         NUMERIC(20,4),
        low          NUMERIC(20,4),
        close        NUMERIC(20,4),
        volume       BIGINT,
        dividends    NUMERIC(20,4),
        stock_splits NUMERIC(20,4),
        PRIMARY KEY (symbol, date)
    );
    """)
    logging.info("Table 'price_data_daily' ready.")
    cursor.execute("DROP TABLE IF EXISTS price_data_daily_etf;")
    cursor.execute("""
    CREATE TABLE price_data_daily_etf (
        symbol       VARCHAR(20),
        date         DATE,
        open         NUMERIC(20,4),
        high         NUMERIC(20,4),
        low          NUMERIC(20,4),
        close        NUMERIC(20,4),
        volume       BIGINT,
        dividends    NUMERIC(20,4),
        stock_splits NUMERIC(20,4),
        PRIMARY KEY (symbol, date)
    );
    """)
    logging.info("Table 'price_data_daily_etf' ready.")
    log_mem("after DDL")

    # Load symbol lists
    cursor.execute("SELECT symbol FROM stock_symbols;")
    stocks = [r['symbol'] for r in cursor.fetchall()]
    logging.info(f"Found {len(stocks)} stock symbols.")
    cursor.execute("SELECT symbol FROM etf_symbols;")
    etfs = [r['symbol'] for r in cursor.fetchall()]
    logging.info(f"Found {len(etfs)} ETF symbols.")
    log_mem("after fetching symbols")

    # Process in batches
    process_in_batches(stocks, "price_data_daily", cursor)
    process_in_batches(etfs,   "price_data_daily_etf", cursor)

    # Record this run
    now = datetime.now()
    cursor.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, %s)
        ON CONFLICT (script_name) DO UPDATE
          SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME, now))

    # Final summary
    peak_mb = get_rss_mb()
    total_s = time.time() - t_start
    logging.info(f"[MEM] peak RSS during run: {peak_mb:.1f} MB")
    logging.info(f"Total runtime: {total_s:.1f}s")

    cursor.close()
    conn.close()
    logging.info("Done.")

if __name__ == "__main__":
    main()
