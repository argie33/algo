#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import gc
import resource
from datetime import datetime, date
from typing import List, Tuple, Optional

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import boto3
import yfinance as yf
import pandas as pd

SCRIPT_NAME = "loadquarterlybalancesheet.py"
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
RETRY_DELAY = 1.0

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

def safe_convert_to_float(value) -> Optional[float]:
    """Safely convert value to float, handling various edge cases"""
    if pd.isna(value) or value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(',', '').replace('$', '').strip()
            if value == '' or value == '-' or value.lower() == 'n/a':
                return None
        return float(value)
    except (ValueError, TypeError):
        return None

def safe_convert_date(dt) -> Optional[date]:
    """Safely convert various date formats to date object"""
    if pd.isna(dt) or dt is None:
        return None
    try:
        if hasattr(dt, 'date'):
            return dt.date()
        elif isinstance(dt, str):
            return datetime.strptime(dt, '%Y-%m-%d').date()
        elif isinstance(dt, date):
            return dt
        else:
            return pd.to_datetime(dt).date()
    except (ValueError, TypeError):
        return None

def get_quarterly_balance_sheet_data(symbol: str) -> Optional[pd.DataFrame]:
    """Get quarterly balance sheet data using proper yfinance API with fallback methods"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Try multiple methods in order of preference
        methods_to_try = [
            ('quarterly_balance_sheet', 'quarterly balance sheet'),
        ]
        
        balance_sheet = None
        
        for method_name, description in methods_to_try:
            try:
                if hasattr(ticker, method_name):
                    logging.info(f"Trying {method_name} for {symbol}")
                    balance_sheet = getattr(ticker, method_name)
                    
                    if balance_sheet is not None and not balance_sheet.empty:
                        logging.info(f"✓ Successfully got data using {method_name} for {symbol}")
                        break
                    else:
                        logging.warning(f"{method_name} returned empty data for {symbol}")
                else:
                    logging.warning(f"Method {method_name} not available for {symbol}")
            except Exception as e:
                logging.warning(f"Error with {method_name} for {symbol}: {e}")
                continue
        
        if balance_sheet is None or balance_sheet.empty:
            logging.warning(f"No quarterly balance sheet data returned by any method for {symbol}")
            return None
        
        # Check if DataFrame contains any actual data (not all NaN)
        if balance_sheet.isna().all().all():
            logging.warning(f"Quarterly balance sheet data is all NaN for {symbol}")
            return None
            
        # Check if we have at least one column with data
        valid_columns = [col for col in balance_sheet.columns if not balance_sheet[col].isna().all()]
        if not valid_columns:
            logging.warning(f"No valid quarterly balance sheet columns found for {symbol}")
            return None
            
        # Sort columns by date (most recent first)
        balance_sheet = balance_sheet.reindex(sorted(balance_sheet.columns, reverse=True), axis=1)
        
        logging.info(f"Retrieved quarterly balance sheet data for {symbol}: {len(balance_sheet.columns)} periods, {len(balance_sheet.index)} line items")
        return balance_sheet
        
    except Exception as e:
        logging.error(f"Error fetching quarterly balance sheet for {symbol}: {e}")
        return None

def process_balance_sheet_data(symbol: str, balance_sheet: pd.DataFrame) -> List[Tuple]:
    """Process balance sheet DataFrame into database-ready tuples"""
    processed_data = []
    valid_dates = 0
    total_values = 0
    valid_values = 0
    
    for date_col in balance_sheet.columns:
        safe_date = safe_convert_date(date_col)
        if safe_date is None:
            logging.debug(f"Skipping invalid date column for {symbol}: {date_col}")
            continue
        valid_dates += 1
            
        for item_name in balance_sheet.index:
            value = balance_sheet.loc[item_name, date_col]
            total_values += 1
            safe_value = safe_convert_to_float(value)
            
            if safe_value is not None:
                valid_values += 1
                processed_data.append((
                    symbol,
                    safe_date,
                    str(item_name),
                    safe_value
                ))
    
    logging.info(f"Processed {symbol}: {valid_dates} valid dates, {valid_values}/{total_values} valid values, {len(processed_data)} records")
    return processed_data

def load_quarterly_balance_sheet(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading quarterly balance sheet for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")

        for symbol in batch:
            success = False
            
            for attempt in range(1, MAX_BATCH_RETRIES + 1):
                try:
                    # Clean symbol for yfinance (handle special characters)
                    yf_symbol = symbol.replace('.', '-').replace('$', '-P').upper()
                    
                    balance_sheet = get_quarterly_balance_sheet_data(yf_symbol)
                    if balance_sheet is None:
                        break
                    
                    # Process the data
                    balance_sheet_data = process_balance_sheet_data(symbol, balance_sheet)
                    
                    if balance_sheet_data:
                        # Insert data
                        execute_values(cur, """
                            INSERT INTO quarterly_balance_sheet (symbol, date, item_name, value)
                            VALUES %s
                            ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                                value = EXCLUDED.value,
                                updated_at = NOW()
                        """, balance_sheet_data)
                        conn.commit()
                        processed += 1
                        logging.info(f"✓ Successfully processed {symbol} ({len(balance_sheet_data)} records)")
                        success = True
                        break
                    else:
                        logging.warning(f"✗ No valid data found for {symbol} after processing")
                        break
                        
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {symbol}: {e}")
                    if attempt < MAX_BATCH_RETRIES:
                        time.sleep(RETRY_DELAY)
                    else:
                        conn.rollback()
            
            if not success:
                failed.append(symbol)

        del batch
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

    # Create quarterly balance sheet table with normalized structure
    logging.info("Creating quarterly balance sheet table...")
    cur.execute("""
        DROP TABLE IF EXISTS quarterly_balance_sheet CASCADE;
    """)

    create_table_sql = """
        CREATE TABLE quarterly_balance_sheet (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, date, item_name)
        );
        
        CREATE INDEX idx_quarterly_balance_sheet_symbol ON quarterly_balance_sheet(symbol);
        CREATE INDEX idx_quarterly_balance_sheet_date ON quarterly_balance_sheet(date);
        CREATE INDEX idx_quarterly_balance_sheet_item ON quarterly_balance_sheet(item_name);
    """
    cur.execute(create_table_sql)
    conn.commit()
    logging.info("Created quarterly balance sheet table with normalized structure")

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_quarterly_balance_sheet(stock_syms, cur, conn)

    # Load ETF symbols (if available)
    try:
        cur.execute("SELECT symbol FROM etf_symbols;")
        etf_syms = [r["symbol"] for r in cur.fetchall()]
        if etf_syms:
            t_e, p_e, f_e = load_quarterly_balance_sheet(etf_syms, cur, conn)
        else:
            t_e, p_e, f_e = 0, 0, []
    except Exception as e:
        logging.info(f"No ETF symbols table or error: {e}")
        t_e, p_e, f_e = 0, 0, []

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