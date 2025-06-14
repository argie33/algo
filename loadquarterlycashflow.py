#!/usr/bin/env python3 
import sys
import time
import logging
import json
import os
import gc
import resource
import math

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import yfinance as yf
import pandas as pd

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadquarterlycashflow.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings
# -------------------------------
MAX_BATCH_RETRIES = 2
RETRY_DELAY = 0.5  # seconds between download retries

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

def clean_value(value):
    """Convert NaN or pandas NAs to None."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    return value

def load_quarterly_cashflow(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading quarterly cash flow for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 3, 0.5
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping = dict(zip(yq_batch, batch))

        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")
        for yq_sym, orig_sym in mapping.items():
            cashflow = None
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    cashflow = ticker.quarterly_cashflow
                    if cashflow is None or cashflow.empty:
                        raise ValueError("No quarterly cash flow data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        break
                    time.sleep(RETRY_DELAY)
            
            if cashflow is None or cashflow.empty:
                logging.error(f"Skipping {orig_sym} - failed to retrieve quarterly cash flow after {MAX_BATCH_RETRIES} attempts")
                continue
            
            try:
                data_to_insert = []
                for date_col in cashflow.columns:
                    date_value = pd.to_datetime(date_col).date()
                    for item_name in cashflow.index:
                        value = cashflow.loc[item_name, date_col]
                        cleaned_value = clean_value(value)
                        data_to_insert.append((orig_sym, date_value, item_name, cleaned_value))

                if data_to_insert:
                    execute_values(cur, """
                        INSERT INTO quarterly_cashflow (symbol, date, item_name, value)
                        VALUES %s
                        ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                            value = EXCLUDED.value,
                            fetched_at = NOW()
                    """, data_to_insert)

                conn.commit()
                processed += 1
                logging.info(f"Successfully processed {orig_sym} with {len(data_to_insert)} records")

            except Exception as e:
                logging.error(f"Failed to process {orig_sym}: {str(e)}")
                failed.append(orig_sym)
                conn.rollback()

        del batch, yq_batch, mapping
        gc.collect()
        log_mem(f"Batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, processed, failed

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    log_mem("startup")

    # Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Recreate table
    logging.info("Recreating quarterly_cashflow table...")
    cur.execute("DROP TABLE IF EXISTS quarterly_cashflow CASCADE;")
    cur.execute("""
        CREATE TABLE quarterly_cashflow (
            id          SERIAL PRIMARY KEY,
            symbol      VARCHAR(10) NOT NULL,
            date        DATE NOT NULL,
            item_name   VARCHAR(255) NOT NULL,
            value       NUMERIC,
            fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(symbol, date, item_name)
        );
    """)
    
    # Create index for better performance
    cur.execute("CREATE INDEX idx_quarterly_cashflow_symbol_date ON quarterly_cashflow(symbol, date);")
    
    # Ensure last_updated table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(255) PRIMARY KEY,
            last_run    TIMESTAMPTZ NOT NULL
        );
    """)
    conn.commit()

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_quarterly_cashflow(stock_syms, cur, conn)

    # Record last run
    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Stocks — total: {t_s}, processed: {p_s}, failed: {len(f_s)}")

    cur.close()
    conn.close()
    logging.info("All done.")
