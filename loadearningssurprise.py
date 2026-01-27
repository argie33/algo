#!/usr/bin/env python3
# Load earnings surprise data - tracks EPS beats and misses
# Monitors actual reported EPS vs analyst estimates
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

SCRIPT_NAME = "loadearningssurprise.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - INFO - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

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
                        time.sleep(delay)
                        delay *= backoff
                    else:
                        logger.debug(f"{f.__name__} failed for {symbol}")
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
    """Ensure earnings_surprises table exists."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS earnings_surprises;")
        cur.execute("""
            CREATE TABLE earnings_surprises (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                earnings_date DATE,
                fiscal_quarter VARCHAR(20),
                actual_eps NUMERIC(10, 4),
                estimated_eps NUMERIC(10, 4),
                eps_surprise NUMERIC(10, 4),
                surprise_pct NUMERIC(8, 4),
                actual_revenue NUMERIC(18, 2),
                estimated_revenue NUMERIC(18, 2),
                revenue_surprise NUMERIC(18, 2),
                surprise_direction VARCHAR(20),
                details TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cur.execute("CREATE INDEX idx_surprise_symbol ON earnings_surprises (symbol);")
        cur.execute("CREATE INDEX idx_surprise_date ON earnings_surprises (earnings_date);")
    conn.commit()

@retry(max_attempts=3, initial_delay=2, backoff=2)
def process_symbol(symbol, conn):
    """Track earnings surprises for a symbol."""
    yf_symbol = symbol.upper().replace(".", "-")
    ticker = yf.Ticker(yf_symbol)

    try:
        info = ticker.info
        if not info:
            return 0
    except Exception as e:
        raise e

    surprise_records = []

    # Track last earnings surprise
    try:
        actual_eps = info.get('trailingEps')
        forward_eps = info.get('forwardEps')

        if actual_eps and forward_eps:
            surprise = actual_eps - forward_eps
            surprise_pct = (surprise / forward_eps * 100) if forward_eps else 0

            # Determine if beat or miss
            direction = "beat" if surprise > 0 else "miss" if surprise < 0 else "inline"

            last_earnings_date = info.get('mostRecentQuarter')
            if last_earnings_date:
                last_earnings_date = pd.to_datetime(last_earnings_date).date()
            else:
                last_earnings_date = pd.Timestamp.now().date()

            surprise_records.append((
                symbol,
                last_earnings_date,
                info.get('currentFiscalYearEnd', ''),
                actual_eps,
                forward_eps,
                surprise,
                surprise_pct,
                None,
                None,
                None,
                direction,
                f"Actual EPS: {actual_eps}, Estimated EPS: {forward_eps}",
            ))
    except Exception as e:
        logger.debug(f"Error processing earnings data for {symbol}: {e}")

    if not surprise_records:
        return 0

    # Insert surprise records
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO earnings_surprises
            (symbol, earnings_date, fiscal_quarter, actual_eps, estimated_eps,
             eps_surprise, surprise_pct, actual_revenue, estimated_revenue,
             revenue_surprise, surprise_direction, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, surprise_records)
    conn.commit()

    return len(surprise_records)

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
        processed = 0
        failed = 0
        total_surprises = 0

        logger.info(f"Loading earnings surprises for {total_symbols} symbols")

        for i, sym in enumerate(symbols):
            try:
                if (i + 1) % 100 == 0:
                    logger.info(f"Progress: {i + 1}/{total_symbols} - {get_rss_mb():.1f} MB RSS")

                surp_count = process_symbol(sym, conn)
                if surp_count is not None:
                    total_surprises += surp_count
                    processed += 1
                else:
                    failed += 1

                if get_rss_mb() > 1000:
                    time.sleep(0.3)
                else:
                    time.sleep(0.05)
            except Exception:
                failed += 1

        update_last_run(conn)
        logger.info(f"[MEM] peak RSS: {get_rss_mb():.1f} MB")
        logger.info(f"Earnings Surprises — total: {total_surprises}, processed: {processed}, failed: {failed}")
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
