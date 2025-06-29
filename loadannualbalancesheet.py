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
SCRIPT_NAME = "loadannualbalancesheet.py"
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
MAX_BATCH_RETRIES = 3
RETRY_DELAY = 0.2  # seconds between download retries

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

def load_annual_balance_sheet(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading annual balance sheet for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping = dict(zip(yq_batch, batch))

        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")

        for yq_sym, orig_sym in mapping.items():
            balance_sheet = None
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    # Use the correct YFinance API method for annual balance sheet
                    balance_sheet = ticker.balance_sheet
                    if balance_sheet is None or balance_sheet.empty:
                        raise ValueError("No annual balance sheet data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        continue
                    time.sleep(RETRY_DELAY)
            
            if balance_sheet is None:
                continue
                
            try:
                # Convert DataFrame to normalized format for insertion
                balance_sheet_data = []
                for date in balance_sheet.columns:
                    for metric in balance_sheet.index:
                        value = balance_sheet.loc[metric, date]
                        if pd.isna(value) or value is None:
                            continue
                        
                        balance_sheet_data.append((
                            orig_sym,
                            date.date() if hasattr(date, 'date') else date,
                            str(metric),
                            float(value)
                        ))
                
                if balance_sheet_data:
                    # Insert using normalized table structure
                    execute_values(cur, """
                        INSERT INTO annual_balance_sheet (symbol, date, item_name, value)
                        VALUES %s
                        ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                            value = EXCLUDED.value,
                            updated_at = NOW()
                    """, balance_sheet_data)
                    
                    conn.commit()
                    processed += 1
                    logging.info(f"Successfully processed annual balance sheet for {orig_sym}")

            except Exception as e:
                logging.error(f"Failed to process annual balance sheet for {orig_sym}: {str(e)}")
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

    # Create annual balance sheet table with normalized structure
    logging.info("Creating annual balance sheet table...")
    cur.execute("""
        DROP TABLE IF EXISTS annual_balance_sheet CASCADE;
    """)

    create_table_sql = """
        CREATE TABLE annual_balance_sheet (
            symbol VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, date, item_name)
        );
        
        CREATE INDEX idx_annual_balance_sheet_symbol ON annual_balance_sheet(symbol);
        CREATE INDEX idx_annual_balance_sheet_date ON annual_balance_sheet(date);
    """
    cur.execute(create_table_sql)
    conn.commit()
    logging.info("Created annual balance sheet table with normalized structure")

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_annual_balance_sheet(stock_syms, cur, conn)

    # Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, p_e, f_e = load_annual_balance_sheet(etf_syms, cur, conn)

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
    logging.info(f"ETFs   — total: {t_e}, processed: {p_e}, failed: {len(f_e)}")

    cur.close()
    conn.close()
    logging.info("All done.") 