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
    "symbol","date","open","high","low",
    "close","adj_close","volume","dividends","stock_splits"
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
# Fetch NYSE trading days
# -------------------------------
nyse = ecals.get_calendar("XNYS")
start = datetime.date(1900, 1, 1)
end   = pd.Timestamp.now(tz=nyse.tz).date()
all_trading_days = nyse.sessions_in_range(start, end)
all_trading_days_set = {d.date() for d in all_trading_days}

# -------------------------------
# Existing-dates helper
# -------------------------------
def get_existing_dates(cur, table, symbol):
    cur.execute(f"SELECT date FROM {table} WHERE symbol = %s", (symbol,))
    return {r["date"] for r in cur.fetchall()}

# -------------------------------
# Download & upsert for one symbol
# -------------------------------
def fetch_and_insert(symbol, table, cur, conn, from_date=None):
    yf_sym = symbol.replace('.', '-').upper()
    # --- retry download ---
    for attempt in range(1, MAX_DOWNLOAD_RETRIES+1):
        logging.info(f"{symbol}: yf.download attempt {attempt}")
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

    # --- sanity checks ---
    if df is None or df.empty:
        logging.warning(f"{symbol}: no data returned; skipping")
        return 0

    expected = ["Open","High","Low","Close","Volume"]
    missing  = [c for c in expected if c not in df.columns]
    if missing:
        logging.warning(f"{symbol}: missing cols {missing}; skipping")
        return 0

    df = df.sort_index().loc[df["Open"].notna()]
    if df.empty:
        logging.warning(f"{symbol}: all Open NaN; skipping")
        return 0

    # --- build rows ---
    rows = []
    for idx, row in df.iterrows():
        rows.append([
            symbol,
            idx.date(),
            float(row["Open"]),
            float(row["High"]),
            float(row["Low"]),
            float(row["Close"]),
            float(row.get("Adj Close", row["Close"])),
            int(row["Volume"]),
            float(row.get("Dividends", 0.0) or 0.0),
            float(row.get("Stock Splits", 0.0) or 0.0)
        ])
    if not rows:
        logging.warning(f"{symbol}: no valid rows; skipping")
        return 0

    # --- upsert ---
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
# Main
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

    # load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stocks = [r["symbol"] for r in cur.fetchall()]
    # load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etfs   = [r["symbol"] for r in cur.fetchall()]

    for table, syms in [("price_daily", stocks), ("etf_price_daily", etfs)]:
        logging.info(f"Processing {table} ({len(syms)} symbols)")
        for sym in syms:
            existing = get_existing_dates(cur, table, sym)
            if existing:
                first_trade   = min(existing)
                relevant_days = {d for d in all_trading_days_set if d >= first_trade}
                missing_days  = relevant_days - existing
            else:
                missing_days = all_trading_days_set

            if not existing:
                logging.info(f"{sym}: no data in table, loading full history")
                fetch_and_insert(sym, table, cur, conn, from_date=None)

            elif missing_days:
                logging.info(f"{sym}: {len(missing_days)} missing days since first trade, reloading full history")
                fetch_and_insert(sym, table, cur, conn, from_date=None)

            else:
                last = max(existing)
                if last >= end:
                    logging.info(f"{sym}: up to date")
                else:
                    fetch_and_insert(sym, table, cur, conn, from_date=last + datetime.timedelta(days=1))

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
