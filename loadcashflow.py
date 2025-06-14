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

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadcashflow.py"
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

def load_cash_flow_data(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading cash flow data for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 3, 0.5
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping = dict(zip(yq_batch, batch))

        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")
        for yq_sym, orig_sym in mapping.items():
            cash_flow = None  # Initialize cash_flow variable
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    cash_flow = ticker.cashflow
                    if cash_flow is None or cash_flow.empty:
                        raise ValueError("No cash flow data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        break  # Break instead of continue to skip processing
                    time.sleep(RETRY_DELAY)
            
            # Skip processing if cash_flow was not successfully retrieved
            if cash_flow is None or cash_flow.empty:
                logging.error(f"Skipping {orig_sym} - failed to retrieve cash flow after {MAX_BATCH_RETRIES} attempts")
                continue
            
            try:
                # Process cash flow data
                for col in cash_flow.columns:
                    period_end = col.strftime('%Y-%m-%d')
                    
                    # Extract values safely
                    def get_value(index_name):
                        return cash_flow.loc[index_name, col] if index_name in cash_flow.index else None
                    
                    # Insert cash flow data
                    cur.execute("""
                        INSERT INTO cash_flow (
                            ticker, period_end, operating_cash_flow, investing_cash_flow,
                            financing_cash_flow, end_cash_position, capital_expenditure,
                            issuance_of_capital_stock, issuance_of_debt, repayment_of_debt,
                            repurchase_of_capital_stock, free_cash_flow, net_income,
                            depreciation, changes_in_working_capital, stock_based_compensation
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (ticker, period_end) DO UPDATE SET
                            operating_cash_flow = EXCLUDED.operating_cash_flow,
                            investing_cash_flow = EXCLUDED.investing_cash_flow,
                            financing_cash_flow = EXCLUDED.financing_cash_flow
                    """, (
                        orig_sym, period_end,
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
                        get_value('Stock Based Compensation')
                    ))

                conn.commit()
                processed += 1
                logging.info(f"Successfully processed {orig_sym}")

            except Exception as e:
                logging.error(f"Failed to process {orig_sym}: {str(e)}")
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

    # Recreate table
    logging.info("Recreating cash flow table...")
    cur.execute("DROP TABLE IF EXISTS cash_flow CASCADE;")

    cur.execute("""
        CREATE TABLE cash_flow (
            ticker VARCHAR(10) NOT NULL,
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
            PRIMARY KEY(ticker, period_end)
        );
    """)

    conn.commit()

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_cash_flow_data(stock_syms, cur, conn)

    # Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, p_e, f_e = load_cash_flow_data(etf_syms, cur, conn)

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

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadcashflow.py"

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
    """Drop & recreate cash_flow tables and ensure last_updated exists."""
    with conn.cursor() as cur:
        # cash_flow table
        cur.execute("DROP TABLE IF EXISTS cash_flow;")
        cur.execute("""
            CREATE TABLE cash_flow (
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
            CREATE INDEX idx_cash_flow_symbol 
            ON cash_flow (symbol);
        """)
        # Create index on date for faster lookups
        cur.execute("""
            CREATE INDEX idx_cash_flow_date 
            ON cash_flow (date);
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
    """Fetch annual cash flow via yfinance and insert into PostgreSQL."""
    yf_symbol = symbol.upper().replace(".", "-")
    ticker = yf.Ticker(yf_symbol)

    # Try to get annual cash flow data
    try:
        cash_flow = ticker.cash_flow
        if cash_flow is None or cash_flow.empty:
            logger.warning(f"No annual cash flow data for {symbol}")
            return
    except Exception as e:
        logger.error(f"Error fetching annual cash flow data for {symbol}: {e}")
        raise

    # Process each item in the annual cash flow dataframe
    data_to_insert = []
    
    # Iterate through rows (items) and columns (dates)
    for item_name, row in cash_flow.iterrows():
        for date_col in cash_flow.columns:
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
        logger.info(f"No annual cash flow data found for {symbol}")
        return
        
    # Batch insert all data
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO cash_flow
            (symbol, date, item_name, value)
            VALUES (%s, %s, %s, %s)
            """,
            data_to_insert
        )
    conn.commit()

    logger.info(f"Successfully processed {len(data_to_insert)} annual cash flow records for {symbol}")

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
            # Get all symbols
            cur.execute("""
                SELECT DISTINCT symbol 
                FROM stock_symbols 
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
        logger.info("loadcashflow complete.")

if __name__ == "__main__":
    main()
