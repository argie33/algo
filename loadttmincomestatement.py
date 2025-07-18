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

SCRIPT_NAME = "loadttmincomestatement.py"
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

def calculate_ttm_income_statement(symbol: str) -> Optional[pd.DataFrame]:
    """Calculate TTM income statement from quarterly data with fallback methods"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Try multiple methods to get quarterly data
        methods_to_try = [
            ('quarterly_income_stmt', 'quarterly income statement (new method)'),
            ('quarterly_financials', 'quarterly income statement (legacy method)'),
        ]
        
        income_statement = None
        
        for method_name, description in methods_to_try:
            try:
                if hasattr(ticker, method_name):
                    logging.info(f"Trying {method_name} for TTM calculation for {symbol}")
                    income_statement = getattr(ticker, method_name)
                    
                    if income_statement is not None and not income_statement.empty:
                        logging.info(f"✓ Successfully got data using {method_name} for TTM calculation for {symbol}")
                        break
                    else:
                        logging.warning(f"{method_name} returned empty data for TTM calculation for {symbol}")
                else:
                    logging.warning(f"Method {method_name} not available for TTM calculation for {symbol}")
            except Exception as e:
                logging.warning(f"Error with {method_name} for TTM calculation for {symbol}: {e}")
                continue
        
        if income_statement is None or income_statement.empty:
            logging.warning(f"No quarterly income statement data returned by any method for TTM calculation for {symbol}")
            return None
        
        # Check if DataFrame contains any actual data (not all NaN)
        if income_statement.isna().all().all():
            logging.warning(f"Quarterly income statement data is all NaN for TTM calculation for {symbol}")
            return None
            
        # Sort columns by date (most recent first)
        income_statement = income_statement.reindex(sorted(income_statement.columns, reverse=True), axis=1)
        
        # Take the most recent 4 quarters for TTM calculation
        if len(income_statement.columns) < 4:
            logging.warning(f"Insufficient quarterly data for TTM calculation for {symbol} (only {len(income_statement.columns)} quarters available)")
            return None
            
        ttm_quarters = income_statement.iloc[:, :4]  # Most recent 4 quarters
        
        # Check if we have enough valid data in the 4 quarters
        valid_quarters = sum(1 for col in ttm_quarters.columns if not ttm_quarters[col].isna().all())
        if valid_quarters < 3:  # Need at least 3 quarters with some data
            logging.warning(f"Insufficient valid quarterly data for TTM calculation for {symbol} (only {valid_quarters} quarters with data)")
            return None
        
        # Calculate TTM by summing the 4 quarters (pandas will handle NaN appropriately)
        ttm_data = ttm_quarters.sum(axis=1, skipna=True)
        
        # Filter out rows where all quarters were NaN
        ttm_data = ttm_data[ttm_data.notna()]
        
        if ttm_data.empty:
            logging.warning(f"No valid TTM data after calculation for {symbol}")
            return None
        
        # Create a DataFrame with TTM data using most recent quarter date as reference
        ttm_date = income_statement.columns[0]  # Most recent quarter date
        ttm_df = pd.DataFrame({ttm_date: ttm_data})
        
        logging.info(f"Calculated TTM income statement for {symbol}: {len(ttm_df)} line items from {valid_quarters} quarters")
        return ttm_df
        
    except Exception as e:
        logging.error(f"Error calculating TTM income statement for {symbol}: {e}")
        return None

def process_ttm_income_statement_data(symbol: str, ttm_income_statement: pd.DataFrame) -> List[Tuple]:
    """Process TTM income statement DataFrame into database-ready tuples"""
    processed_data = []
    valid_dates = 0
    total_values = 0
    valid_values = 0
    
    for date_col in ttm_income_statement.columns:
        safe_date = safe_convert_date(date_col)
        if safe_date is None:
            logging.debug(f"Skipping invalid date column for {symbol}: {date_col}")
            continue
        valid_dates += 1
            
        for item_name in ttm_income_statement.index:
            value = ttm_income_statement.loc[item_name, date_col]
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
    
    logging.info(f"Processed TTM {symbol}: {valid_dates} valid dates, {valid_values}/{total_values} valid values, {len(processed_data)} records")
    return processed_data

def load_ttm_income_statement(symbols: List[str], cur, conn) -> Tuple[int, int, List[str]]:
    """Load TTM income statement data for given symbols"""
    total = len(symbols)
    logging.info(f"Loading TTM income statement for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 10, 0.5
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
                    
                    ttm_income_statement = calculate_ttm_income_statement(yf_symbol)
                    if ttm_income_statement is None:
                        break
                    
                    # Process the data
                    ttm_income_statement_data = process_ttm_income_statement_data(symbol, ttm_income_statement)
                    
                    if ttm_income_statement_data:
                        # Insert data
                        execute_values(cur, """
                            INSERT INTO ttm_income_statement (symbol, date, item_name, value)
                            VALUES %s
                            ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                                value = EXCLUDED.value,
                                updated_at = NOW()
                        """, ttm_income_statement_data)
                        conn.commit()
                        processed += 1
                        logging.info(f"✓ Successfully processed {symbol} ({len(ttm_income_statement_data)} TTM records)")
                        success = True
                        break
                    else:
                        logging.warning(f"✗ No valid TTM data found for {symbol} after processing")
                        break
                        
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {symbol}: {e}")
                    if attempt < MAX_BATCH_RETRIES:
                        time.sleep(RETRY_DELAY)
                    else:
                        conn.rollback()
            
            if not success:
                failed.append(symbol)
                
        gc.collect()
        log_mem(f"Batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, processed, failed

def create_table(cur, conn):
    """Create the TTM income statement table"""
    logging.info("Creating TTM income statement table...")
    cur.execute("DROP TABLE IF EXISTS ttm_income_statement CASCADE;")
    
    create_table_sql = """
        CREATE TABLE ttm_income_statement (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, date, item_name)
        );
        
        CREATE INDEX idx_ttm_income_statement_symbol ON ttm_income_statement(symbol);
        CREATE INDEX idx_ttm_income_statement_date ON ttm_income_statement(date);
        CREATE INDEX idx_ttm_income_statement_item ON ttm_income_statement(item_name);
    """
    cur.execute(create_table_sql)
    conn.commit()
    logging.info("Created TTM income statement table")

if __name__ == "__main__":
    log_mem("startup")

    # Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    ,
            sslmode='require'
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create table
    create_table(cur, conn)

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    if stock_syms:
        t_s, p_s, f_s = load_ttm_income_statement(stock_syms, cur, conn)
        logging.info(f"Stocks — total: {t_s}, processed: {p_s}, failed: {len(f_s)}")

    # Load ETF symbols (if available)
    try:
        cur.execute("SELECT symbol FROM etf_symbols;")
        etf_syms = [r["symbol"] for r in cur.fetchall()]
        if etf_syms:
            t_e, p_e, f_e = load_ttm_income_statement(etf_syms, cur, conn)
            logging.info(f"ETFs — total: {t_e}, processed: {p_e}, failed: {len(f_e)}")
    except Exception as e:
        logging.info(f"No ETF symbols table or error: {e}")

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

    cur.close()
    conn.close()
    logging.info("All done.")