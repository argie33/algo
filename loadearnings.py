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

SCRIPT_NAME = "loadearnings.py"

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")
if not DB_SECRET_ARN:
    logger.error("DB_SECRET_ARN environment variable is not set")
    sys.exit(1)

def get_db_config():
    """Fetch DB credentials from AWS Secrets Manager."""
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return sec["username"], sec["password"], sec["host"], int(sec["port"]), sec["dbname"]

def retry(max_attempts=3, initial_delay=2, backoff=2):
    """Retry decorator with exponential backoff."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(symbol, conn, *args, **kwargs):
            attempts, delay = 0, initial_delay
            while attempts < max_attempts:
                try:
                    return fn(symbol, conn, *args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logger.error(
                        f"{fn.__name__} failed for {symbol} "
                        f"(attempt {attempts}/{max_attempts}): {e}",
                        exc_info=True
                    )
                    time.sleep(delay)
                    delay *= backoff
            raise RuntimeError(f"All {max_attempts} attempts failed for {fn.__name__}({symbol})")
        return wrapper
    return decorator

def clean_value(v):
    """Convert pandas/Numpy NaN to None, unwrap Numpy scalars."""
    import numpy as np
    if isinstance(v, float) and math.isnan(v):
        return None
    if pd.isna(v):
        return None
    if isinstance(v, np.generic):
        return v.item()
    return v

def ensure_tables(conn):
    """Drop & recreate all earnings tables with appropriate constraints."""
    with conn.cursor() as cur:
        # EPS table
        cur.execute("DROP TABLE IF EXISTS earnings_eps;")
        cur.execute("""
            CREATE TABLE earnings_eps (
                id          SERIAL PRIMARY KEY,
                symbol      VARCHAR(64)   NOT NULL,
                period      TIMESTAMPTZ   NOT NULL,
                actual      DOUBLE PRECISION,
                estimate    DOUBLE PRECISION,
                fetched_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, period, actual, estimate)
            );
        """)

        # Annual financials
        cur.execute("DROP TABLE IF EXISTS earnings_financial_annual;")
        cur.execute("""
            CREATE TABLE earnings_financial_annual (
                id               SERIAL PRIMARY KEY,
                symbol           VARCHAR(64) NOT NULL,
                period           VARCHAR(64) NOT NULL,
                revenue          BIGINT,
                revenue_estimate BIGINT,
                earnings         BIGINT,
                fetched_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, period)
            );
        """)

        # Quarterly financials
        cur.execute("DROP TABLE IF EXISTS earnings_financial_quarterly;")
        cur.execute("""
            CREATE TABLE earnings_financial_quarterly (
                id               SERIAL PRIMARY KEY,
                symbol           VARCHAR(64) NOT NULL,
                period           VARCHAR(64) NOT NULL,
                revenue          BIGINT,
                revenue_estimate BIGINT,
                earnings         BIGINT,
                fetched_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, period)
            );
        """)

        # EPS revisions & trend tables
        cur.execute("DROP TABLE IF EXISTS earnings_eps_trend;")
        cur.execute("""
            CREATE TABLE earnings_eps_trend (
                id         SERIAL PRIMARY KEY,
                symbol     VARCHAR(64) NOT NULL,
                period     VARCHAR(64) NOT NULL,
                up_count   INTEGER,
                down_count INTEGER,
                fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, period)
            );
        """)

        # Last-run stamp
        cur.execute("""
            CREATE TABLE IF NOT EXISTS last_updated (
                script_name VARCHAR(255) PRIMARY KEY,
                last_run    TIMESTAMPTZ NOT NULL
            );
        """)
    conn.commit()

def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return (usage/1024) if sys.platform.startswith("linux") else (usage/(1024*1024))

def log_mem(stage):
    logger.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

@retry()
def process_symbol(symbol, conn):
    yf_sym = symbol.upper().replace(".", "-")
    ticker = yf.Ticker(yf_sym)

    # 1) Earnings dates (reported vs estimate)
    try:
        df = ticker.get_earnings_dates()
        if isinstance(df, pd.DataFrame) and not df.empty:
            for _, row in df.iterrows():
                dt = row["Earnings Date"]
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO earnings_eps(symbol, period, actual, estimate)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT(symbol, period, actual, estimate) DO NOTHING
                        """,
                        (
                            symbol,
                            dt,
                            clean_value(row.get("Reported EPS")),
                            clean_value(row.get("EPS Estimate"))
                        )
                    )
            conn.commit()
    except Exception as e:
        logger.warning(f"get_earnings_dates failed for {symbol}: {e}", exc_info=True)

    # 2) Annual revenue & earnings
    try:
        ann = ticker.earnings
        if isinstance(ann, pd.DataFrame) and not ann.empty:
            for period, row in ann.iterrows():
                period_str = getattr(period, "date", lambda: period)()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO earnings_financial_annual
                          (symbol, period, revenue, revenue_estimate, earnings)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT(symbol, period) DO NOTHING
                        """,
                        (
                            symbol,
                            str(period_str),
                            clean_value(row.get("Revenue")),
                            None,
                            clean_value(row.get("Earnings"))
                        )
                    )
            conn.commit()
    except Exception as e:
        logger.warning(f"ticker.earnings failed for {symbol}: {e}", exc_info=True)

    # 3) Quarterly revenue & earnings
    try:
        qtr = ticker.quarterly_earnings
        if isinstance(qtr, pd.DataFrame) and not qtr.empty:
            for period, row in qtr.iterrows():
                period_str = getattr(period, "date", lambda: period)()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO earnings_financial_quarterly
                          (symbol, period, revenue, revenue_estimate, earnings)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT(symbol, period) DO NOTHING
                        """,
                        (
                            symbol,
                            str(period_str),
                            clean_value(row.get("Revenue")),
                            None,
                            clean_value(row.get("Earnings"))
                        )
                    )
            conn.commit()
    except Exception as e:
        logger.warning(f"ticker.quarterly_earnings failed for {symbol}: {e}", exc_info=True)

    # 4) EPS revisions (ups/downs in last 7 days)
    if hasattr(ticker, "eps_revisions"):
        try:
            rev = ticker.eps_revisions
            if isinstance(rev, pd.DataFrame) and not rev.empty:
                for row_name in rev.index:
                    for col in rev.columns:
                        val = clean_value(rev.at[row_name, col])
                        period = f"{col}_{row_name}"
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO earnings_eps(symbol, period, actual, estimate)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT(symbol, period, actual, estimate) DO NOTHING
                                """,
                                (symbol, period, val, None)
                            )
                conn.commit()
        except Exception as e:
            logger.warning(f"eps_revisions failed for {symbol}: {e}", exc_info=True)

    # 5) EPS trend (analyst upgrades/downgrades)
    if hasattr(ticker, "eps_trend"):
        try:
            trend = ticker.eps_trend
            if isinstance(trend, pd.DataFrame) and not trend.empty:
                for month, row in trend.iterrows():
                    up   = clean_value(row.get("upLastMonth"))
                    down = clean_value(row.get("downLastMonth"))
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO earnings_eps_trend(symbol, period, up_count, down_count)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT(symbol, period) DO NOTHING
                            """,
                            (symbol, str(month), up, down)
                        )
                conn.commit()
        except Exception as e:
            logger.warning(f"eps_trend failed for {symbol}: {e}", exc_info=True)

    logger.info(f"Finished all earnings modules for {symbol}")

def update_last_run(conn):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO last_updated(script_name, last_run)
            VALUES(%s, NOW())
            ON CONFLICT(script_name) DO UPDATE
              SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME,))
    conn.commit()

def main():
    import gc
    user, pwd, host, port, dbname = get_db_config()
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=pwd,
        dbname=dbname, sslmode="require", cursor_factory=DictCursor
    )

    logger.info("Recreating tables...")
    ensure_tables(conn)

    log_mem("Before fetching symbols")
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols;")
        symbols = [r["symbol"] for r in cur.fetchall()]
    log_mem("Fetched symbols")

    total = len(symbols)
    done = 0
    fails = 0
    for sym in symbols:
        try:
            log_mem(f"Start {sym} ({done+1}/{total})")
            process_symbol(sym, conn)
            done += 1
            gc.collect()
            time.sleep(0.05 if get_rss_mb() < 800 else 0.5)
            log_mem(f"End {sym}")
        except Exception:
            logger.exception(f"Error processing {sym}")
            fails += 1
            if fails > total * 0.2:
                logger.error("Too many failures, aborting.")
                break

    update_last_run(conn)
    conn.close()
    log_mem("Script end")
    logger.info("All done.")

if __name__ == "__main__":
    main()
