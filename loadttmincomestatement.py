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
SCRIPT_NAME = "loadttmincomestatement.py"
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

def load_ttm_income_statement(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading TTM income statement for {total} symbols")
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
            income_statement = None
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    # Use the correct YFinance API method for quarterly income statement
                    income_statement = ticker.quarterly_financials
                    if income_statement is None or income_statement.empty:
                        raise ValueError("No TTM income statement data received")
                    
                    # Additional validation to ensure we have data
                    if income_statement.shape[0] == 0 or income_statement.shape[1] == 0:
                        raise ValueError("Empty income statement data received")
                    
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        continue
                    time.sleep(RETRY_DELAY)
            
            if income_statement is None:
                continue
                
            try:
                # For TTM, sum the last 4 quarters - but handle cases where we don't have 4 quarters
                num_quarters = min(income_statement.shape[1], 4)  # Use available quarters, max 4
                
                if num_quarters > 0:
                    # Sum the available quarters
                    ttm_data = income_statement.iloc[:, :num_quarters].sum(axis=1)
                    latest_date = income_statement.columns[0]
                else:
                    # No data available
                    logging.warning(f"No income statement data available for {orig_sym}")
                    continue
                
                # Convert pandas Timestamp to date properly
                if hasattr(latest_date, 'date'):
                    latest_date_obj = latest_date.date()
                elif hasattr(latest_date, 'to_pydatetime'):
                    latest_date_obj = latest_date.to_pydatetime().date()
                else:
                    latest_date_obj = latest_date
                
                # Build row data with proper error handling
                row_data = [orig_sym, latest_date_obj]
                
                # Get the predefined columns from the table structure
                predefined_columns = [
                    "Total Revenue", "Cost Of Revenue", "Gross Profit", "Research And Development",
                    "Selling General And Administration", "Operating Income", "Operating Expense",
                    "Interest Expense", "Interest Income", "Net Interest Income", "Other Income Expense",
                    "Income Tax Expense", "Net Income", "Net Income Common Stockholders",
                    "Net Income From Continuing Ops", "Net Income Including Noncontrolling Interests",
                    "Net Income Continuous Operations", "EBIT", "EBITDA", "EBITDAR",
                    "Reconciled Cost Of Revenue", "Reconciled Depreciation",
                    "Net Income From Continuing And Discontinued Operation", "Total Expenses",
                    "Total Revenue As Reported", "Operating Revenue", "Operating Income Loss",
                    "Net Income Available To Common Stockholders Basic",
                    "Net Income Available To Common Stockholders Diluted", "Basic Average Shares",
                    "Basic EPS", "Diluted Average Shares", "Diluted EPS", "Total Unusual Items",
                    "Total Unusual Items Excluding Goodwill", "Normalized Income", "Tax Rate For Calcs",
                    "Tax Effect Of Unusual Items", "Interest Income After Tax", "Net Interest Income After Tax",
                    "Change In Net Income", "Net Income From Continuing Operation Net Minority Interest",
                    "Net Income Including Noncontrolling Interests Net Minority Interest",
                    "Net Income Continuous Operations Net Minority Interest"
                ]
                
                # Map yfinance data to predefined columns
                for column in predefined_columns:
                    try:
                        # Try to find the column in the yfinance data (case-insensitive)
                        matching_keys = [key for key in ttm_data.index if key.lower() == column.lower()]
                        if matching_keys:
                            value = ttm_data[matching_keys[0]]
                            if pd.isna(value) or value is None:
                                row_data.append(None)
                            else:
                                row_data.append(float(value))
                        else:
                            row_data.append(None)
                    except (KeyError, IndexError, ValueError) as e:
                        logging.debug(f"Could not get {column} for {orig_sym}: {e}")
                        row_data.append(None)
                
                # Build the INSERT statement with predefined columns
                columns = ['symbol', 'date'] + predefined_columns
                placeholders = ', '.join(['%s'] * len(columns))
                column_names = ', '.join([f'"{col}"' if ' ' in col else col for col in columns])
                
                insert_sql = f"""
                    INSERT INTO ttm_income_statement ({column_names})
                    VALUES ({placeholders})
                    ON CONFLICT (symbol, date) DO UPDATE SET
                """
                
                # Build the UPDATE part
                update_parts = []
                for col in predefined_columns:
                    col_name = f'"{col}"' if ' ' in col else col
                    update_parts.append(f"{col_name} = EXCLUDED.{col_name}")
                insert_sql += ', '.join(update_parts)
                
                cur.execute(insert_sql, row_data)
                conn.commit()
                processed += 1
                logging.info(f"Successfully processed TTM income statement for {orig_sym}")

            except Exception as e:
                logging.error(f"Failed to process TTM income statement for {orig_sym}: {str(e)}")
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

    # Create TTM income statement table
    logging.info("Creating TTM income statement table...")
    cur.execute("""
        DROP TABLE IF EXISTS ttm_income_statement CASCADE;
    """)

    # Create table with predefined structure for common income statement columns
    create_table_sql = """
        CREATE TABLE ttm_income_statement (
            symbol VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            "Total Revenue" DOUBLE PRECISION,
            "Cost Of Revenue" DOUBLE PRECISION,
            "Gross Profit" DOUBLE PRECISION,
            "Research And Development" DOUBLE PRECISION,
            "Selling General And Administration" DOUBLE PRECISION,
            "Operating Income" DOUBLE PRECISION,
            "Operating Expense" DOUBLE PRECISION,
            "Interest Expense" DOUBLE PRECISION,
            "Interest Income" DOUBLE PRECISION,
            "Net Interest Income" DOUBLE PRECISION,
            "Other Income Expense" DOUBLE PRECISION,
            "Income Tax Expense" DOUBLE PRECISION,
            "Net Income" DOUBLE PRECISION,
            "Net Income Common Stockholders" DOUBLE PRECISION,
            "Net Income From Continuing Ops" DOUBLE PRECISION,
            "Net Income Including Noncontrolling Interests" DOUBLE PRECISION,
            "Net Income Continuous Operations" DOUBLE PRECISION,
            "EBIT" DOUBLE PRECISION,
            "EBITDA" DOUBLE PRECISION,
            "EBITDAR" DOUBLE PRECISION,
            "Reconciled Cost Of Revenue" DOUBLE PRECISION,
            "Reconciled Depreciation" DOUBLE PRECISION,
            "Net Income From Continuing And Discontinued Operation" DOUBLE PRECISION,
            "Total Expenses" DOUBLE PRECISION,
            "Total Revenue As Reported" DOUBLE PRECISION,
            "Operating Revenue" DOUBLE PRECISION,
            "Operating Income Loss" DOUBLE PRECISION,
            "Net Income Available To Common Stockholders Basic" DOUBLE PRECISION,
            "Net Income Available To Common Stockholders Diluted" DOUBLE PRECISION,
            "Basic Average Shares" DOUBLE PRECISION,
            "Basic EPS" DOUBLE PRECISION,
            "Diluted Average Shares" DOUBLE PRECISION,
            "Diluted EPS" DOUBLE PRECISION,
            "Total Unusual Items" DOUBLE PRECISION,
            "Total Unusual Items Excluding Goodwill" DOUBLE PRECISION,
            "Normalized Income" DOUBLE PRECISION,
            "Tax Rate For Calcs" DOUBLE PRECISION,
            "Tax Effect Of Unusual Items" DOUBLE PRECISION,
            "Interest Income After Tax" DOUBLE PRECISION,
            "Net Interest Income After Tax" DOUBLE PRECISION,
            "Change In Net Income" DOUBLE PRECISION,
            "Net Income From Continuing Operation Net Minority Interest" DOUBLE PRECISION,
            "Net Income Including Noncontrolling Interests Net Minority Interest" DOUBLE PRECISION,
            "Net Income Continuous Operations Net Minority Interest" DOUBLE PRECISION,
            PRIMARY KEY(symbol, date)
        );
    """
    cur.execute(create_table_sql)
    conn.commit()
    logging.info("Created TTM income statement table with predefined structure")

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_ttm_income_statement(stock_syms, cur, conn)

    # Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, p_e, f_e = load_ttm_income_statement(etf_syms, cur, conn)

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