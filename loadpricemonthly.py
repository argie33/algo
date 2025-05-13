#!/usr/bin/env python3
import sys
import time
import logging
from datetime import datetime
import json
import os

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import pandas as pd
import yfinance as yf

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadpricemonthly.py"
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

# --- start up ---
logging.info(f"Starting {SCRIPT_NAME}")
DB_USER, DB_PWD, DB_HOST, DB_PORT, DB_NAME = get_db_config()

# --- connect to Postgres ---
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

# --- ensure tables exist / fresh monthly table ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(255) PRIMARY KEY,
    last_run   TIMESTAMP
);
""")
cursor.execute("DROP TABLE IF EXISTS price_data_monthly;")
cursor.execute("""
CREATE TABLE price_data_monthly (
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
logging.info("Table 'price_data_monthly' is ready.")

# --- load the list of symbols ---
cursor.execute("SELECT symbol FROM stock_symbols;")
symbols = [r['symbol'] for r in cursor.fetchall()]
logging.info(f"Found {len(symbols)} symbols.")

# --- parameters for fetch retries ---
MAX_RETRIES      = 3        # number of attempts per symbol
RETRY_DELAY      = 5        # seconds between retries
RATE_LIMIT_DELAY = 1        # seconds between symbols

def fetch_monthly_data(symbol):
    """
    Uses yfinance.download to grab the full monthly history.
    """
    yf_sym = symbol.replace('.', '-')
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = yf.download(
                yf_sym,
                period="max",
                interval="1mo",
                actions=True,
                progress=False
            )
            if df is None or df.empty:
                raise ValueError("No data returned")
            # normalize & rename
            df = df.reset_index().rename(columns={
                'Date':          'date',
                'Open':          'open',
                'High':          'high',
                'Low':           'low',
                'Close':         'close',
                'Volume':        'volume',
                'Dividends':     'dividends',
                'Stock Splits':  'stock_splits'
            })
            # ensure both columns exist
            for col in ('dividends', 'stock_splits'):
                if col not in df.columns:
                    df[col] = 0.0
            df['symbol'] = symbol
            return df
        except Exception as e:
            logging.error(f"Error fetching {symbol} (attempt {attempt}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    logging.error(f"Failed to fetch {symbol} after {MAX_RETRIES} attempts")
    return None

# --- main loop: fetch & bulk insert ---
for idx, sym in enumerate(symbols, start=1):
    logging.info(f"[{idx}/{len(symbols)}] Fetching monthly data for {sym}")
    df = fetch_monthly_data(sym)
    if df is None:
        continue

    # prepare rows for bulk insert
    to_ins = df[['symbol','date','open','high','low','close','volume','dividends','stock_splits']]\
               .where(pd.notnull(df), None)
    rows = list(to_ins.itertuples(index=False, name=None))

    insert_sql = """
    INSERT INTO price_data_monthly
      (symbol, date, open, high, low, close, volume, dividends, stock_splits)
    VALUES %s
    ON CONFLICT (symbol, date) DO NOTHING
    """
    try:
        execute_values(cursor, insert_sql, rows, page_size=500)
        logging.info(f"Inserted {len(rows)} rows for {sym}")
    except Exception as e:
        logging.error(f"DB error for {sym}: {e}")

    time.sleep(RATE_LIMIT_DELAY)

# --- update last_updated ---
now = datetime.now()
cursor.execute("""
INSERT INTO last_updated (script_name, last_run)
VALUES (%s, %s)
ON CONFLICT (script_name) DO UPDATE
  SET last_run = EXCLUDED.last_run
""", (SCRIPT_NAME, now))
logging.info("Updated last_updated timestamp.")

cursor.close()
conn.close()
logging.info("Done.")
