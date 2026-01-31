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

# Exponential backoff for rate limits (60s → 90s → 135s → 300s)
RATE_LIMIT_BACKOFF = [60, 90, 135, 300]

class RateLimitError(Exception):
    """Exception raised when yfinance returns rate limit error"""
    pass

def get_db_config():
    """Get database configuration from AWS Secrets Manager or environment variables.

    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager") \
                             .get_secret_value(SecretId=db_secret_arn)["SecretString"]
            sec = json.loads(secret_str)
            logging.info("Using AWS Secrets Manager for database config")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")

    # Fall back to environment variables
    logging.info("Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks")
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

def get_income_statement_data(symbol: str) -> Optional[pd.DataFrame]:
    """Get annual income statement data using proper yfinance API with fallback methods"""
    try:
        # Convert ticker format for yfinance (e.g., BRK.B → BRK-B)

        yf_symbol = symbol.replace(".", "-").replace("$", "-").upper()

        ticker = yf.Ticker(yf_symbol)
        
        # Try multiple methods in order of preference
        methods_to_try = [
            ('income_stmt', 'annual income statement (new method)'),
            ('financials', 'annual income statement (legacy method)'),
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
        error_str = str(e).lower()
        # Detect rate limit errors
        if "too many requests" in error_str or "rate limit" in error_str or "429" in error_str:
            raise RateLimitError(f"Rate limited while fetching {symbol}: {e}")
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
                    symbol,
                    safe_date,
                    str(item_name),
                    safe_value
                ))
    
    logging.info(f"Processed {symbol}: {valid_dates} valid dates, {valid_values}/{total_values} valid values, {len(processed_data)} records")
    return processed_data

def load_annual_income_statement(symbols: List[str], cur, conn) -> Tuple[int, int, List[str]]:
    """Load annual income statement data for given symbols with exponential backoff"""
    total = len(symbols)
    logging.info(f"Loading annual income statement for {total} symbols with exponential backoff")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 10, 0  # NO static pause - only backoff on errors
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE
    global_rate_limit_backoff_idx = 0

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")

        for symbol in batch:
            success = False
            rate_limit_backoff_idx = 0

            while rate_limit_backoff_idx < len(RATE_LIMIT_BACKOFF):
                try:
                    # Clean symbol for yfinance (handle special characters)
                    yf_symbol = symbol.replace('.', '-').replace('$', '-P').upper()

                    income_statement = get_income_statement_data(yf_symbol)
                    if income_statement is None:
                        break

                    # Process the data
                    income_statement_data = process_income_statement_data(symbol, income_statement)

                    if income_statement_data:
                        # Transform pivot data to denormalized format
                        # Group by (symbol, date) and extract key fields
                        grouped = {}
                        for sym, date, item_name, value in income_statement_data:
                            key = (sym, date)
                            if key not in grouped:
                                grouped[key] = {}
                            item_lower = str(item_name).lower()
                            if 'revenue' in item_lower:
                                grouped[key]['revenue'] = value
                            elif 'operating income' in item_lower:
                                grouped[key]['operating_income'] = value
                            elif 'pretax income' in item_lower or 'income before' in item_lower:
                                grouped[key]['pretax_income'] = value
                            elif 'net income' in item_lower and 'noncontrolling' not in item_lower:
                                grouped[key]['net_income'] = value
                            elif 'eps' in item_lower or 'diluted eps' in item_lower:
                                grouped[key]['eps'] = value

                        # Convert to insert tuples
                        insert_data = []
                        for (sym, date), fields in grouped.items():
                            insert_data.append((
                                sym,
                                date,
                                fields.get('revenue'),
                                fields.get('operating_income'),
                                fields.get('pretax_income'),
                                fields.get('net_income'),
                                fields.get('eps')
                            ))

                        if insert_data:
                            # Insert data
                            execute_values(cur, """
                                INSERT INTO annual_income_statement (symbol, date, revenue, operating_income, pretax_income, net_income, eps)
                                VALUES %s
                                ON CONFLICT (symbol, date) DO UPDATE SET
                                    revenue = COALESCE(EXCLUDED.revenue, annual_income_statement.revenue),
                                    operating_income = COALESCE(EXCLUDED.operating_income, annual_income_statement.operating_income),
                                    pretax_income = COALESCE(EXCLUDED.pretax_income, annual_income_statement.pretax_income),
                                    net_income = COALESCE(EXCLUDED.net_income, annual_income_statement.net_income),
                                    eps = COALESCE(EXCLUDED.eps, annual_income_statement.eps),
                                    updated_at = NOW()
                            """, insert_data)
                            conn.commit()
                            processed += 1
                            logging.info(f"✓ Successfully processed {symbol} ({len(insert_data)} records)")
                            success = True
                            break
                    else:
                        logging.warning(f"✗ No valid data found for {symbol} after processing")
                        break

                except RateLimitError as e:
                    wait_time = RATE_LIMIT_BACKOFF[rate_limit_backoff_idx]
                    logging.warning(f"Rate limited for {symbol}: {e}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    rate_limit_backoff_idx += 1
                    continue

                except Exception as e:
                    logging.warning(f"Error processing {symbol}: {e}")
                    # CRITICAL: Rollback on error to prevent "transaction aborted" state
                    try:
                        conn.rollback()
                        logging.debug(f"Transaction rolled back for {symbol}")
                    except Exception as rb_error:
                        logging.warning(f"Rollback failed: {rb_error}")
                    break

            if not success:
                failed.append(symbol)
                
        gc.collect()
        log_mem(f"Batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, processed, failed

def create_table(cur, conn):
    """Create the annual income statement table if it doesn't exist"""
    logging.info("Creating annual income statement table if needed...")
    try:
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS annual_income_statement (
                symbol VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                revenue DOUBLE PRECISION,
                operating_income DOUBLE PRECISION,
                pretax_income DOUBLE PRECISION,
                net_income DOUBLE PRECISION,
                eps DOUBLE PRECISION,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY(symbol, date)
            );

            CREATE INDEX IF NOT EXISTS idx_annual_income_statement_symbol ON annual_income_statement(symbol);
            CREATE INDEX IF NOT EXISTS idx_annual_income_statement_date ON annual_income_statement(date);
        """
        cur.execute(create_table_sql)
        conn.commit()
        logging.info("Created annual income statement table")
    except Exception as e:
        logging.info(f"Table likely exists: {e}")
        # Rollback to prevent transaction abort state
        try:
            conn.rollback()
        except Exception as rb_error:
            logging.warning(f"Rollback failed: {rb_error}")

if __name__ == "__main__":
    log_mem("startup")

    # Connect to DB with socket fallback
    cfg = get_db_config()
    try:
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
    except psycopg2.OperationalError:
        # Socket auth fallback for local development
        conn = psycopg2.connect(
            dbname=cfg["dbname"],
            user="stocks"
        )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create table
    try:
        create_table(cur, conn)
    except Exception as e:
        logging.warning(f"Failed to create table: {e}")
        pass

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