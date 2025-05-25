#!/usr/bin/env python3  
import os
import json
import logging
import math
import gc
import sys
import time

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

import yfinance as yf
import pandas as pd
import exchange_calendars as ecals

SCRIPT_NAME = "loadlatestpriceweekly.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# --- DB config loader ---
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
        .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])['SecretString']
    sec = json.loads(secret_str)
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

# --- NYSE trading days ---
nyse = ecals.get_calendar("XNYS")

# Use the calendar's own timezone (so tz.key exists)
start = pd.Timestamp("1900-01-01", tz=nyse.tz)
end   = pd.Timestamp.now(tz=nyse.tz)

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
            start=from_date if from_date else None,
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

    df = df.sort_index()
    df = df[df["Open"].notna()]
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
            0.0 if ("Dividends" not in row or math.isnan(row["Dividends"])) else float(row["Dividends"]),
            0.0 if ("Stock Splits" not in row or math.isnan(row["Stock Splits"])) else float(row["Stock Splits"])
        ])

    if not rows:
        logging.warning(f"{symbol}: no rows after cleaning; skipping")
        return 0

    COL_LIST = ", ".join([
        "symbol","date","open","high","low",
        "close","adj_close","volume","dividends","stock_splits"
    ])
    sql = f"""
        INSERT INTO {table} ({COL_LIST}) VALUES %s
        ON CONFLICT (symbol, date) DO UPDATE SET
            open        = EXCLUDED.open,
            high        = EXCLUDED.high,
            low         = EXCLUDED.low,
            close       = EXCLUDED.close,
            adj_close   = EXCLUDED.adj_close,
            volume      = EXCLUDED.volume,
            dividends   = EXCLUDED.dividends,
            stock_splits= EXCLUDED.stock_splits
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

    # Stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    # ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]

    for table, syms in [("price_weekly", stock_syms), ("etf_price_weekly", etf_syms)]:
        for symbol in syms:
            existing_dates = get_existing_dates(cur, table, symbol)
            missing_days = all_trading_days_set - existing_dates

            if missing_days:
                logging.info(f"{symbol}: missing {len(missing_days)} trading days, reloading full history")
                fetch_and_insert(symbol, table, cur, conn, from_date=None)
            else:
                if not existing_dates:
                    logging.info(f"{symbol}: no data in table, loading full history")
                    fetch_and_insert(symbol, table, cur, conn, from_date=None)
                else:
                    last_date = max(existing_dates)
                    if last_date >= pd.Timestamp.now(tz=nyse.tz).date():
                        logging.info(f"{symbol}: up to date")
                        continue
                    fetch_and_insert(symbol, table, cur, conn, from_date=last_date + pd.Timedelta(days=1))

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
