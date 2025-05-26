#!/usr/bin/env python3

import sys
import time
import logging
import json
import os
import gc
import resource
import math
import datetime

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

import yfinance as yf
import pandas as pd
import exchange_calendars as ecals

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadlatestpricedaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings
# -------------------------------
MAX_DOWNLOAD_RETRIES = 3
RETRY_DELAY         = 0.2  # seconds

# -------------------------------
# Price-daily columns (for INSERT)
# -------------------------------
PRICE_COLUMNS = [
    "symbol", "date", "open", "high", "low",
    "close", "adj_close", "volume", "dividends", "stock_splits"
]
COL_LIST = ", ".join(PRICE_COLUMNS)

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

# -------------------------------
# Build NYSE trading days set
# -------------------------------
# calendar only goes back to Jan 1, 2006
calendar_start_date = datetime.date(2006, 1, 1)

nyse = ecals.get_calendar("XNYS")
# compute last trading day as naive date
today_aware      = pd.Timestamp.now(tz=nyse.tz)
last_trading_day = today_aware.date()

# get all sessions between calendar_start_date and last_trading_day
sessions = nyse.sessions_in_range(calendar_start_date, last_trading_day)
all_trading_days_set = {sess.date() for sess in sessions}

# -------------------------------
# Helper: fetch existing dates
# -------------------------------
def get_existing_dates(cur, table, symbol):
    cur.execute(f"SELECT date FROM {table} WHERE symbol = %s", (symbol,))
    return {r["date"] for r in cur.fetchall()}

# -------------------------------
# Download & upsert for one symbol
# -------------------------------
def fetch_and_insert(symbol, table, cur, conn, from_date=None):
    yf_sym = symbol.replace('.', '-').upper()

    # retry download
    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        logging.info(f"{symbol}: yf.download attempt {attempt} (from {from_date})")
        log_mem(f"{symbol} download start")
        try:
            df = yf.download(
                tickers=yf_sym,
                start=from_date,
                interval="1d",
                auto_adjust=True,
                actions=True,
                progress=False
            )
            break
        except Exception as e:
            logging.warning(f"{symbol}: download error: {e}")
            time.sleep(RETRY_DELAY)
    else:
        logging.error(f"{symbol}: failed download after {MAX_DOWNLOAD_RETRIES} attempts")
        return 0

    # no data?
    if df is None or df.empty:
        logging.warning(f"{symbol}: no data returned; skipping")
        return 0

    # flatten multi-index columns
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(1)

    # required columns
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        logging.warning(f"{symbol}: missing cols {missing}; skipping")
        return 0

    df = df.sort_index()
    df = df[df["Open"].notna()]
    if df.empty:
        logging.warning(f"{symbol}: all Open NaN; skipping")
        return 0

    # build rows
    rows = []
    for idx, row in df.iterrows():
        rows.append([
            symbol,
            idx.date(),
            None if math.isnan(row["Open"]) else float(row["Open"]),
            None if math.isnan(row["High"]) else float(row["High"]),
            None if math.isnan(row["Low"]) else float(row["Low"]),
            None if math.isnan(row["Close"]) else float(row["Close"]),
            None if math.isnan(row.get("Adj Close", row["Close"])) else float(row.get("Adj Close", row["Close"])),
            None if math.isnan(row["Volume"]) else int(row["Volume"]),
            0.0 if ("Dividends" not in row or math.isnan(row["Dividends"])) else float(row["Dividends"]),
            0.0 if ("Stock Splits" not in row or math.isnan(row["Stock Splits"])) else float(row["Stock Splits"])
        ])
    if not rows:
        logging.warning(f"{symbol}: no valid rows; skipping")
        return 0

    # upsert into PostgreSQL
    sql = f"""
        INSERT INTO {table} ({COL_LIST})
        VALUES %s
        ON CONFLICT (symbol, date) DO UPDATE SET
          open         = EXCLUDED.open,
          high         = EXCLUDED.high,
          low          = EXCLUDED.low,
          close        = EXCLUDED.close,
          adj_close    = EXCLUDED.adj_close,
          volume       = EXCLUDED.volume,
          dividends    = EXCLUDED.dividends,
          stock_splits = EXCLUDED.stock_splits
    """
    execute_values(cur, sql, rows)
    conn.commit()
    logging.info(f"{table} — {symbol}: upserted {len(rows)} rows")
    log_mem(f"{symbol} insert done")
    return len(rows)

# -------------------------------
# Main entrypoint
# -------------------------------
def main():
    log_mem("startup")

    cfg  = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # load stock & ETF symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stocks = [r["symbol"] for r in cur.fetchall()]
    cur.execute("SELECT symbol FROM etf_symbols;")
    etfs   = [r["symbol"] for r in cur.fetchall()]

    for table, syms in [("price_daily", stocks), ("etf_price_daily", etfs)]:
        logging.info(f"Processing {table} ({len(syms)} symbols)")
        for sym in syms:
            try:
                existing = get_existing_dates(cur, table, sym)

                if existing:
                    first_loaded = min(existing)
                    baseline     = max(first_loaded, calendar_start_date)
                    relevant     = {d for d in all_trading_days_set if d >= baseline}
                    missing      = relevant - existing
                else:
                    missing = all_trading_days_set

                if not existing:
                    # initial load
                    logging.info(f"{sym}: no data → full history")
                    rows = fetch_and_insert(sym, table, cur, conn, from_date=None)

                elif missing:
                    # fill historic gaps only
                    gap_start = min(missing)
                    logging.info(f"{sym}: {len(missing)} gaps → from {gap_start}")
                    rows = fetch_and_insert(sym, table, cur, conn, from_date=gap_start)
                    if rows == 0:
                        logging.warning(f"{sym}: gap fill failed → full history")
                        rows = fetch_and_insert(sym, table, cur, conn, from_date=None)

                else:
                    # upsert latest days, always including last_trading_day
                    last_date = max(existing)
                    if last_date < last_trading_day:
                        start_date = last_date + datetime.timedelta(days=1)
                    else:
                        start_date = last_trading_day

                    logging.info(f"{sym}: incremental from {start_date}")
                    rows = fetch_and_insert(sym, table, cur, conn, from_date=start_date)
                    if rows == 0:
                        logging.warning(f"{sym}: incremental failed → full history")
                        rows = fetch_and_insert(sym, table, cur, conn, from_date=None)

            except Exception as e:
                logging.error(f"{sym}: unexpected error, full reload: {e}", exc_info=True)
                fetch_and_insert(sym, table, cur, conn, from_date=None)

    # record last run
    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
          SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    log_mem("shutdown")
    cur.close()
    conn.close()
    logging.info("All done.")

if __name__ == "__main__":
    main()
