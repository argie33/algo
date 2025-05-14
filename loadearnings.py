#!/usr/bin/env python3
import sys
import time
import logging
import functools
import os
import json

import boto3
import psycopg2
from psycopg2.extras import DictCursor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from yahooquery import Ticker
from yahooquery.utils import TimeoutHTTPAdapter
import pandas as pd
import math

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadearnings.py"

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

@retry(max_attempts=3, initial_delay=2, backoff=2)
def process_symbol(symbol, conn):
    """Fetch earnings via yahooquery and insert into PostgreSQL."""
    yq_symbol = symbol.upper().replace(".", "-")
    ticker = Ticker(yq_symbol, asynchronous=False)
    adapter = TimeoutHTTPAdapter(
        max_retries=Retry(total=2, backoff_factor=1),
        timeout=10.0
    )
    ticker.session.mount("https://", adapter)
    ticker.session.mount("http://", adapter)

    data = ticker.earnings
    earnings_data = data.get(yq_symbol)
    if not earnings_data or not isinstance(earnings_data, dict):
        raise ValueError(f"No valid earnings data for {symbol}: {earnings_data!r}")

    # Insert EPS
    for record in earnings_data.get("earningsChart", {}).get("quarterly", []):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO earnings_eps (symbol, period, actual, estimate) VALUES (%s, %s, %s, %s)",
                (
                    symbol,
                    record.get("date"),
                    clean_value(record.get("actual")),
                    clean_value(record.get("estimate"))
                )
            )
    conn.commit()

    # Insert financial annual
    for record in earnings_data.get("financialsChart", {}).get("yearly", []):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO earnings_financial_annual (symbol, period, revenue, earnings) VALUES (%s, %s, %s, %s)",
                (
                    symbol,
                    str(record.get("date")),
                    clean_value(record.get("revenue")),
                    clean_value(record.get("earnings"))
                )
            )
    conn.commit()

    # Insert financial quarterly
    for record in earnings_data.get("financialsChart", {}).get("quarterly", []):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO earnings_financial_quarterly (symbol, period, revenue, earnings) VALUES (%s, %s, %s, %s)",
                (
                    symbol,
                    record.get("date"),
                    clean_value(record.get("revenue")),
                    clean_value(record.get("earnings"))
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

    ensure_tables(conn)

    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols;")
        symbols = [r["symbol"] for r in cur.fetchall()]

    for sym in symbols:
        try:
            process_symbol(sym, conn)
        except Exception:
            logger.exception(f"Failed to process {sym}")
        time.sleep(0.2)

    update_last_run(conn)
    conn.close()
    logger.info("loadearnings complete.")

if __name__ == "__main__":
    main()
