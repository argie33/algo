#!/usr/bin/env python3
import sys
import time
import logging
import functools
import json
import os

import requests
import pandas as pd
import math
from yahooquery import Ticker

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadkeystats.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Environment-driven configuration
# -------------------------------
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]

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

# -------------------------------
# DB connect helper
# -------------------------------
def pg_connect():
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(
        host=host, port=port,
        user=user, password=pwd,
        dbname=db
    )
    conn.autocommit = True
    return conn

# -------------------------------
# Create key_stats table
# -------------------------------
def create_key_stats_table():
    conn = pg_connect()
    cur = conn.cursor()
    logging.info("Dropping table key_stats if it exists.")
    cur.execute("DROP TABLE IF EXISTS key_stats;")
    logging.info("Creating table key_stats.")
    cur.execute("""
    CREATE TABLE key_stats (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10),
        maxAge INT,
        priceHint INT,
        enterpriseValue DOUBLE PRECISION,
        forwardPE DOUBLE PRECISION,
        profitMargins DOUBLE PRECISION,
        floatShares DOUBLE PRECISION,
        sharesOutstanding DOUBLE PRECISION,
        sharesShort DOUBLE PRECISION,
        sharesShortPriorMonth DOUBLE PRECISION,
        sharesShortPreviousMonthDate TIMESTAMP,
        dateShortInterest TIMESTAMP,
        sharesPercentSharesOut DOUBLE PRECISION,
        heldPercentInsiders DOUBLE PRECISION,
        heldPercentInstitutions DOUBLE PRECISION,
        shortRatio DOUBLE PRECISION,
        shortPercentOfFloat DOUBLE PRECISION,
        beta DOUBLE PRECISION,
        category VARCHAR(50),
        bookValue DOUBLE PRECISION,
        priceToBook DOUBLE PRECISION,
        fundFamily VARCHAR(100),
        legalType VARCHAR(100),
        lastFiscalYearEnd TIMESTAMP,
        nextFiscalYearEnd TIMESTAMP,
        mostRecentQuarter TIMESTAMP,
        earningsQuarterlyGrowth DOUBLE PRECISION,
        netIncomeToCommon DOUBLE PRECISION,
        trailingEps DOUBLE PRECISION,
        forwardEps DOUBLE PRECISION,
        pegRatio DOUBLE PRECISION,
        lastSplitFactor VARCHAR(20),
        lastSplitDate TIMESTAMP,
        enterpriseToRevenue DOUBLE PRECISION,
        enterpriseToEbitda DOUBLE PRECISION,
        week52Change DOUBLE PRECISION,
        sp52WeekChange DOUBLE PRECISION,
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.close()
    conn.close()
    logging.info("key_stats table ready.")

# -------------------------------
# Retry decorator
# -------------------------------
def retry(max_attempts=3, initial_delay=2, backoff=2):
    def decorator_retry(func):
        @functools.wraps(func)
        def wrapper_retry(*args, **kwargs):
            attempts = 0
            delay = initial_delay
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logging.error(
                        f"Attempt {attempts} for {func.__name__} failed: {e}",
                        exc_info=True
                    )
                    time.sleep(delay)
                    delay *= backoff
            raise
        return wrapper_retry
    return decorator_retry

# -------------------------------
# Helpers to parse & clean
# -------------------------------
def parse_ts(value):
    try:
        if isinstance(value, (int, float)):
            dt = pd.to_datetime(value, unit='s', errors='coerce')
        else:
            dt = pd.to_datetime(value, errors='coerce')
        return dt.to_pydatetime() if not pd.isna(dt) else None
    except:
        return None

def clean_row(row):
    out = {}
    for k, v in row.items():
        if isinstance(v, float) and math.isnan(v):
            out[k] = None
        elif pd.isna(v):
            out[k] = None
        else:
            out[k] = v
    return out

# -------------------------------
# Insert function
# -------------------------------
def insert_key_stat(rec, symbol, conn):
    rec = clean_row(rec)
    cur = conn.cursor()
    cols = [
        "symbol","maxAge","priceHint","enterpriseValue","forwardPE","profitMargins",
        "floatShares","sharesOutstanding","sharesShort","sharesShortPriorMonth",
        "sharesShortPreviousMonthDate","dateShortInterest","sharesPercentSharesOut",
        "heldPercentInsiders","heldPercentInstitutions","shortRatio","shortPercentOfFloat",
        "beta","category","bookValue","priceToBook","fundFamily","legalType",
        "lastFiscalYearEnd","nextFiscalYearEnd","mostRecentQuarter","earningsQuarterlyGrowth",
        "netIncomeToCommon","trailingEps","forwardEps","pegRatio","lastSplitFactor",
        "lastSplitDate","enterpriseToRevenue","enterpriseToEbitda","week52Change","sp52WeekChange"
    ]
    placeholders = ", ".join(["%s"] * len(cols))
    col_list = ", ".join(cols)
    vals = [symbol] + [rec.get(c) for c in cols[1:]]
    sql = f"INSERT INTO key_stats ({col_list}) VALUES ({placeholders});"
    cur.execute(sql, vals)
    cur.close()

# -------------------------------
# Per‑symbol processing
# -------------------------------
@retry(max_attempts=3, initial_delay=2, backoff=2)
def process_symbol(symbol):
    yq = symbol.replace('.', '-').lower()
    logging.info(f"Fetching key stats for {symbol}")
    data = Ticker(yq).key_stats
    rec = data.get(yq)
    if not isinstance(rec, dict):
        logging.warning(f"No or invalid key_stats for {symbol}")
        return

    for fld in [
        "sharesShortPreviousMonthDate","dateShortInterest",
        "lastFiscalYearEnd","nextFiscalYearEnd",
        "mostRecentQuarter","lastSplitDate"
    ]:
        rec[fld] = parse_ts(rec.get(fld))

    conn = pg_connect()
    try:
        insert_key_stat(rec, symbol, conn)
        logging.info(f"Inserted key stats for {symbol}")
    finally:
        conn.close()

# -------------------------------
# Update last_updated stamp
# -------------------------------
def update_last_updated():
    conn = pg_connect()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
          SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    cur.close()
    conn.close()

# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    create_key_stats_table()

    conn = pg_connect()
    cur  = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT DISTINCT symbol FROM stock_symbols;")
    symbols = [r["symbol"] for r in cur.fetchall()]
    cur.close()
    conn.close()

    for sym in symbols:
        try:
            process_symbol(sym)
        except Exception:
            pass
        time.sleep(0.1)

    update_last_updated()
    logging.info("All symbols processed.")
