#!/usr/bin/env python3
import sys
import time
import logging
import functools
import os
import json
import resource

import boto3
import psycopg2
from psycopg2.extras import DictCursor
import yfinance as yf
import pandas as pd
import math

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadincomestmt.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

# -------------------------------
# Environment-driven configuration
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
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"]
    )

def retry(max_attempts=3, initial_delay=2, backoff=2):
    """Retry decorator with exponential backoff."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(symbol, conn, *args, **kwargs):
            attempts, delay = 0, initial_delay
            while attempts < max_attempts:
                try:
                    return f(symbol, conn, *args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logger.error(
                        f"{f.__name__} failed for {symbol} "
                        f"(attempt {attempts}/{max_attempts}): {e}",
                        exc_info=True
                    )
                    time.sleep(delay)
                    delay *= backoff
            raise RuntimeError(
                f"All {max_attempts} attempts failed for {f.__name__} with symbol {symbol}"
            )
        return wrapper
    return decorator

def clean_value(value):
    """Convert NaN or pandas NAs to None."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    return value

def ensure_tables(conn):
    """Drop & recreate income_stmt tables and ensure last_updated exists."""
    with conn.cursor() as cur:
        # income_stmt table
        cur.execute("DROP TABLE IF EXISTS income_stmt;")
        cur.execute("""
            CREATE TABLE income_stmt (
                id          SERIAL PRIMARY KEY,
                symbol      VARCHAR(10) NOT NULL,
                date        DATE NOT NULL,
                item_name   VARCHAR(255) NOT NULL,
                value       NUMERIC,
                fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        # Create index on symbol for faster lookups
        cur.execute("""
            CREATE INDEX idx_income_stmt_symbol 
            ON income_stmt (symbol);
        """)
        # Create index on date for faster lookups
        cur.execute("""
            CREATE INDEX idx_income_stmt_date 
            ON income_stmt (date);
        """)
        # last_updated
        cur.execute("""
            CREATE TABLE IF NOT EXISTS last_updated (
                script_name VARCHAR(255) PRIMARY KEY,
                last_run    TIMESTAMPTZ NOT NULL
            );
        """)
    conn.commit()

def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

@retry(max_attempts=3, initial_delay=2, backoff=2)
def process_symbol(symbol, conn):
    """Fetch annual income statement via yfinance and insert into PostgreSQL."""
    yf_symbol = symbol.upper().replace(".", "-")
    ticker = yf.Ticker(yf_symbol)

    # Try to get annual income statement data
    try:
        income_stmt = ticker.income_stmt
        if income_stmt is None or income_stmt.empty:
            logger.warning(f"No annual income statement data for {symbol}")
            return
    except Exception as e:
        logger.error(f"Error fetching annual income statement data for {symbol}: {e}")
        raise

    # Process each item in the annual income statement dataframe
    data_to_insert = []
    
    # Iterate through rows (items) and columns (dates)
    for item_name, row in income_stmt.iterrows():
        for date_col in income_stmt.columns:
            # Convert the pandas Timestamp to a Python date object
            date_str = pd.to_datetime(date_col).strftime('%Y-%m-%d')
            
            # Get the value for this item and date
            value = clean_value(row[date_col])
            
            # Only insert if we have a valid value
            if value is not None:
                data_to_insert.append((
                    symbol,
                    date_str,
                    str(item_name),
                    value
                ))
    
    if not data_to_insert:
        logger.info(f"No annual income statement data found for {symbol}")
        return
        
    # Batch insert all data
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO income_stmt
            (symbol, date, item_name, value)
            VALUES (%s, %s, %s, %s)
            """,
            data_to_insert
        )
    conn.commit()

    logger.info(f"Successfully processed {len(data_to_insert)} annual income statement records for {symbol}")

def update_last_run(conn):
    """Stamp the last run time in last_updated."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE
              SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME,))
    conn.commit()

def main():
    conn = None
    try:
        user, pwd, host, port, dbname = get_db_config()
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=pwd,
            dbname=dbname,
            sslmode="require",
            cursor_factory=DictCursor
        )
        
        # Set a larger cursor size for better performance
        conn.set_session(autocommit=False)
        
        ensure_tables(conn)

        log_mem("Before fetching symbols")
        with conn.cursor() as cur:
            # Only get active symbols to reduce processing
            cur.execute("""
                SELECT DISTINCT symbol 
                FROM stock_symbols 
                WHERE is_active = true
                ORDER BY symbol;
            """)
            symbols = [r["symbol"] for r in cur.fetchall()]
        log_mem("After fetching symbols")

        total_symbols = len(symbols)
        processed = 0
        failed = 0

        for sym in symbols:
            try:
                log_mem(f"Processing {sym} ({processed + 1}/{total_symbols})")
                process_symbol(sym, conn)
                processed += 1
                # Adaptive sleep based on memory usage
                if get_rss_mb() > 1000:  # If using more than 1GB
                    time.sleep(0.5)
                else:
                    time.sleep(0.1)
            except Exception:
                logger.exception(f"Failed to process {sym}")
                failed += 1
                if failed > total_symbols * 0.2:  # If more than 20% failed
                    logger.error("Too many failures, stopping process")
                    break

        update_last_run(conn)
        logger.info(f"Completed processing {processed}/{total_symbols} symbols with {failed} failures")
    except Exception:
        logger.exception("Fatal error in main()")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                logger.exception("Error closing database connection")
        log_mem("End of script")
        logger.info("loadincomestmt complete.")

if __name__ == "__main__":
    main()
