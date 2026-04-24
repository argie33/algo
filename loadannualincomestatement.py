#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import gc
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False
from datetime import datetime, date
from typing import List, Tuple, Optional, Dict

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import boto3
import yfinance as yf
import pandas as pd

# Load environment variables from .env.local if it exists
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

SCRIPT_NAME = "loadannualincomestatement.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_rss_mb():
    """Get RSS memory in MB, cross-platform."""
    if not HAS_RESOURCE:
        try:
            import psutil
            return psutil.Process().memory_info().rss / (1024 * 1024)
        except:
            return 0
    usage = resource.getrusage(resource.RUSAGE_SELF)
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
    aws_region = os.environ.get("AWS_REGION", "us-east-1")

    if db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region) \
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
                        logging.info(f"[OK] Successfully got data using {method_name} for {symbol}")
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
    """Load annual income statement data for given symbols with parallelization"""
    total = len(symbols)
    logging.info(f"Loading annual income statement for {total} symbols with ThreadPoolExecutor parallelization")

    # Global rate limiter (max 20 concurrent HTTP requests to yfinance)
    rate_limiter = threading.Semaphore(20)

    # Get connection params for worker threads
    connect_params = {
        "host": cur.connection.get_dsn_parameters()['host'] if hasattr(cur.connection, 'get_dsn_parameters') else os.getenv('DB_HOST', 'localhost'),
        "dbname": cur.connection.get_dsn_parameters()['dbname'] if hasattr(cur.connection, 'get_dsn_parameters') else os.getenv('DB_NAME', 'stocks'),
        "user": cur.connection.get_dsn_parameters()['user'] if hasattr(cur.connection, 'get_dsn_parameters') else os.getenv('DB_USER', 'stocks'),
        "password": os.getenv('DB_PASSWORD', '')
    }

    def process_symbol_worker(symbol: str) -> Tuple[str, bool]:
        """Process a single symbol in a thread. Returns (symbol, success)"""
        try:
            thread_conn = psycopg2.connect(**connect_params)
            thread_conn.autocommit = False
            thread_cur = thread_conn.cursor(cursor_factory=RealDictCursor)

            rate_limit_backoff_idx = 0

            while rate_limit_backoff_idx < len(RATE_LIMIT_BACKOFF):
                try:
                    # Clean symbol for yfinance
                    yf_symbol = symbol.replace('.', '-').replace('$', '-P').upper()

                    # Acquire rate limiter
                    rate_limiter.acquire()
                    try:
                        income_statement = get_income_statement_data(yf_symbol)
                    finally:
                        rate_limiter.release()

                    if income_statement is None:
                        break

                    # Process the data
                    income_statement_data = process_income_statement_data(symbol, income_statement)

                    if income_statement_data:
                        # Transform pivot data to denormalized format
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
                            execute_values(thread_cur, """
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
                            thread_conn.commit()
                            logging.info(f"[OK] {symbol} ({len(insert_data)} records)")
                            return (symbol, True)
                    else:
                        logging.warning(f"[FAIL] No valid data found for {symbol}")
                        break

                except RateLimitError as e:
                    wait_time = RATE_LIMIT_BACKOFF[rate_limit_backoff_idx]
                    logging.warning(f"Rate limited for {symbol}: waiting {wait_time}s...")
                    time.sleep(wait_time)
                    rate_limit_backoff_idx += 1
                    continue

                except Exception as e:
                    logging.warning(f"Error processing {symbol}: {str(e)[:100]}")
                    try:
                        thread_conn.rollback()
                    except:
                        pass
                    break

            return (symbol, False)

        except Exception as e:
            logging.error(f"Worker thread error for {symbol}: {str(e)[:100]}")
            return (symbol, False)

        finally:
            try:
                thread_conn.close()
            except:
                pass

    # Process symbols in parallel
    processed, failed = 0, []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_symbol_worker, symbol): symbol for symbol in symbols}

        for i, future in enumerate(as_completed(futures)):
            try:
                symbol, success = future.result()
                if success:
                    processed += 1
                else:
                    failed.append(symbol)

                if (i + 1) % 50 == 0:
                    logging.info(f"Progress: {processed}/{total} processed - {len(failed)} failed")

            except Exception as e:
                symbol = futures[future]
                logging.error(f"Exception in worker for {symbol}: {str(e)[:100]}")
                failed.append(symbol)

    gc.collect()
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