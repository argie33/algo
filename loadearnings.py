#!/usr/bin/env python3
import os
import time
import math
import logging
import functools
import resource

import pandas as pd
import yfinance as yf
import psycopg2
from psycopg2.extras import RealDictCursor

# ─── LOGGING ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ─── MEMORY INSTRUMENTATION ─────────────────────────────────────────────────
def log_mem(stage: str):
    """Log current RSS memory usage in MB."""
    usage_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mem_mb = usage_kb / 1024
    logger.info(f"[MEM] {stage}: {mem_mb:.1f} MB")

# ─── DB CONFIG FROM ENV ─────────────────────────────────────────────────────
DB_PARAMS = {
    "host":     os.getenv("DB_HOST"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "cursor_factory": RealDictCursor
}

# ─── RETRY DECORATOR ─────────────────────────────────────────────────────────
def retry(max_attempts=3, initial_delay=2, backoff=2):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(symbol, *args, **kw):
            attempts, delay = 0, initial_delay
            while attempts < max_attempts:
                try:
                    return fn(symbol, *args, **kw)
                except Exception as e:
                    attempts += 1
                    logger.error(f"{fn.__name__} [{symbol}] failed (#{attempts}): {e}", exc_info=True)
                    time.sleep(delay)
                    delay *= backoff
            raise RuntimeError(f"All {max_attempts} attempts failed for {fn.__name__} [{symbol}]")
        return wrapper
    return deco

# ─── TABLE CREATION ─────────────────────────────────────────────────────────
def create_tables():
    log_mem("before table DDL")
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS earnings_eps (
          id          SERIAL PRIMARY KEY,
          symbol      VARCHAR(10) NOT NULL,
          period      VARCHAR(20) NOT NULL,
          actual      DOUBLE PRECISION,
          estimate    DOUBLE PRECISION,
          fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_eps_symbol ON earnings_eps(symbol);
        """,
        """
        CREATE TABLE IF NOT EXISTS earnings_financial_annual (
          id          SERIAL PRIMARY KEY,
          symbol      VARCHAR(10) NOT NULL,
          period      VARCHAR(20) NOT NULL,
          revenue     BIGINT,
          earnings    BIGINT,
          fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_ann_symbol ON earnings_financial_annual(symbol);
        """,
        """
        CREATE TABLE IF NOT EXISTS earnings_financial_quarterly (
          id          SERIAL PRIMARY KEY,
          symbol      VARCHAR(10) NOT NULL,
          period      VARCHAR(20) NOT NULL,
          revenue     BIGINT,
          earnings    BIGINT,
          fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_qtr_symbol ON earnings_financial_quarterly(symbol);
        """
    ]
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    for ddl in ddl_statements:
        cur.execute(ddl)
    conn.commit()
    cur.close()
    conn.close()
    log_mem("after table DDL")
    logger.info("Tables created or already exist.")

# ─── HELPERS & UPSERT ────────────────────────────────────────────────────────
def clean_value(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return v

def upsert(sql: str, params: tuple):
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    cur.close()
    conn.close()

# ─── INSERT FUNCTIONS ────────────────────────────────────────────────────────
def insert_eps(symbol, period, actual, estimate):
    upsert(
        "INSERT INTO earnings_eps(symbol, period, actual, estimate) VALUES (%s, %s, %s, %s);",
        (symbol, period, actual, estimate)
    )

def insert_fin_ann(symbol, period, revenue, earnings):
    upsert(
        "INSERT INTO earnings_financial_annual(symbol, period, revenue, earnings) VALUES (%s, %s, %s, %s);",
        (symbol, period, revenue, earnings)
    )

def insert_fin_qtr(symbol, period, revenue, earnings):
    upsert(
        "INSERT INTO earnings_financial_quarterly(symbol, period, revenue, earnings) VALUES (%s, %s, %s, %s);",
        (symbol, period, revenue, earnings)
    )

# ─── PROCESS ONE SYMBOL ──────────────────────────────────────────────────────
@retry(max_attempts=3)
def process_symbol(symbol):
    log_mem(f"{symbol} ▶ start")
    start_ts = time.time()
    logger.info(f"Fetching {symbol}…")
    ticker = yf.Ticker(symbol)

    # Annual earnings DataFrame
    ann = ticker.earnings
    if ann is None or ann.empty:
        raise ValueError("No annual earnings data")
    for year, row in ann.iterrows():
        insert_fin_ann(symbol, str(year),
                       clean_value(row.get("Revenue")),
                       clean_value(row.get("Earnings")))

    # Quarterly earnings DataFrame
    qtr = ticker.quarterly_earnings
    if qtr is not None and not qtr.empty:
        for idx, row in qtr.iterrows():
            insert_fin_qtr(symbol, str(idx.date()),
                           clean_value(row.get("Revenue")),
                           clean_value(row.get("Earnings")))
    else:
        logger.warning(f"No quarterly earnings for {symbol}")

    # EPS — use actual from net earnings; estimate=NULL
    for year, row in ann.iterrows():
        insert_eps(symbol, str(year),
                   clean_value(row.get("Earnings")), None)
    if qtr is not None:
        for idx, row in qtr.iterrows():
            insert_eps(symbol, str(idx.date()),
                       clean_value(row.get("Earnings")), None)

    elapsed = time.time() - start_ts
    logger.info(f"{symbol} done in {elapsed:.1f}s")
    log_mem(f"{symbol} ◀ end")

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    log_mem("startup")
    create_tables()

    # load symbols
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM stock_symbols;")
    symbols = [r["symbol"] for r in cur.fetchall()]
    cur.close()
    conn.close()

    for sym in symbols:
        try:
            process_symbol(sym)
        except Exception:
            logger.exception(f"Processing failed for {sym}")
        time.sleep(0.1)

    log_mem("all symbols complete")
    logger.info("All done.")

if __name__ == "__main__":
    main()
