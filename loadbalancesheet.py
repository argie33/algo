#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import gc
import resource
import math
from decimal import Decimal, InvalidOperation

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime
import pandas as pd
import numpy as np

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
# Financial value conversion helper
# -------------------------------
def safe_financial_value(value):
    """Convert financial value to Decimal, handling NaN/None/inf cases."""
    if value is None or pd.isna(value) or np.isinf(value):
        return None
    try:
        # Convert to string first to handle numpy types
        str_value = str(value)
        if str_value.lower() in ('nan', 'inf', '-inf'):
            return None
        return Decimal(str_value)
    except (ValueError, InvalidOperation, TypeError):
        return None

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
    CHUNK_SIZE, PAUSE = 5, 0.3
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE
    fetched_at = datetime.now()

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping = dict(zip(yq_batch, batch))

        logging.info(f"Processing batch {batch_idx+1}/{batches} ({len(batch)} symbols)")
        log_mem(f"Batch {batch_idx+1} start")
        
        for yq_sym, orig_sym in mapping.items():
            balance_sheet = None
            
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
                        break
                    time.sleep(RETRY_DELAY)
            
            if balance_sheet is None or balance_sheet.empty:
                logging.error(f"Skipping {orig_sym} - failed to retrieve balance sheet after {MAX_BATCH_RETRIES} attempts")
                continue
            
            try:
                # Process balance sheet data for each period
                for col in balance_sheet.columns:
                    period_end = col.strftime('%Y-%m-%d')
                    
                    # Extract values safely with financial conversion
                    def get_value(index_name):
                        if index_name in balance_sheet.index:
                            return safe_financial_value(balance_sheet.loc[index_name, col])
                        return None
                    
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
                            cash_and_cash_equivalents, fetched_at
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (ticker, period_end) DO UPDATE SET
                            ordinary_shares_number = EXCLUDED.ordinary_shares_number,
                            share_issued = EXCLUDED.share_issued,
                            net_debt = EXCLUDED.net_debt,
                            total_debt = EXCLUDED.total_debt,
                            tangible_book_value = EXCLUDED.tangible_book_value,
                            invested_capital = EXCLUDED.invested_capital,
                            working_capital = EXCLUDED.working_capital,
                            net_tangible_assets = EXCLUDED.net_tangible_assets,
                            common_stock_equity = EXCLUDED.common_stock_equity,
                            total_capitalization = EXCLUDED.total_capitalization,
                            stockholders_equity = EXCLUDED.stockholders_equity,
                            retained_earnings = EXCLUDED.retained_earnings,
                            additional_paid_in_capital = EXCLUDED.additional_paid_in_capital,
                            capital_stock = EXCLUDED.capital_stock,
                            common_stock = EXCLUDED.common_stock,
                            preferred_stock = EXCLUDED.preferred_stock,
                            total_liabilities_net_minority_interest = EXCLUDED.total_liabilities_net_minority_interest,
                            long_term_debt = EXCLUDED.long_term_debt,
                            current_liabilities = EXCLUDED.current_liabilities,
                            current_debt = EXCLUDED.current_debt,
                            accounts_payable = EXCLUDED.accounts_payable,
                            total_assets = EXCLUDED.total_assets,
                            net_ppe = EXCLUDED.net_ppe,
                            goodwill = EXCLUDED.goodwill,
                            current_assets = EXCLUDED.current_assets,
                            inventory = EXCLUDED.inventory,
                            accounts_receivable = EXCLUDED.accounts_receivable,
                            cash_and_cash_equivalents = EXCLUDED.cash_and_cash_equivalents,
                            fetched_at = EXCLUDED.fetched_at
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
                        get_value('Cash And Cash Equivalents'),
                        fetched_at
                    ))

                conn.commit()
                processed += 1
                logging.info(f"Successfully processed {orig_sym} - {len(balance_sheet.columns)} periods")

            except Exception as e:
                logging.error(f"Failed to process {orig_sym}: {str(e)}")
                failed.append(orig_sym)
                conn.rollback()

        # Cleanup
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
    # Recreate table with proper schema
    logging.info("Recreating balance sheet table...")
    cur.execute("DROP TABLE IF EXISTS balance_sheet CASCADE;")

    cur.execute("""
        CREATE TABLE balance_sheet (
            ticker VARCHAR(10) NOT NULL,
            period_end DATE NOT NULL,
            ordinary_shares_number NUMERIC(20,2),
            share_issued NUMERIC(20,2),
            net_debt NUMERIC(20,2),
            total_debt NUMERIC(20,2),
            tangible_book_value NUMERIC(20,2),
            invested_capital NUMERIC(20,2),
            working_capital NUMERIC(20,2),
            net_tangible_assets NUMERIC(20,2),
            common_stock_equity NUMERIC(20,2),
            total_capitalization NUMERIC(20,2),
            stockholders_equity NUMERIC(20,2),
            retained_earnings NUMERIC(20,2),
            additional_paid_in_capital NUMERIC(20,2),
            capital_stock NUMERIC(20,2),
            common_stock NUMERIC(20,2),
            preferred_stock NUMERIC(20,2),
            total_liabilities_net_minority_interest NUMERIC(20,2),
            long_term_debt NUMERIC(20,2),
            current_liabilities NUMERIC(20,2),
            current_debt NUMERIC(20,2),
            accounts_payable NUMERIC(20,2),
            total_assets NUMERIC(20,2),
            net_ppe NUMERIC(20,2),
            goodwill NUMERIC(20,2),
            current_assets NUMERIC(20,2),
            inventory NUMERIC(20,2),
            accounts_receivable NUMERIC(20,2),
            cash_and_cash_equivalents NUMERIC(20,2),
            fetched_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(ticker, period_end)
        );
    """)

    # Create indexes for performance
    cur.execute("CREATE INDEX idx_balance_sheet_ticker ON balance_sheet(ticker);")
    cur.execute("CREATE INDEX idx_balance_sheet_period_end ON balance_sheet(period_end);")
    cur.execute("CREATE INDEX idx_balance_sheet_fetched_at ON balance_sheet(fetched_at);")

    conn.commit()
    logging.info("Balance sheet table recreated successfully")

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
