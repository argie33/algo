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
SCRIPT_NAME = "loadearnings.py"

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING"),
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
    """Drop & recreate earnings tables and ensure last_updated exists."""
    with conn.cursor() as cur:
        # earnings EPS
        cur.execute("DROP TABLE IF EXISTS earnings_eps;")
        cur.execute("""
            CREATE TABLE earnings_eps (
                id          SERIAL PRIMARY KEY,
                symbol      VARCHAR(10) NOT NULL,
                period      VARCHAR(20) NOT NULL,
                actual      DOUBLE PRECISION,
                estimate    DOUBLE PRECISION,
                fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        # earnings financial annual
        cur.execute("DROP TABLE IF EXISTS earnings_financial_annual;")
        cur.execute("""
            CREATE TABLE earnings_financial_annual (
                id          SERIAL PRIMARY KEY,
                symbol      VARCHAR(10) NOT NULL,
                period      VARCHAR(20) NOT NULL,
                revenue     BIGINT,
                revenue_estimate BIGINT,
                earnings    BIGINT,
                fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        # earnings financial quarterly
        cur.execute("DROP TABLE IF EXISTS earnings_financial_quarterly;")
        cur.execute("""
            CREATE TABLE earnings_financial_quarterly (
                id          SERIAL PRIMARY KEY,
                symbol      VARCHAR(10) NOT NULL,
                period      VARCHAR(20) NOT NULL,
                revenue     BIGINT,
                revenue_estimate BIGINT,
                earnings    BIGINT,
                fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
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
    """Fetch earnings via yfinance and insert into PostgreSQL."""
    yf_symbol = symbol.upper().replace(".", "-")
    ticker = yf.Ticker(yf_symbol)
    earnings = ticker.earnings
    quarterly_earnings = ticker.quarterly_earnings
    financials = ticker.financials
    quarterly_financials = ticker.quarterly_financials

    # Insert EPS (quarterly)
    if quarterly_earnings is not None and not quarterly_earnings.empty:
        for idx, row in quarterly_earnings.iterrows():
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO earnings_eps (symbol, period, actual, estimate) VALUES (%s, %s, %s, %s)",
                    (
                        symbol,
                        str(idx),
                        clean_value(row.get("Actual Earnings")),
                        clean_value(row.get("Estimated Earnings"))
                    )
                )
    conn.commit()


    # Insert financial annual (with revenue estimates if available)
    revenue_est_annual = None
    try:
        revenue_est_annual = ticker.get_earnings_forecast().get('annualRevenueEstimate')
    except Exception:
        revenue_est_annual = None
    if earnings is not None and not earnings.empty:
        for idx, row in earnings.iterrows():
            revenue_est = None
            if revenue_est_annual is not None and str(idx) in revenue_est_annual:
                revenue_est = clean_value(revenue_est_annual[str(idx)])
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO earnings_financial_annual (symbol, period, revenue, revenue_estimate, earnings) VALUES (%s, %s, %s, %s, %s)",
                    (
                        symbol,
                        str(idx),
                        clean_value(row.get("Revenue")),
                        revenue_est,
                        clean_value(row.get("Earnings"))
                    )
                )
    conn.commit()

    # Insert financial quarterly (with revenue estimates if available)
    revenue_est_quarterly = None
    try:
        revenue_est_quarterly = ticker.get_earnings_forecast().get('quarterlyRevenueEstimate')
    except Exception:
        revenue_est_quarterly = None
    if quarterly_financials is not None and not quarterly_financials.empty:
        for idx, row in quarterly_financials.iterrows():
            revenue_est = None
            if revenue_est_quarterly is not None and str(idx) in revenue_est_quarterly:
                revenue_est = clean_value(revenue_est_quarterly[str(idx)])
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO earnings_financial_quarterly (symbol, period, revenue, revenue_estimate, earnings) VALUES (%s, %s, %s, %s, %s)",
                    (
                        symbol,
                        str(idx),
                        clean_value(row.get("Total Revenue")),
                        revenue_est,
                        clean_value(row.get("Net Income"))
                    )
                )
    conn.commit()

    logger.info(f"Successfully processed earnings for {symbol}")

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
    import gc
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


    # Always drop and create tables before inserting data
    logger.info("Dropping and creating all earnings tables before data load...")
    ensure_tables(conn)
    logger.info("Table creation complete.")

    log_mem("Before fetching symbols")
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols;")
        symbols = [r["symbol"] for r in cur.fetchall()]
    log_mem("After fetching symbols")

    total_symbols = len(symbols)
    processed = 0
    failed = 0

    for sym in symbols:
        try:
            log_mem(f"Before processing {sym} ({processed + 1}/{total_symbols})")
            process_symbol(sym, conn)
            conn.commit()
            processed += 1
            gc.collect()
            if get_rss_mb() > 800:
                time.sleep(0.5)
            else:
                time.sleep(0.05)
            log_mem(f"After processing {sym}")
        except Exception:
            logger.exception(f"Failed to process {sym}")
            failed += 1
            if failed > total_symbols * 0.2:
                logger.error("Too many failures, stopping process")
                break

    update_last_run(conn)
    try:
        conn.close()
    except Exception:
        logger.exception("Error closing database connection")
    log_mem("End of script")
    logger.info("loadearnings complete.")

if __name__ == "__main__":
    main()
