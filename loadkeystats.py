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
# Configuration
# -------------------------------
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]
BATCH_SIZE     = int(os.getenv("BATCH_SIZE", "100"))  # symbols per API call
PAUSE_BETWEEN_BATCHES = float(os.getenv("PAUSE_BETWEEN_BATCHES", "0.5"))

def get_db_config():
    """
    Fetch host, port, dbname, username & password from Secrets Manager.
    SecretString must be JSON with keys: username, password, host, port, dbname.
    """
    client = boto3.client("secretsmanager")
    resp   = client.get_secret_value(SecretId=DB_SECRET_ARN)
    sec    = json.loads(resp["SecretString"])
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
    cur  = conn.cursor()
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
            attempts, delay = 0, initial_delay
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
# Insert function (unchanged)
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
    col_list     = ", ".join(cols)
    vals         = [symbol] + [rec.get(c) for c in cols[1:]]
    sql          = f"INSERT INTO key_stats ({col_list}) VALUES ({placeholders});"
    cur.execute(sql, vals)
    cur.close()

# -------------------------------
# Batch-fetch & process 
# -------------------------------
@retry(max_attempts=3, initial_delay=2, backoff=2)
def process_batch(symbols, conn):
    """
    Fetch key_stats for a list of symbols in one Ticker() call,
    clean & insert each record into key_stats.
    """
    # yahooquery expects lower‐case, dots→dashes
    yqs = [s.replace('.', '-').lower() for s in symbols]
    logging.info(f"Fetching key_stats for batch of {len(symbols)} symbols...")
    data = Ticker(yqs).key_stats

    for sym, yq in zip(symbols, yqs):
        rec = data.get(yq)
        if not isinstance(rec, dict):
            logging.warning(f"No or invalid key_stats for {sym}")
            continue

        # parse all timestamp fields
        for fld in [
            "sharesShortPreviousMonthDate","dateShortInterest",
            "lastFiscalYearEnd","nextFiscalYearEnd",
            "mostRecentQuarter","lastSplitDate"
        ]:
            rec[fld] = parse_ts(rec.get(fld))

        insert_key_stat(rec, sym, conn)
        logging.info(f"Inserted key_stats for {sym}")

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

    # load all symbols once
    conn = pg_connect()
    cur  = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT DISTINCT symbol FROM stock_symbols;")
    symbols = [r["symbol"] for r in cur.fetchall()]
    cur.close()
    conn.close()

    # process symbols in batches
    conn = pg_connect()
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i : i + BATCH_SIZE]
        try:
            process_batch(batch, conn)
        except Exception as e:
            logging.error(f"Batch {i//BATCH_SIZE+1} failed: {e}")
        time.sleep(PAUSE_BETWEEN_BATCHES)

    conn.close()
    update_last_updated()
    logging.info("All symbols processed.")
