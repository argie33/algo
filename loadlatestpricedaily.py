#!/usr/bin/env python3
import sys
import time
import logging
from datetime import datetime, timedelta
import json
import os

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
import yfinance as yf

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadlatestdailyprice.py"
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
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"]
    )

# -------------------------------
# Fetch function with retries
# -------------------------------
MAX_RETRIES      = 3
RETRY_DELAY      = 5
RATE_LIMIT_DELAY = 0.0

def fetch_daily_data(symbol, start_date, end_date):
    yf_sym = symbol.replace('.', '-')
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            ticker = yf.Ticker(yf_sym)
            df     = ticker.history(
                start=start_date,
                end=end_date,
                interval="1d",
                auto_adjust=False
            )
            if df is None:
                raise ValueError("No data returned")
            df = df.reset_index().rename(columns={
                'Date':         'date',
                'Open':         'open',
                'High':         'high',
                'Low':          'low',
                'Close':        'close',
                'Volume':       'volume',
                'Dividends':    'dividends',
                'Stock Splits':'stock_splits'
            })
            # Ensure dividends & splits always exist
            for col in ('dividends', 'stock_splits'):
                if col not in df.columns:
                    df[col] = 0.0
            return df
        except Exception as e:
            logging.error(f"Error fetching {symbol} (attempt {attempt}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    logging.error(f"Failed to fetch {symbol} after {MAX_RETRIES} attempts.")
    return None

def main():
    logging.info(f"Starting {SCRIPT_NAME}")
    user, pwd, host, port, db = get_db_config()

    # Connect
    try:
        conn = psycopg2.connect(
            host=host, port=port,
            user=user, password=pwd, dbname=db
        )
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=RealDictCursor)
        logging.info("Connected to Postgres.")
    except Exception as e:
        logging.error(f"Cannot connect to Postgres: {e}")
        sys.exit(1)

    # Ensure last_updated table exists
    cur.execute("""
    CREATE TABLE IF NOT EXISTS last_updated (
        script_name VARCHAR(255) PRIMARY KEY,
        last_run   TIMESTAMP
    );
    """)

    # Load symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    symbols = [r["symbol"] for r in cur.fetchall()]
    logging.info(f"Found {len(symbols)} symbols to update.")

    today_date = datetime.now().date()
    today_str  = today_date.strftime("%Y-%m-%d")

    # Common upsert SQL
    UPSERT_SQL = """
    INSERT INTO price_data_daily
      (symbol, date, open, high, low, close, volume, dividends, stock_splits)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (symbol, date) DO UPDATE
      SET open         = EXCLUDED.open,
          high         = EXCLUDED.high,
          low          = EXCLUDED.low,
          close        = EXCLUDED.close,
          volume       = EXCLUDED.volume,
          dividends    = EXCLUDED.dividends,
          stock_splits = EXCLUDED.stock_splits;
    """

    for idx, sym in enumerate(symbols, start=1):
        logging.info(f"[{idx}/{len(symbols)}] Processing {sym}")

        # 1) Detect gap in historical DB vs yfinance
        cur.execute("""
            SELECT
              MIN(date) AS first_date,
              MAX(date) AS last_date,
              COUNT(*) AS row_count
            FROM price_data_daily
            WHERE symbol = %s;
        """, (sym,))
        row = cur.fetchone()
        first_date = row["first_date"]
        last_date  = row["last_date"]
        db_count   = row["row_count"] or 0

        if db_count > 0:
            # fetch yfinance history over that same span
            hist_df = fetch_daily_data(
                sym,
                first_date.strftime("%Y-%m-%d"),
                (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
            )
            yf_count = hist_df.shape[0] if hist_df is not None else 0

            if yf_count != db_count:
                logging.warning(
                    f"  → Gap detected for {sym}: "
                    f"DB has {db_count} rows from {first_date} to {last_date}, "
                    f"yfinance has {yf_count}. Repopulating full history."
                )
                # delete old
                cur.execute(
                    "DELETE FROM price_data_daily WHERE symbol = %s;",
                    (sym,)
                )
                # fetch entire history
                full_df = fetch_daily_data(sym, "1800-01-01", today_str)
                if full_df is not None and not full_df.empty:
                    full_df["symbol"] = sym
                    ins = full_df[[
                        "symbol","date","open","high","low","close",
                        "volume","dividends","stock_splits"
                    ]].where(pd.notnull(full_df), None)
                    rows = list(ins.itertuples(index=False, name=None))
                    cur.executemany(UPSERT_SQL, rows)
                    logging.info(f"  → Repopulated {len(rows)} rows for {sym}.")
                else:
                    logging.error(f"  → Failed to fetch full history for {sym}.")
                # skip incremental for this symbol
                continue

        # 2) No gap (or first-ever load) → incremental + upsert
        if last_date:
            start_date = last_date
        else:
            start_date = datetime(1800,1,1).date()
        start_str = start_date.strftime("%Y-%m-%d")

        df = fetch_daily_data(sym, start_str, today_str)
        if df is None or df.empty:
            logging.info(f"  → No new data for {sym} from {start_str} to {today_str}.")
            continue

        df["symbol"] = sym
        to_ins = df[[
            "symbol","date","open","high","low","close",
            "volume","dividends","stock_splits"
        ]].where(pd.notnull(df), None)
        rows = list(to_ins.itertuples(index=False, name=None))

        try:
            cur.executemany(UPSERT_SQL, rows)
            logging.info(f"  → Upserted {len(rows)} rows for {sym}.")
        except Exception as e:
            logging.error(f"  → DB error for {sym}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    # 3) Record this run
    now = datetime.now()
    cur.execute("""
    INSERT INTO last_updated (script_name, last_run)
    VALUES (%s, %s)
    ON CONFLICT (script_name) DO UPDATE
      SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME, now))

    cur.close()
    conn.close()
    logging.info("Done.")

if __name__ == "__main__":
    main()
