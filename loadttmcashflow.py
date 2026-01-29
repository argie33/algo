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

SCRIPT_NAME = "loadttmcashflow.py"
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
    """Get database configuration - works in AWS, locally via socket, or with env vars"""
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        try:
            import boto3
            secret_str = boto3.client("secretsmanager").get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"],
            }
        except Exception as e:
            logging.warning(f"Failed to fetch from AWS Secrets Manager: {e}, falling back to local connection")

    # Try local socket connection first (peer authentication) - for local development
    try:
        # Test socket connection without storing config
        test_conn = psycopg2.connect(
            dbname=os.environ.get("DB_NAME", "stocks"),
            user="stocks"
        )
        test_conn.close()
        # Socket connection works, use it
        return {
            "host": None,  # Use socket
            "user": "stocks",
            "password": None,
            "dbname": os.environ.get("DB_NAME", "stocks"),
        }
    except Exception as e:
        logging.debug(f"Socket connection not available, falling back to env vars: {e}")
        pass

    # Fall back to environment variables
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", "bed0elAn"),
        "dbname": os.environ.get("DB_NAME", "stocks"),
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

def calculate_ttm_cash_flow(symbol: str) -> Optional[pd.DataFrame]:
    """Calculate TTM cash flow from quarterly data with fallback methods"""
    try:
        # Convert ticker format for yfinance (e.g., BRK.B → BRK-B)

        yf_symbol = symbol.replace(".", "-").replace("$", "-").upper()

        ticker = yf.Ticker(yf_symbol)
        
        # Try multiple methods to get quarterly data
        methods_to_try = [
            ('quarterly_cash_flow', 'quarterly cash flow (new method)'),
            ('quarterly_cashflow', 'quarterly cash flow (legacy method)'),
        ]
        
        cash_flow = None
        
        for method_name, description in methods_to_try:
            try:
                if hasattr(ticker, method_name):
                    logging.info(f"Trying {method_name} for TTM calculation for {symbol}")
                    cash_flow = getattr(ticker, method_name)
                    
                    if cash_flow is not None and not cash_flow.empty:
                        logging.info(f"✓ Successfully got data using {method_name} for TTM calculation for {symbol}")
                        break
                    else:
                        logging.warning(f"{method_name} returned empty data for TTM calculation for {symbol}")
                else:
                    logging.warning(f"Method {method_name} not available for TTM calculation for {symbol}")
            except Exception as e:
                logging.warning(f"Error with {method_name} for TTM calculation for {symbol}: {e}")
                continue
        
        if cash_flow is None or cash_flow.empty:
            logging.warning(f"No quarterly cash flow data returned by any method for TTM calculation for {symbol}")
            return None
        
        # Check if DataFrame contains any actual data (not all NaN)
        if cash_flow.isna().all().all():
            logging.warning(f"Quarterly cash flow data is all NaN for TTM calculation for {symbol}")
            return None
            
        # Sort columns by date (most recent first)
        cash_flow = cash_flow.reindex(sorted(cash_flow.columns, reverse=True), axis=1)
        
        # Take the most recent 4 quarters for TTM calculation
        if len(cash_flow.columns) < 4:
            logging.warning(f"Insufficient quarterly data for TTM calculation for {symbol} (only {len(cash_flow.columns)} quarters available)")
            return None
            
        ttm_quarters = cash_flow.iloc[:, :4]  # Most recent 4 quarters
        
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
        ttm_date = cash_flow.columns[0]  # Most recent quarter date
        ttm_df = pd.DataFrame({ttm_date: ttm_data})
        
        logging.info(f"Calculated TTM cash flow for {symbol}: {len(ttm_df)} line items from {valid_quarters} quarters")
        return ttm_df
        
    except Exception as e:
        logging.error(f"Error calculating TTM cash flow for {symbol}: {e}")
        return None

def process_ttm_cash_flow_data(symbol: str, ttm_cash_flow: pd.DataFrame) -> List[Tuple]:
    """Process TTM cash flow DataFrame into database-ready tuples"""
    processed_data = []
    valid_dates = 0
    total_values = 0
    valid_values = 0
    
    for date_col in ttm_cash_flow.columns:
        safe_date = safe_convert_date(date_col)
        if safe_date is None:
            logging.debug(f"Skipping invalid date column for {symbol}: {date_col}")
            continue
        valid_dates += 1
            
        for item_name in ttm_cash_flow.index:
            value = ttm_cash_flow.loc[item_name, date_col]
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

def load_ttm_cash_flow(symbols: List[str], cur, conn) -> Tuple[int, int, List[str]]:
    """Load TTM cash flow data for given symbols"""
    total = len(symbols)
    logging.info(f"Loading TTM cash flow for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 10, 0  # Fast mode - no static pauses
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
                    
                    ttm_cash_flow = calculate_ttm_cash_flow(yf_symbol)
                    if ttm_cash_flow is None:
                        break
                    
                    # Process the data
                    ttm_cash_flow_data = process_ttm_cash_flow_data(symbol, ttm_cash_flow)
                    
                    if ttm_cash_flow_data:
                        # Insert data
                        execute_values(cur, """
                            INSERT INTO ttm_cash_flow (symbol, date, item_name, value)
                            VALUES %s
                            ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                                value = EXCLUDED.value,
                                updated_at = NOW()
                        """, ttm_cash_flow_data)
                        conn.commit()
                        processed += 1
                        logging.info(f"✓ Successfully processed {symbol} ({len(ttm_cash_flow_data)} TTM records)")
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
    """Create the TTM cash flow table if it doesn't exist"""
    logging.info("Creating TTM cash flow table if needed...")
    try:
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS ttm_cash_flow (
                symbol VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                item_name TEXT NOT NULL,
                value DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY(symbol, date, item_name)
            );

            CREATE INDEX IF NOT EXISTS idx_ttm_cash_flow_symbol ON ttm_cash_flow(symbol);
            CREATE INDEX IF NOT EXISTS idx_ttm_cash_flow_date ON ttm_cash_flow(date);
            CREATE INDEX IF NOT EXISTS idx_ttm_cash_flow_item ON ttm_cash_flow(item_name);
        """
        cur.execute(create_table_sql)
        conn.commit()
        logging.info("Created TTM cash flow table if needed")
    except Exception as e:
        logging.info(f"Table likely exists: {e}")

if __name__ == "__main__":
    log_mem("startup")

    # Connect to DB
    cfg = get_db_config()
    if cfg["host"]:
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg.get("port", 5432),
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
    else:
        # Socket connection (peer auth)
        conn = psycopg2.connect(
            dbname=cfg["dbname"],
            user=cfg["user"]
        )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create table
    create_table(cur, conn)

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    if stock_syms:
        t_s, p_s, f_s = load_ttm_cash_flow(stock_syms, cur, conn)
        logging.info(f"Stocks — total: {t_s}, processed: {p_s}, failed: {len(f_s)}")

    # Load ETF symbols (if available)
    try:
        cur.execute("SELECT symbol FROM etf_symbols;")
        etf_syms = [r["symbol"] for r in cur.fetchall()]
        if etf_syms:
            t_e, p_e, f_e = load_ttm_cash_flow(etf_syms, cur, conn)
            logging.info(f"ETFs — total: {t_e}, processed: {p_e}, failed: {len(f_e)}")
    except Exception as e:
        logging.info(f"No ETF symbols table or error: {e}")
        conn.rollback()  # Recover from failed transaction
        cur = conn.cursor(cursor_factory=RealDictCursor)  # Create new cursor

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