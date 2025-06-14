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

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadbalancesheet.py"
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

def load_balance_sheet_data(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading balance sheet data for {total} symbols")
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
            balance_sheet = None  # Initialize balance_sheet variable
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    balance_sheet = ticker.balance_sheet
                    if balance_sheet is None or balance_sheet.empty:
                        raise ValueError("No balance sheet data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        break  # Break instead of continue to skip processing
                    time.sleep(RETRY_DELAY)
            
            # Skip processing if balance_sheet was not successfully retrieved
            if balance_sheet is None or balance_sheet.empty:
                logging.error(f"Skipping {orig_sym} - failed to retrieve balance sheet after {MAX_BATCH_RETRIES} attempts")
                continue
            
            try:
                # Process balance sheet data
                for col in balance_sheet.columns:
                    period_end = col.strftime('%Y-%m-%d')
                    
                    # Extract values safely
                    def get_value(index_name):
                        return balance_sheet.loc[index_name, col] if index_name in balance_sheet.index else None
                    
                    # Insert balance sheet data
                    cur.execute("""
                        INSERT INTO balance_sheet (
                            ticker, period_end, ordinary_shares_number, share_issued, 
                            net_debt, total_debt, tangible_book_value, invested_capital,
                            working_capital, net_tangible_assets, common_stock_equity,
                            total_capitalization, stockholders_equity, retained_earnings,
                            additional_paid_in_capital, capital_stock, common_stock,
                            preferred_stock, total_liabilities_net_minority_interest,
                            long_term_debt, current_liabilities, current_debt,
                            accounts_payable, total_assets, net_ppe, goodwill,
                            current_assets, inventory, accounts_receivable,
                            cash_and_cash_equivalents
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (ticker, period_end) DO UPDATE SET
                            ordinary_shares_number = EXCLUDED.ordinary_shares_number,
                            total_debt = EXCLUDED.total_debt,
                            stockholders_equity = EXCLUDED.stockholders_equity
                    """, (
                        orig_sym, period_end,
                        get_value('Ordinary Shares Number'),
                        get_value('Share Issued'),
                        get_value('Net Debt'),
                        get_value('Total Debt'),
                        get_value('Tangible Book Value'),
                        get_value('Invested Capital'),
                        get_value('Working Capital'),
                        get_value('Net Tangible Assets'),
                        get_value('Common Stock Equity'),
                        get_value('Total Capitalization'),
                        get_value('Stockholders Equity'),
                        get_value('Retained Earnings'),
                        get_value('Additional Paid In Capital'),
                        get_value('Capital Stock'),
                        get_value('Common Stock'),
                        get_value('Preferred Stock'),
                        get_value('Total Liabilities Net Minority Interest'),
                        get_value('Long Term Debt'),
                        get_value('Current Liabilities'),
                        get_value('Current Debt'),
                        get_value('Accounts Payable'),
                        get_value('Total Assets'),
                        get_value('Net PPE'),
                        get_value('Goodwill'),
                        get_value('Current Assets'),
                        get_value('Inventory'),
                        get_value('Accounts Receivable'),
                        get_value('Cash And Cash Equivalents')
                    ))

                conn.commit()
                processed += 1
                logging.info(f"Successfully processed {orig_sym}")

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
    logging.info("Recreating balance sheet table...")
    cur.execute("DROP TABLE IF EXISTS balance_sheet CASCADE;")

    cur.execute("""
        CREATE TABLE balance_sheet (
            ticker VARCHAR(10) NOT NULL,
            period_end DATE NOT NULL,
            ordinary_shares_number BIGINT,
            share_issued BIGINT,
            net_debt BIGINT,
            total_debt BIGINT,
            tangible_book_value BIGINT,
            invested_capital BIGINT,
            working_capital BIGINT,
            net_tangible_assets BIGINT,
            common_stock_equity BIGINT,
            total_capitalization BIGINT,
            stockholders_equity BIGINT,
            retained_earnings BIGINT,
            additional_paid_in_capital BIGINT,
            capital_stock BIGINT,
            common_stock BIGINT,
            preferred_stock BIGINT,
            total_liabilities_net_minority_interest BIGINT,
            long_term_debt BIGINT,
            current_liabilities BIGINT,
            current_debt BIGINT,
            accounts_payable BIGINT,
            total_assets BIGINT,
            net_ppe BIGINT,
            goodwill BIGINT,
            current_assets BIGINT,
            inventory BIGINT,
            accounts_receivable BIGINT,
            cash_and_cash_equivalents BIGINT,
            PRIMARY KEY(ticker, period_end)
        );
    """)

    conn.commit()

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_balance_sheet_data(stock_syms, cur, conn)

    # Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, p_e, f_e = load_balance_sheet_data(etf_syms, cur, conn)

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
