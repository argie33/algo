#!/usr/bin/env python3
# Load earnings guidance data - tracks guidance raises and cuts
# Monitors when companies update their forward earnings guidance
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

SCRIPT_NAME = "loadguidance.py"

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
    """Ensure guidance_changes table exists."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS guidance_changes;")
        cur.execute("""
            CREATE TABLE guidance_changes (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                guidance_date DATE,
                prior_guidance NUMERIC(10, 2),
                new_guidance NUMERIC(10, 2),
                guidance_change NUMERIC(10, 2),
                change_pct NUMERIC(8, 4),
                guidance_type VARCHAR(50),
                announcement_text TEXT,
                source VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cur.execute("CREATE INDEX idx_guidance_symbol ON guidance_changes (symbol);")
        cur.execute("CREATE INDEX idx_guidance_date ON guidance_changes (guidance_date);")
    conn.commit()

@retry(max_attempts=3, initial_delay=2, backoff=2)
def process_symbol(symbol, conn):
    """Track guidance changes by monitoring estimate revisions."""
    yf_symbol = symbol.upper().replace(".", "-")
    ticker = yf.Ticker(yf_symbol)

    try:
        # Get current estimates and trends
        info = ticker.info
        if not info:
            return 0
    except Exception as e:
        raise e

    guidance_records = []

    # Track forward EPS guidance
    try:
        forward_eps = info.get('forwardEps')
        trailing_eps = info.get('trailingEps')

        if forward_eps and trailing_eps:
            change = forward_eps - trailing_eps
            change_pct = (change / trailing_eps * 100) if trailing_eps else 0

            guidance_records.append((
                symbol,
                pd.Timestamp.now().date(),
                trailing_eps,
                forward_eps,
                change,
                change_pct,
                'EPS',
                f"Forward EPS: {forward_eps}, Trailing EPS: {trailing_eps}",
                'yfinance'
            ))
    except Exception as e:
        logger.debug(f"Error processing forward EPS for {symbol}: {e}")

    # Track target price guidance
    try:
        target_mean = info.get('targetMeanPrice')
        current_price = info.get('currentPrice')

        if target_mean and current_price:
            upside = target_mean - current_price
            upside_pct = (upside / current_price * 100) if current_price else 0

            guidance_records.append((
                symbol,
                pd.Timestamp.now().date(),
                current_price,
                target_mean,
                upside,
                upside_pct,
                'TARGET_PRICE',
                f"Target: {target_mean}, Current: {current_price}",
                'yfinance'
            ))
    except Exception as e:
        logger.debug(f"Error processing target price for {symbol}: {e}")

    if not guidance_records:
        return 0

    # Insert guidance changes
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO guidance_changes
            (symbol, guidance_date, prior_guidance, new_guidance, guidance_change,
             change_pct, guidance_type, announcement_text, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, guidance_records)
    conn.commit()

    return len(guidance_records)

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
        total_guidance = 0

        logger.info(f"Loading guidance data for {total_symbols} symbols")

        for i, sym in enumerate(symbols):
            try:
                if (i + 1) % 100 == 0:
                    logger.info(f"Progress: {i + 1}/{total_symbols} - {get_rss_mb():.1f} MB RSS")

                guid_count = process_symbol(sym, conn)
                if guid_count is not None:
                    total_guidance += guid_count
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
        logger.info(f"Guidance — total: {total_guidance}, processed: {processed}, failed: {failed}")
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
