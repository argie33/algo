#!/usr/bin/env python3
import os
import sys
import time
import json
import math
import gc
import logging
import functools
import resource

import boto3
import psycopg2
from psycopg2.extras import DictCursor
import yfinance as yf
import pandas as pd

SCRIPT_NAME = "loadearnings.py"

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

# ─── SecretsManager DB config ────────────────────────────────────────────────
DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")
if not DB_SECRET_ARN:
    logger.error("DB_SECRET_ARN environment variable is not set")
    sys.exit(1)

def get_db_config():
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec.get("port", 5432)),
        sec["dbname"]
    )

# ─── Memory logging ─────────────────────────────────────────────────────────
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return (usage/1024) if sys.platform.startswith("linux") else (usage/(1024*1024))

def log_mem(stage: str):
    logger.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# ─── Clean NaN/None ─────────────────────────────────────────────────────────
def clean_value(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    if pd.isna(v):
        return None
    return v

# ─── Retry decorator ─────────────────────────────────────────────────────────
def retry(max_attempts=3, initial_delay=2, backoff=2):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(symbol, *args, **kwargs):
            attempts, delay = 0, initial_delay
            while attempts < max_attempts:
                attempts += 1
                try:
                    return fn(symbol, *args, **kwargs)
                except Exception as e:
                    logger.error(f"{fn.__name__}({symbol}) attempt {attempts}: {e}", exc_info=True)
                    time.sleep(delay)
                    delay *= backoff
            raise RuntimeError(f"All {max_attempts} attempts failed for {symbol}")
        return wrapper
    return deco

# ─── Create tables (FIXED) ─────────────────────────────────────────────────────
def create_tables():
    log_mem("before table DDL")
    # ← fetch real credentials here
    user, pwd, host, port, dbname = get_db_config()
    conn = psycopg2.connect(
        host=host, port=port,
        user=user, password=pwd,
        dbname=dbname, sslmode="require",
        cursor_factory=DictCursor
    )
    cur = conn.cursor()
    # drop & recreate your three tables
    cur.execute("DROP TABLE IF EXISTS earnings_eps;")
    cur.execute("""
        CREATE TABLE earnings_eps (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            period VARCHAR(20),
            actual DOUBLE PRECISION,
            estimate DOUBLE PRECISION,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("CREATE INDEX ON earnings_eps(symbol);")

    cur.execute("DROP TABLE IF EXISTS earnings_financial_annual;")
    cur.execute("""
        CREATE TABLE earnings_financial_annual (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            period VARCHAR(20),
            revenue BIGINT,
            earnings BIGINT,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("CREATE INDEX ON earnings_financial_annual(symbol);")

    cur.execute("DROP TABLE IF EXISTS earnings_financial_quarterly;")
    cur.execute("""
        CREATE TABLE earnings_financial_quarterly (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            period VARCHAR(20),
            revenue BIGINT,
            earnings BIGINT,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("CREATE INDEX ON earnings_financial_quarterly(symbol);")

    conn.commit()
    cur.close()
    conn.close()
    log_mem("after table DDL")
    logger.info("Tables created or already exist.")

# ─── Insert helpers ───────────────────────────────────────────────────────────
def upsert(conn, sql, params):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    cur.close()

def insert_eps(conn, symbol, period, actual, estimate):
    upsert(conn,
        "INSERT INTO earnings_eps(symbol,period,actual,estimate) VALUES (%s,%s,%s,%s);",
        (symbol, period, actual, estimate)
    )

def insert_fin_ann(conn, symbol, period, revenue, earnings):
    upsert(conn,
        "INSERT INTO earnings_financial_annual(symbol,period,revenue,earnings) VALUES (%s,%s,%s,%s);",
        (symbol, period, revenue, earnings)
    )

def insert_fin_qtr(conn, symbol, period, revenue, earnings):
    upsert(conn,
        "INSERT INTO earnings_financial_quarterly(symbol,period,revenue,earnings) VALUES (%s,%s,%s,%s);",
        (symbol, period, revenue, earnings)
    )

# ─── Process one symbol ───────────────────────────────────────────────────────
@retry()
def process_symbol(symbol):
    log_mem(f"{symbol} start")
    start = time.time()
    logger.info(f"Fetching earnings for {symbol}")
    yf_sym = symbol.upper().replace(".", "-")
    ticker = yf.Ticker(yf_sym)

    # open a new connection for each symbol
    user, pwd, host, port, dbname = get_db_config()
    conn = psycopg2.connect(
        host=host, port=port,
        user=user, password=pwd,
        dbname=dbname, sslmode="require",
        cursor_factory=DictCursor
    )

    # annual
    ann = ticker.earnings
    for year, row in ann.iterrows():
        insert_fin_ann(conn, symbol, str(year),
                       clean_value(row["Revenue"]),
                       clean_value(row["Earnings"]))

    # quarterly
    qtr = ticker.quarterly_earnings
    if qtr is not None:
        for idx, row in qtr.iterrows():
            insert_fin_qtr(conn, symbol, str(idx.date()),
                           clean_value(row["Revenue"]),
                           clean_value(row["Earnings"]))

    # EPS (just reuse earnings field)
    for year, row in ann.iterrows():
        insert_eps(conn, symbol, str(year), clean_value(row["Earnings"]), None)
    if qtr is not None:
        for idx, row in qtr.iterrows():
            insert_eps(conn, symbol, str(idx.date()), clean_value(row["Earnings"]), None)

    conn.close()
    elapsed = time.time() - start
    logger.info(f"{symbol} done in {elapsed:.1f}s")
    log_mem(f"{symbol} end")

# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    log_mem("startup")
    create_tables()

    user, pwd, host, port, dbname = get_db_config()
    conn = psycopg2.connect(
        host=host, port=port,
        user=user, password=pwd,
        dbname=dbname, sslmode="require",
        cursor_factory=DictCursor
    )
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM stock_symbols;")
    symbols = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()

    for sym in symbols:
        try:
            process_symbol(sym)
        except Exception:
            logger.exception(f"Failed processing {sym}")
        gc.collect()
        time.sleep(0.2)

    log_mem("complete")

if __name__ == "__main__":
    main()
