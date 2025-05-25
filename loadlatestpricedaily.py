#!/usr/bin/env python3
import os
import json
import logging
import math
import sys

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

import yfinance as yf
import pandas as pd
import exchange_calendars as ecals
import datetime

SCRIPT_NAME = "loadlatestpricedaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# --- DB config loader ---
def get_db_config():
    secret = boto3.client("secretsmanager") \
        .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret)
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

# --- NYSE trading days ---
nyse = ecals.get_calendar("XNYS")

# Use naive dates (no tz) to satisfy sessions_in_range
start = datetime.date(2005, 5, 25)
# derive today in calendar's timezone, then strip tz to get a date
end = pd.Timestamp.now(tz=nyse.tz).date()

all_trading_days = nyse.sessions_in_range(start, end)
all_trading_days_set = set(d.date() for d in all_trading_days)

def get_existing_dates(cur, table, symbol):
    cur.execute(f"SELECT date FROM {table} WHERE symbol = %s", (symbol,))
    return {r["date"] for r in cur.fetchall()}

def fetch_and_insert(symbol, table, cur, conn, from_date=None):
    yf_sym = symbol.replace('.', '-')
    try:
        df = yf.download(
            tickers=yf_sym,
            start=from_date,
            interval="1d",
            auto_adjust=True,
            actions=True,
            progress=False
        )
    except Exception as e:
        logging.warning(f"{symbol}: yfinance download failed: {e}")
        return 0

    if df is None or df.empty:
        logging.warning(f"{symbol}: no data returned from yfinance")
        return 0

    df = df.sort_index().dropna(subset=["Open"])
    if df.empty:
        logging.warning(f"{symbol}: no valid price rows after cleaning")
        return 0

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
            0.0 if math.isnan(row.get("Dividends", 0.0)) else float(row["Dividends"]),
            0.0 if math.isnan(row.get("Stock Splits", 0.0)) else float(row["Stock Splits"])
        ])

    if not rows:
        logging.warning(f"{symbol}: no rows after cleaning; skipping")
        return 0

    cols = "symbol,date,open,high,low,close,adj_close,volume,dividends,stock_splits"
    sql = f"""
        INSERT INTO {table} ({cols}) VALUES %s
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
    return len(rows)

def main():
    cfg  = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Load symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms   = [r["symbol"] for r in cur.fetchall()]

    for table, syms in [("price_daily", stock_syms), ("etf_price_daily", etf_syms)]:
        for symbol in syms:
            existing = get_existing_dates(cur, table, symbol)
            missing  = all_trading_days_set - existing

            if missing:
                logging.info(f"{symbol}: missing {len(missing)} days, reloading full history")
                fetch_and_insert(symbol, table, cur, conn, from_date=None)
            else:
                if not existing:
                    logging.info(f"{symbol}: no data in table, loading full history")
                    fetch_and_insert(symbol, table, cur, conn, from_date=None)
                else:
                    last = max(existing)
                    if last >= end:
                        logging.info(f"{symbol}: up to date")
                        continue
                    fetch_and_insert(symbol, table, cur, conn, from_date=last + datetime.timedelta(days=1))

    # Record last run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()
    cur.close()
    conn.close()
    logging.info("All done.")

if __name__ == "__main__":
    main()
