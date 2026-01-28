#!/usr/bin/env python3
# Load insider transaction data from SEC Form 4 filings via yfinance
# Tracks insider buying/selling activity as a leading indicator of company health
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

# Script metadata & logging setup
SCRIPT_NAME = "loadinsidertransactions.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - INFO - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

# Environment-driven configuration
DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")

def get_db_config():
    """Fetch database config from Secrets Manager or environment."""
    if DB_SECRET_ARN:
        try:
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
        except Exception as e:
            logger.warning(f"Failed to fetch from Secrets Manager: {e}, using environment variables")

    return (
        os.getenv("DB_USER", "stocks"),
        os.getenv("DB_PASSWORD", "bed0elAn"),
        os.getenv("DB_HOST", "localhost"),
        int(os.getenv("DB_PORT", 5432)),
        os.getenv("DB_NAME", "stocks")
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
                    if attempts < max_attempts:
                        logger.debug(f"{f.__name__} failed for {symbol} (attempt {attempts}/{max_attempts}), retrying...")
                        time.sleep(delay)
                        delay *= backoff
                    else:
                        logger.warning(f"{f.__name__} failed for {symbol} after {max_attempts} attempts")
                        return None
            return None
        return wrapper
    return decorator

def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def ensure_table(conn):
    """Ensure insider_transactions table exists with proper schema."""
    with conn.cursor() as cur:
        # Create table if not exists (never drop - avoid data loss on crash)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS insider_transactions (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                insider_name VARCHAR(255),
                position VARCHAR(100),
                transaction_type VARCHAR(50),
                shares BIGINT,
                value NUMERIC(15, 2),
                transaction_date DATE,
                ownership_type VARCHAR(20),
                transaction_text TEXT,
                url TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        # Create indexes for faster lookups (idempotent - won't fail if exists)
        try:
            cur.execute("CREATE INDEX idx_insider_symbol ON insider_transactions (symbol);")
        except psycopg2.Error:
            pass  # Index already exists
        try:
            cur.execute("CREATE INDEX idx_insider_date ON insider_transactions (transaction_date);")
        except psycopg2.Error:
            pass  # Index already exists
        try:
            cur.execute("CREATE INDEX idx_insider_name ON insider_transactions (insider_name);")
        except psycopg2.Error:
            pass  # Index already exists
    conn.commit()

@retry(max_attempts=3, initial_delay=2, backoff=2)
def process_symbol(symbol, conn):
    """Fetch insider transactions for a symbol and insert into database."""
    yf_symbol = symbol.upper().replace(".", "-")
    ticker = yf.Ticker(yf_symbol)

    try:
        insider_data = ticker.insider_transactions
        if insider_data is None or insider_data.empty:
            return False
    except Exception as e:
        raise e

    transactions = []
    for idx, row in insider_data.iterrows():
        try:
            # Parse transaction details
            insider_name = row.get('Owner Name', '')
            shares = int(row.get('Shares', 0)) if pd.notna(row.get('Shares')) else 0
            value = float(row.get('Value', 0)) if pd.notna(row.get('Value')) else 0.0
            transaction_date = pd.to_datetime(idx.date()) if hasattr(idx, 'date') else pd.to_datetime(idx)
            transaction_type = row.get('Transaction', '')
            ownership_type = row.get('Ownership', '')

            transactions.append((
                symbol,
                insider_name,
                row.get('Title', ''),
                transaction_type,
                shares,
                value,
                transaction_date.date(),
                ownership_type,
                str(row),
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&symbol={yf_symbol}&type=4&dateb=&owner=exclude&count=100"
            ))
        except Exception as e:
            logger.warning(f"Error parsing insider transaction for {symbol}: {e}")
            continue

    if not transactions:
        return False

    # Batch insert transactions
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO insider_transactions
            (symbol, insider_name, position, transaction_type, shares, value,
             transaction_date, ownership_type, transaction_text, url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, transactions)
    conn.commit()

    return True

def update_last_run(conn):
    """Record script execution timestamp."""
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
        ssl_mode = "disable" if host == "localhost" else "require"

        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=pwd,
            dbname=dbname,
            sslmode=ssl_mode,
            cursor_factory=DictCursor
        )
        conn.set_session(autocommit=False)

        ensure_table(conn)
        logger.info(f"[MEM] startup: {get_rss_mb():.1f} MB RSS")

        # Get all stock symbols
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol;")
            symbols = [r["symbol"] for r in cur.fetchall()]

        total_symbols = len(symbols)
        symbols_with_data = 0
        symbols_skipped = 0

        logger.info(f"Loading insider transactions for {total_symbols} symbols (REAL DATA ONLY)")

        for i, sym in enumerate(symbols):
            if (i + 1) % 500 == 0:
                logger.info(f"Progress: {i + 1}/{total_symbols} - {get_rss_mb():.1f} MB RSS")

            try:
                has_data = process_symbol(sym, conn)
                if has_data:
                    symbols_with_data += 1
                else:
                    # No data - SKIP (don't insert placeholder)
                    symbols_skipped += 1

                # Adaptive throttling
                if get_rss_mb() > 1000:
                    time.sleep(0.3)
                else:
                    time.sleep(0.05)
            except Exception as e:
                logger.error(f"ERROR processing {sym}: {e}")
                symbols_skipped += 1

        update_last_run(conn)
        logger.info(f"[MEM] peak RSS: {get_rss_mb():.1f} MB")
        logger.info(f"Insider Transactions — REAL DATA ONLY: {symbols_with_data} symbols with data, {symbols_skipped} skipped (no data)")
        logger.info("Done.")
    except Exception:
        logger.exception("Fatal error in main()")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                logger.exception("Error closing connection")

if __name__ == "__main__":
    main()
