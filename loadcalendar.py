#!/usr/bin/env python3
# TRIGGER: 2026-01-28_193000 - CRITICAL DATA LOSS FIX - Calendar data now crash-safe
# Load calendar data - trigger v2.7 - production ready with data preservation
# FIXED: 2026-01-28 - Removed DROP TABLE vulnerability - historical calendar events preserved
# TRIGGER DEPLOY: loadcalendar with data loss fix applied
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
SCRIPT_NAME = "loadcalendar.py"

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

def get_db_config():
    """Get database configuration - works in AWS and locally.

    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    # Try AWS Secrets Manager first
    if db_secret_arn and aws_region:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logging.info(f"Using AWS Secrets Manager for database config")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "database": sec["dbname"]
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
        "database": os.environ.get("DB_NAME", "stocks")
    }


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
    """Ensure calendar tables exist (never drop - avoid data loss)."""
    with conn.cursor() as cur:
        # calendar events
        cur.execute("""
            CREATE TABLE IF NOT EXISTS calendar_events (
                id          SERIAL PRIMARY KEY,
                symbol     VARCHAR(10) NOT NULL,
                event_type VARCHAR(50) NOT NULL,
                start_date TIMESTAMPTZ,
                end_date   TIMESTAMPTZ,
                title      TEXT,
                fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        # Create index on symbol for faster lookups (idempotent)
        try:
            cur.execute("""
                CREATE INDEX idx_calendar_events_symbol
                ON calendar_events (symbol);
            """)
        except Exception as e:
            logging.debug(f"Index idx_calendar_events_symbol already exists or could not be created: {e}")
            pass  # Index already exists
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

def process_symbol(symbol, conn):
    """Fetch calendar events via yfinance and insert into PostgreSQL - REAL DATA ONLY."""
    yf_symbol = symbol.upper().replace(".", "-")
    ticker = yf.Ticker(yf_symbol)

    # Try to get calendar data
    try:
        calendar_data = ticker.calendar
        if calendar_data is None or not isinstance(calendar_data, dict):
            logger.debug(f"No calendar data for {symbol}")
            return False
    except Exception as e:
        logger.error(f"ERROR fetching calendar data for {symbol}: {e}")
        return False

    events_to_insert = []

    # Process earnings events
    if 'Earnings Date' in calendar_data:
        earnings_date = calendar_data.get('Earnings Date')
        # Handle earnings date which can be a single value or a range
        if isinstance(earnings_date, list):
            start_date = pd.to_datetime(earnings_date[0]) if earnings_date else None
            end_date = pd.to_datetime(earnings_date[1]) if len(earnings_date) > 1 else start_date
        else:
            start_date = pd.to_datetime(earnings_date)
            end_date = start_date

        earnings_title = "Q" + str(calendar_data.get('Earnings Quarter', '')) + " Earnings"
        events_to_insert.append((
            symbol,
            'earnings',
            start_date,
            end_date,
            earnings_title
        ))

    # Process dividend events
    if 'Dividend Date' in calendar_data:
        div_date = pd.to_datetime(calendar_data.get('Dividend Date'))
        ex_date = pd.to_datetime(calendar_data.get('Ex-Dividend Date'))
        div_amount = calendar_data.get('Dividend', 0.0)
        if div_date is not None:
            events_to_insert.append((
                symbol,
                'dividend',
                div_date,
                div_date,
                f"Dividend Payment ${div_amount:.4f}"
            ))
        if ex_date is not None:
            events_to_insert.append((
                symbol,
                'dividend',
                ex_date,
                ex_date,
                f"Ex-Dividend ${div_amount:.4f}"
            ))

    # Add any splits using splits property
    try:
        splits = ticker.splits
        if not splits.empty:
            for date, ratio in splits.items():
                events_to_insert.append((
                    symbol,
                    'split',
                    pd.to_datetime(date),
                    pd.to_datetime(date),
                    f"{ratio}:1 Stock Split"
                ))
    except Exception as e:
        logger.debug(f"Failed to fetch splits for {symbol}: {e}")

    if not events_to_insert:
        logger.debug(f"No calendar events found for {symbol}")
        return False

    # Batch insert all events
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO calendar_events
            (symbol, event_type, start_date, end_date, title)
            VALUES (%s, %s, %s, %s, %s)
            """,
            events_to_insert
        )
    conn.commit()

    logger.debug(f"Successfully processed {len(events_to_insert)} calendar events for {symbol}")
    return True

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
        cfg = get_db_config()

        # For local connections, use disable SSL; for remote use require
        ssl_mode = "disable" if cfg["host"] == "localhost" else "require"

        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            dbname=cfg["database"],
            sslmode=ssl_mode,
            cursor_factory=DictCursor
        )

        # Set a larger cursor size for better performance
        conn.set_session(autocommit=False)

        ensure_tables(conn)

        log_mem("Before fetching symbols")
        with conn.cursor() as cur:
            # Get all stock symbols
            cur.execute("""
                SELECT DISTINCT symbol
                FROM stock_symbols
                ORDER BY symbol;
            """)
            symbols = [r["symbol"] for r in cur.fetchall()]
        log_mem("After fetching symbols")

        total_symbols = len(symbols)
        processed_with_data = 0
        symbols_skipped = 0

        for i, sym in enumerate(symbols):
            if (i + 1) % 500 == 0:
                logger.info(f"Progress: {i + 1}/{total_symbols} - {get_rss_mb():.1f} MB RSS")

            try:
                success = process_symbol(sym, conn)
                if success:
                    processed_with_data += 1
                else:
                    # No data - SKIP (don't insert placeholder)
                    symbols_skipped += 1

                # Adaptive sleep based on memory usage
                if get_rss_mb() > 1000:  # If using more than 1GB
                    time.sleep(0.5)
                else:
                    time.sleep(0.1)
            except Exception as e:
                logger.error(f"ERROR processing {sym}: {e}")
                symbols_skipped += 1

        update_last_run(conn)
        logger.info(f"Calendar — REAL DATA ONLY: {processed_with_data} symbols with data, {symbols_skipped} skipped (no data)")
    except Exception as e:
        logger.exception(f"Fatal error in main(): {e}")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.exception(f"Error closing database connection: {e}")
        log_mem("End of script")
        logger.info("loadcalendar complete.")

if __name__ == "__main__":
    main()
