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
SCRIPT_NAME = "loadquarterlybalancesheet.py"
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

def load_quarterly_balance_sheet(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading quarterly balance sheet for {total} symbols")
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
                    balance_sheet = ticker.quarterly_balance_sheet
                    if balance_sheet is None or balance_sheet.empty:
                        raise ValueError("No quarterly balance sheet data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        continue
                    time.sleep(RETRY_DELAY)
            
            try:
                # Convert DataFrame to list of tuples for insertion
                balance_sheet_data = []
                for date in balance_sheet.columns:
                    row_data = [orig_sym, date.date() if hasattr(date, 'date') else date]
                    for metric in balance_sheet.index:
                        value = balance_sheet.loc[metric, date]
                        if pd.isna(value) or value is None:
                            row_data.append(None)
                        else:
                            row_data.append(float(value))
                    balance_sheet_data.append(tuple(row_data))
                
                if balance_sheet_data:
                    # Get column names for the table
                    columns = ['symbol', 'date'] + list(balance_sheet.index.astype(str))
                    placeholders = ', '.join(['%s'] * len(columns))
                    column_names = ', '.join(columns)
                    
                    # Build the INSERT statement dynamically
                    insert_sql = f"""
                        INSERT INTO quarterly_balance_sheet ({column_names})
                        VALUES ({placeholders})
                        ON CONFLICT (symbol, date) DO UPDATE SET
                    """
                    
                    # Build the UPDATE part dynamically
                    update_parts = []
                    for col in columns[2:]:  # Skip symbol and date
                        update_parts.append(f"{col} = EXCLUDED.{col}")
                    insert_sql += ', '.join(update_parts)
                    
                    cur.executemany(insert_sql, balance_sheet_data)
                    conn.commit()
                    processed += 1
                    logging.info(f"Successfully processed quarterly balance sheet for {orig_sym}")

            except Exception as e:
                logging.error(f"Failed to process quarterly balance sheet for {orig_sym}: {str(e)}")
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

    # Create quarterly balance sheet table
    logging.info("Creating quarterly balance sheet table...")
    cur.execute("""
        DROP TABLE IF EXISTS quarterly_balance_sheet CASCADE;
    """)

    # Create table with predefined structure for common balance sheet columns
    create_table_sql = """
        CREATE TABLE quarterly_balance_sheet (
            symbol VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            "Total Assets" DOUBLE PRECISION,
            "Total Current Assets" DOUBLE PRECISION,
            "Cash And Cash Equivalents" DOUBLE PRECISION,
            "Short Term Investments" DOUBLE PRECISION,
            "Net Receivables" DOUBLE PRECISION,
            "Inventory" DOUBLE PRECISION,
            "Other Current Assets" DOUBLE PRECISION,
            "Total Non Current Assets" DOUBLE PRECISION,
            "Property Plant Equipment Net" DOUBLE PRECISION,
            "Intangible Assets" DOUBLE PRECISION,
            "Goodwill" DOUBLE PRECISION,
            "Long Term Investments" DOUBLE PRECISION,
            "Other Assets" DOUBLE PRECISION,
            "Total Liabilities Net Minority Interest" DOUBLE PRECISION,
            "Total Current Liabilities" DOUBLE PRECISION,
            "Accounts Payable" DOUBLE PRECISION,
            "Short Term Debt" DOUBLE PRECISION,
            "Other Current Liabilities" DOUBLE PRECISION,
            "Total Non Current Liabilities Net Minority Interest" DOUBLE PRECISION,
            "Long Term Debt" DOUBLE PRECISION,
            "Other Liabilities" DOUBLE PRECISION,
            "Total Equity Gross Minority Interest" DOUBLE PRECISION,
            "Total Equity" DOUBLE PRECISION,
            "Retained Earnings" DOUBLE PRECISION,
            "Common Stock" DOUBLE PRECISION,
            "Treasury Stock" DOUBLE PRECISION,
            "Other Equity" DOUBLE PRECISION,
            "Total Capitalization" DOUBLE PRECISION,
            "Working Capital" DOUBLE PRECISION,
            "Net Tangible Assets" DOUBLE PRECISION,
            "Invested Capital" DOUBLE PRECISION,
            "Tangible Book Value" DOUBLE PRECISION,
            "Total Debt" DOUBLE PRECISION,
            "Net Debt" DOUBLE PRECISION,
            "Share Issued" DOUBLE PRECISION,
            "Ordinary Shares Number" DOUBLE PRECISION,
            "Treasury Shares Number" DOUBLE PRECISION,
            PRIMARY KEY(symbol, date)
        );
    """
    cur.execute(create_table_sql)
    conn.commit()
    logging.info("Created quarterly balance sheet table with predefined structure")

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_quarterly_balance_sheet(stock_syms, cur, conn)

    # Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, p_e, f_e = load_quarterly_balance_sheet(etf_syms, cur, conn)

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