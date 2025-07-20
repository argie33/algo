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

SCRIPT_NAME = "loadannualincomestatement.py"
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
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec.get("port", 5432)),
        sec["dbname"]
    )

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

def get_income_statement_data(symbol: str) -> Optional[pd.DataFrame]:
    """Get annual income statement data using proper yfinance API with fallback methods"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Try multiple methods in order of preference
        methods_to_try = [
            ('income_stmt', 'annual income statement (new method)')
            ('financials', 'annual income statement (legacy method)')
        ]
        
        income_statement = None
        
        for method_name, description in methods_to_try:
            try:
                if hasattr(ticker, method_name):
                    logging.info(f"Trying {method_name} for {symbol}")
                    income_statement = getattr(ticker, method_name)
                    
                    if income_statement is not None and not income_statement.empty:
                        logging.info(f"✓ Successfully got data using {method_name} for {symbol}")
                        break
                    else:
                        logging.warning(f"{method_name} returned empty data for {symbol}")
                else:
                    logging.warning(f"Method {method_name} not available for {symbol}")
            except Exception as e:
                logging.warning(f"Error with {method_name} for {symbol}: {e}")
                continue
        
        if income_statement is None or income_statement.empty:
            logging.warning(f"No income statement data returned by any method for {symbol}")
            return None
        
        # Check if DataFrame contains any actual data (not all NaN)
        if income_statement.isna().all().all():
            logging.warning(f"Income statement data is all NaN for {symbol}")
            return None
            
        # Check if we have at least one column with data
        valid_columns = [col for col in income_statement.columns if not income_statement[col].isna().all()]
        if not valid_columns:
            logging.warning(f"No valid income statement columns found for {symbol}")
            return None
            
        # Sort columns by date (most recent first)
        income_statement = income_statement.reindex(sorted(income_statement.columns, reverse=True), axis=1)
        
        logging.info(f"Retrieved income statement data for {symbol}: {len(income_statement.columns)} periods, {len(income_statement.index)} line items")
        return income_statement
        
    except Exception as e:
        logging.error(f"Error fetching income statement for {symbol}: {e}")
        return None

def process_income_statement_data(symbol: str, income_statement: pd.DataFrame) -> List[Tuple]:
    """Process income statement DataFrame into database-ready tuples"""
    processed_data = []
    valid_dates = 0
    total_values = 0
    valid_values = 0
    
    for date_col in income_statement.columns:
        safe_date = safe_convert_date(date_col)
        if safe_date is None:
            logging.debug(f"Skipping invalid date column for {symbol}: {date_col}")
            continue
        valid_dates += 1
            
        for item_name in income_statement.index:
            value = income_statement.loc[item_name, date_col]
            total_values += 1
            safe_value = safe_convert_to_float(value)
            
            if safe_value is not None:
                valid_values += 1
                processed_data.append((
                    symbol
                    safe_date
                    str(item_name)
                    safe_value
                ))
    
    logging.info(f"Processed {symbol}: {valid_dates} valid dates, {valid_values}/{total_values} valid values, {len(processed_data)} records")
    return processed_data

def load_annual_income_statement(symbols: List[str], cur, conn) -> Tuple[int, int, List[str]]:
    """Load annual income statement data for given symbols"""
    total = len(symbols)
    logging.info(f"Loading annual income statement for {total} symbols")
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
                    
                    income_statement = get_income_statement_data(yf_symbol)
                    if income_statement is None:
                        break
                    
                    # Process the data
                    income_statement_data = process_income_statement_data(symbol, income_statement)
                    
                    if income_statement_data:
                        # Insert data
                        execute_values(cur, """
                            INSERT INTO annual_income_statement (symbol, date, item_name, value)
                            VALUES %s
                            ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                                value = EXCLUDED.value
                                updated_at = NOW()
                        """, income_statement_data)
                        conn.commit()
                        processed += 1
                        logging.info(f"✓ Successfully processed {symbol} ({len(income_statement_data)} records)")
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
                
        gc.collect()
        log_mem(f"Batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, processed, failed

def create_table(cur, conn):
    """Create the annual income statement table"""
    logging.info("Creating annual income statement table...")
    cur.execute("DROP TABLE IF EXISTS annual_income_statement CASCADE;")
    
    create_table_sql = """
        CREATE TABLE annual_income_statement (
            symbol VARCHAR(20) NOT NULL
            date DATE NOT NULL
            item_name TEXT NOT NULL
            value DOUBLE PRECISION NOT NULL
            created_at TIMESTAMP DEFAULT NOW()
            updated_at TIMESTAMP DEFAULT NOW()
            PRIMARY KEY(symbol, date, item_name)
        );
        
        CREATE INDEX idx_annual_income_statement_symbol ON annual_income_statement(symbol);
        CREATE INDEX idx_annual_income_statement_date ON annual_income_statement(date);
        CREATE INDEX idx_annual_income_statement_item ON annual_income_statement(item_name);
    """
    cur.execute(create_table_sql)
    conn.commit()
    logging.info("Created annual income statement table")

if __name__ == "__main__":
    log_mem("startup")

    # Connect to DB - IDENTICAL to loadcalendar.py
    user, pwd, host, port, dbname = get_db_config()
    
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"🔌 Connection attempt {attempt}/{max_retries} to {host}:{port}")
            
            # Test basic connectivity first
            logging.info("🔌 Testing basic network connectivity...")
            import socket
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(10)
            test_result = test_socket.connect_ex((host, port))
            
            if test_result == 0:
                logging.info("✅ Network connectivity test passed")
                local_addr = test_socket.getsockname()
                peer_addr = test_socket.getpeername()
                logging.info(f"🔍 Local socket: {local_addr[0]}:{local_addr[1]}")
                logging.info(f"🔍 Remote socket: {peer_addr[0]}:{peer_addr[1]}")
            else:
                logging.error(f"❌ Network connectivity test failed with code: {test_result}")
                if test_result == 111:
                    logging.error("🔍 DIAGNOSIS: Connection refused - PostgreSQL not running or not accepting connections")
                elif test_result == 113:
                    logging.error("🔍 DIAGNOSIS: No route to host - network routing or security group issue")
                elif test_result == 110:
                    logging.error("🔍 DIAGNOSIS: Connection timeout - security group blocking or RDS not accessible")
                else:
                    logging.error(f"🔍 DIAGNOSIS: Unknown network error code {test_result}")
            test_socket.close()
            
            # Clean connection pattern (auto-negotiate SSL) - IDENTICAL to loadcalendar.py
            conn = psycopg2.connect(
                host=host, port=port,
                user=user, password=pwd,
                dbname=dbname,
                cursor_factory=RealDictCursor
            )
            logging.info("✅ Database connection established successfully")
            break
            
        except psycopg2.OperationalError as e:
            error_msg = str(e)
            logging.error(f"❌ PostgreSQL connection error (attempt {attempt}/{max_retries}): {error_msg}")
            
            if attempt < max_retries:
                logging.info(f"⏳ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                logging.error(f"❌ All {max_retries} connection attempts failed")
                raise
    
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create table
    create_table(cur, conn)

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    if stock_syms:
        t_s, p_s, f_s = load_annual_income_statement(stock_syms, cur, conn)
        logging.info(f"Stocks — total: {t_s}, processed: {p_s}, failed: {len(f_s)}")

    # Load ETF symbols (if available)
    try:
        cur.execute("SELECT symbol FROM etf_symbols;")
        etf_syms = [r["symbol"] for r in cur.fetchall()]
        if etf_syms:
            t_e, p_e, f_e = load_annual_income_statement(etf_syms, cur, conn)
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