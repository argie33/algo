#!/usr/bin/env python3 
"""
loadcashflow.py - Load annual cash flow data from Yahoo Finance
Standardized structure matching loadinfo.py
"""
import sys
import time
import logging
import json
import os
import gc
import resource
import math
import functools
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import pandas as pd
import boto3
import yfinance as yf

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadcashflow.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logger.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Environment and DB configuration
# -------------------------------
DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")
if not DB_SECRET_ARN:
    logger.error("DB_SECRET_ARN environment variable is not set")
    sys.exit(1)

def get_db_config():
    """
    Fetch host, port, dbname, username & password from Secrets Manager.
    SecretString must be JSON with keys: username, password, host, port, dbname.
    """
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"], 
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

# -------------------------------
# Retry settings and decorator
# -------------------------------
MAX_BATCH_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries

def retry(max_attempts=3, initial_delay=2, backoff=2):
    """Retry decorator with exponential backoff."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(symbol, *args, **kwargs):
            attempts, delay = 0, initial_delay
            while attempts < max_attempts:
                try:
                    return f(symbol, *args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logger.error(
                        f"{f.__name__} failed for {symbol} "
                        f"(attempt {attempts}/{max_attempts}): {e}"
                    )
                    if attempts < max_attempts:
                        time.sleep(delay)
                        delay *= backoff
            raise RuntimeError(
                f"All {max_attempts} attempts failed for {f.__name__} with symbol {symbol}"
            )
        return wrapper
    return decorator

def clean_value(value):
    """Convert NaN or pandas NAs to None."""
    if pd.isna(value):
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value

def ensure_tables(conn):
    """Drop & recreate cash_flow table and ensure last_updated exists."""
    with conn.cursor() as cur:
        logger.info("Dropping and recreating cash_flow table...")
        
        # Drop table and indexes
        cur.execute("DROP TABLE IF EXISTS cash_flow CASCADE;")
        
        # Create cash_flow table
        cur.execute("""
            CREATE TABLE cash_flow (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                period_end DATE NOT NULL,
                operating_cash_flow BIGINT,
                investing_cash_flow BIGINT,
                financing_cash_flow BIGINT,
                end_cash_position BIGINT,
                capital_expenditure BIGINT,
                issuance_of_capital_stock BIGINT,
                issuance_of_debt BIGINT,
                repayment_of_debt BIGINT,
                repurchase_of_capital_stock BIGINT,
                free_cash_flow BIGINT,
                net_income BIGINT,
                depreciation BIGINT,
                changes_in_working_capital BIGINT,
                stock_based_compensation BIGINT,
                fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, period_end)
            );
        """)
        
        # Create indexes
        cur.execute("CREATE INDEX idx_cash_flow_symbol ON cash_flow (symbol);")
        cur.execute("CREATE INDEX idx_cash_flow_period_end ON cash_flow (period_end);")
        
        # Ensure last_updated table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS last_updated (
                script_name VARCHAR(255) PRIMARY KEY,
                last_run TIMESTAMPTZ NOT NULL
            );
        """)
    conn.commit()
    logger.info("Tables created successfully")

@retry(max_attempts=MAX_BATCH_RETRIES, initial_delay=RETRY_DELAY, backoff=2)
def process_symbol(symbol, fetched_at):
    """Fetch annual cash flow data via yfinance and return processed data."""
    yf_symbol = symbol.upper().replace(".", "-").replace("$", "-")
    logger.debug(f"Processing {symbol} (yfinance: {yf_symbol})")
    
    ticker = yf.Ticker(yf_symbol)
    
    # Get annual cash flow data
    try:
        cash_flow = ticker.cashflow
        if cash_flow is None or cash_flow.empty:
            logger.warning(f"No annual cash flow data for {symbol}")
            return []
    except Exception as e:
        logger.error(f"Error fetching annual cash flow data for {symbol}: {e}")
        raise

    data_to_insert = []
    
    # Process each period (column)
    for col in cash_flow.columns:
        period_end = pd.to_datetime(col).strftime('%Y-%m-%d')
        
        # Extract values safely with proper field mapping
        def get_value(index_name):
            return clean_value(cash_flow.loc[index_name, col]) if index_name in cash_flow.index else None
        
        # Prepare data row
        data_row = (
            symbol,
            period_end,
            get_value('Operating Cash Flow'),
            get_value('Investing Cash Flow'),
            get_value('Financing Cash Flow'),
            get_value('End Cash Position'),
            get_value('Capital Expenditure'),
            get_value('Issuance Of Capital Stock'),
            get_value('Issuance Of Debt'),
            get_value('Repayment Of Debt'),
            get_value('Repurchase Of Capital Stock'),
            get_value('Free Cash Flow'),
            get_value('Net Income'),
            get_value('Depreciation'),
            get_value('Changes In Working Capital'),
            get_value('Stock Based Compensation'),
            fetched_at
        )
        data_to_insert.append(data_row)
    
    logger.debug(f"Extracted {len(data_to_insert)} periods for {symbol}")
    return data_to_insert

def process_batch(symbols, conn, fetched_at):
    """Process a batch of symbols."""
    batch_data = []
    failed_symbols = []
    
    for symbol in symbols:
        try:
            symbol_data = process_symbol(symbol, fetched_at)
            batch_data.extend(symbol_data)
            logger.info(f"Successfully processed {symbol} - {len(symbol_data)} periods")
        except Exception as e:
            logger.error(f"Failed to process {symbol}: {e}")
            failed_symbols.append(symbol)
    
    # Batch insert all data
    if batch_data:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO cash_flow (
                    symbol, period_end, operating_cash_flow, investing_cash_flow,
                    financing_cash_flow, end_cash_position, capital_expenditure,
                    issuance_of_capital_stock, issuance_of_debt, repayment_of_debt,
                    repurchase_of_capital_stock, free_cash_flow, net_income,
                    depreciation, changes_in_working_capital, stock_based_compensation,
                    fetched_at
                ) VALUES %s
                ON CONFLICT (symbol, period_end) DO UPDATE SET
                    operating_cash_flow = EXCLUDED.operating_cash_flow,
                    investing_cash_flow = EXCLUDED.investing_cash_flow,
                    financing_cash_flow = EXCLUDED.financing_cash_flow,
                    end_cash_position = EXCLUDED.end_cash_position,
                    capital_expenditure = EXCLUDED.capital_expenditure,
                    issuance_of_capital_stock = EXCLUDED.issuance_of_capital_stock,
                    issuance_of_debt = EXCLUDED.issuance_of_debt,
                    repayment_of_debt = EXCLUDED.repayment_of_debt,
                    repurchase_of_capital_stock = EXCLUDED.repurchase_of_capital_stock,
                    free_cash_flow = EXCLUDED.free_cash_flow,
                    net_income = EXCLUDED.net_income,
                    depreciation = EXCLUDED.depreciation,
                    changes_in_working_capital = EXCLUDED.changes_in_working_capital,
                    stock_based_compensation = EXCLUDED.stock_based_compensation,
                    fetched_at = EXCLUDED.fetched_at
                """,
                batch_data
            )
        conn.commit()
        logger.info(f"Inserted {len(batch_data)} cash flow records")
    
    return len(symbols) - len(failed_symbols), failed_symbols

def update_last_run(conn):
    """Update the last run timestamp."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME,))
    conn.commit()

def main():
    """Main execution function."""
    log_mem("startup")
    conn = None
    
    try:
        # Connect to database
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            dbname=cfg["dbname"],
            cursor_factory=RealDictCursor
        )
        conn.autocommit = False
        logger.info("Connected to database successfully")
        
        # Set up tables
        ensure_tables(conn)
        
        # Get current timestamp for consistent fetched_at
        fetched_at = datetime.now()
        
        # Fetch all symbols
        log_mem("before fetching symbols")
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol;")
            symbols = [r["symbol"] for r in cur.fetchall()]
        log_mem("after fetching symbols")
        
        total_symbols = len(symbols)
        logger.info(f"Processing {total_symbols} symbols")
        
        # Process in batches
        BATCH_SIZE = 10
        BATCH_PAUSE = 1.0
        total_processed = 0
        total_failed = []
        
        for i in range(0, total_symbols, BATCH_SIZE):
            batch = symbols[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            total_batches = (total_symbols + BATCH_SIZE - 1) // BATCH_SIZE
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} symbols)")
            log_mem(f"batch {batch_num} start")
            
            try:
                processed, failed = process_batch(batch, conn, fetched_at)
                total_processed += processed
                total_failed.extend(failed)
                
                logger.info(f"Batch {batch_num} completed: {processed} processed, {len(failed)} failed")
                
            except Exception as e:
                logger.error(f"Batch {batch_num} failed completely: {e}")
                total_failed.extend(batch)
            
            # Memory management
            gc.collect()
            log_mem(f"batch {batch_num} end")
            
            # Pause between batches
            if i + BATCH_SIZE < total_symbols:
                time.sleep(BATCH_PAUSE)
        
        # Update last run timestamp
        update_last_run(conn)
        
        # Final statistics
        peak_mem = get_rss_mb()
        logger.info(f"[MEM] peak RSS: {peak_mem:.1f} MB")
        logger.info(f"Processing complete: {total_processed}/{total_symbols} processed, {len(total_failed)} failed")
        
        if total_failed:
            logger.warning(f"Failed symbols: {total_failed[:10]}{'...' if len(total_failed) > 10 else ''}")
        
    except Exception as e:
        logger.exception(f"Fatal error in main(): {e}")
        sys.exit(1)
        
    finally:
        if conn:
            try:
                conn.close()
                logger.info("Database connection closed")
            except Exception:
                logger.exception("Error closing database connection")
        
        log_mem("end of script")
        logger.info("loadcashflow.py completed successfully")

if __name__ == "__main__":
    main()
