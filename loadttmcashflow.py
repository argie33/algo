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
SCRIPT_NAME = "loadttmcashflow.py"
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

def load_ttm_cash_flow(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading TTM cash flow for {total} symbols")
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
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    cash_flow = ticker.quarterly_cashflow
                    if cash_flow is None or cash_flow.empty:
                        raise ValueError("No TTM cash flow data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        continue
                    time.sleep(RETRY_DELAY)
            
            try:
                if cash_flow.shape[1] >= 4:
                    ttm_data = cash_flow.iloc[:, :4].sum(axis=1)
                    latest_date = cash_flow.columns[0]
                    row_data = [orig_sym, pd.Timestamp(latest_date).date()]
                    for metric in cash_flow.index:
                        value = ttm_data[metric]
                        if pd.isna(value) or value is None:
                            row_data.append(None)
                        else:
                            row_data.append(float(value))
                    columns = ['symbol', 'date'] + list(cash_flow.index.astype(str))
                    placeholders = ', '.join(['%s'] * len(columns))
                    column_names = ', '.join(columns)
                    insert_sql = f"""
                        INSERT INTO ttm_cash_flow ({column_names})
                        VALUES ({placeholders})
                        ON CONFLICT (symbol, date) DO UPDATE SET
                    """
                    update_parts = []
                    for col in columns[2:]:
                        update_parts.append(f"{col} = EXCLUDED.{col}")
                    insert_sql += ', '.join(update_parts)
                    cur.execute(insert_sql, row_data)
                    conn.commit()
                    processed += 1
                    logging.info(f"Successfully processed TTM cash flow for {orig_sym}")
            except Exception as e:
                logging.error(f"Failed to process TTM cash flow for {orig_sym}: {str(e)}")
                failed.append(orig_sym)
                conn.rollback()
        del batch, yq_batch, mapping
        gc.collect()
        log_mem(f"Batch {batch_idx+1} end")
        time.sleep(PAUSE)
    return total, processed, failed

if __name__ == "__main__":
    log_mem("startup")
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    logging.info("Creating TTM cash flow table...")
    cur.execute("""
        DROP TABLE IF EXISTS ttm_cash_flow CASCADE;
    """)
    sample_ticker = yf.Ticker("AAPL")
    sample_cash_flow = sample_ticker.quarterly_cashflow
    if sample_cash_flow is not None and not sample_cash_flow.empty:
        columns = ['symbol VARCHAR(10) NOT NULL', 'date DATE NOT NULL']
        for metric in sample_cash_flow.index:
            columns.append(f'"{metric}" DOUBLE PRECISION')
        columns.append('PRIMARY KEY(symbol, date)')
        create_table_sql = f"""
            CREATE TABLE ttm_cash_flow (
                {', '.join(columns)}
            );
        """
        cur.execute(create_table_sql)
        conn.commit()
        logging.info("Created TTM cash flow table with dynamic columns")
    else:
        logging.error("Could not get sample data to create table structure")
        sys.exit(1)
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_ttm_cash_flow(stock_syms, cur, conn)
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, p_e, f_e = load_ttm_cash_flow(etf_syms, cur, conn)
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