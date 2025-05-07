#!/usr/bin/env python3
import sys
import time
import logging
from datetime import datetime
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
SCRIPT_NAME = "loadpricedaily.py" 

# — log everything ≥ INFO to stdout, including errors on stderr —
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
# Start up
# -------------------------------
logging.info(f"Starting {SCRIPT_NAME}")
DB_USER, DB_PWD, DB_HOST, DB_PORT, DB_NAME = get_db_config()

# -------------------------------
# Connect to PostgreSQL
# -------------------------------
try:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PWD,
        dbname=DB_NAME
    )
    conn.autocommit = True
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    logging.info("Connected to PostgreSQL database.")
except Exception as e:
    logging.error(f"Unable to connect to Postgres: {e}")
    sys.exit(1)

# -------------------------------
# Ensure last_updated table exists
# -------------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(255) PRIMARY KEY,
    last_run   TIMESTAMP
);
""")

# -------------------------------
# Recreate price_data_daily Table
# -------------------------------
cursor.execute("DROP TABLE IF EXISTS price_data_daily;")
cursor.execute("""
CREATE TABLE price_data_daily (
    symbol       VARCHAR(20),
    date         DATE,
    open         NUMERIC(20,4),
    high         NUMERIC(20,4),
    low          NUMERIC(20,4),
    close        NUMERIC(20,4),
    volume       BIGINT,
    dividends    NUMERIC(20,4),
    stock_splits NUMERIC(20,4),
    PRIMARY KEY (symbol, date)
);
""")
logging.info("Table 'price_data_daily' ready.")

# -------------------------------
# Load Symbols
# -------------------------------
cursor.execute("SELECT symbol FROM stock_symbols;")
symbols = [row['symbol'] for row in cursor.fetchall()]
logging.info(f"Found {len(symbols)} symbols.")

# -------------------------------
# Fetch Function
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
            if df is None or df.empty:
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

            # Guarantee those columns exist
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

# -------------------------------
# Main Loop
# -------------------------------
start = "1800-01-01"
end   = datetime.now().strftime("%Y-%m-%d")

for idx, sym in enumerate(symbols, start=1):
    logging.info(f"[{idx}/{len(symbols)}] Fetching {sym}")
    data = fetch_daily_data(sym, start, end)
    if data is None:
        continue

    data['symbol'] = sym
    df_to_insert = data[[
        'symbol','date','open','high','low','close','volume','dividends','stock_splits'
    ]].where(pd.notnull(data), None)

    rows = list(df_to_insert.itertuples(index=False, name=None))
    sql  = """
    INSERT INTO price_data_daily
      (symbol, date, open, high, low, close, volume, dividends, stock_splits)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    try:
        cursor.executemany(sql, rows)
        logging.info(f"Inserted {len(rows)} rows for {sym}.")
    except Exception as e:
        logging.error(f"DB error for {sym}: {e}")

    time.sleep(RATE_LIMIT_DELAY)

# -------------------------------
# Record this run
# -------------------------------
now = datetime.now()
cursor.execute("""
INSERT INTO last_updated (script_name, last_run)
VALUES (%s, %s)
ON CONFLICT (script_name) DO UPDATE
  SET last_run = EXCLUDED.last_run;
""", (SCRIPT_NAME, now))

cursor.close()
conn.close()
logging.info("Done.")
