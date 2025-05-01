#!/usr/bin/env python3
import time
import logging
from datetime import datetime
import json
import boto3
import pymysql
import pandas as pd
import yfinance as yf
from os import getenv

# -------------------------------
# Script metadata
# -------------------------------
SCRIPT_NAME = "loadpricedaily.py"

# -------------------------------
# Environment-driven configuration
# -------------------------------
DB_HOST       = getenv("DB_ENDPOINT")
DB_PORT       = int(getenv("DB_PORT", "3306"))
DB_NAME       = getenv("DB_NAME")
DB_SECRET_ARN = getenv("DB_SECRET_ARN")

def get_db_creds():
    """Fetch username/password from AWS Secrets Manager."""
    client = boto3.client("secretsmanager")
    resp   = client.get_secret_value(SecretId=DB_SECRET_ARN)
    sec    = json.loads(resp["SecretString"])
    return sec["username"], sec["password"]

# Retrieve credentials
DB_USER, DB_PWD = get_db_creds()

# Build pymysql config
db_config = {
    "host":         DB_HOST,
    "port":         DB_PORT,
    "user":         DB_USER,
    "password":     DB_PWD,
    "database":     DB_NAME,
    "cursorclass":  pymysql.cursors.DictCursor,
    "autocommit":   True,
    # If your RDS requires SSL, uncomment and adjust the path:
    # "ssl": {"ca": "/path/to/rds-combined-ca-bundle.pem"}
}

# -------------------------------
# Setup Logging
# -------------------------------
logging.basicConfig(
    filename="failed_fetch.log",
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -------------------------------
# Connect to MySQL
# -------------------------------
conn   = pymysql.connect(**db_config)
cursor = conn.cursor()
print("Connected to the database.")

# -------------------------------
# Ensure last_updated table exists
# -------------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(255) PRIMARY KEY,
    last_run   DATETIME
);
""")
conn.commit()

# -------------------------------
# Recreate price_data_daily Table
# -------------------------------
cursor.execute("DROP TABLE IF EXISTS price_data_daily;")
conn.commit()
cursor.execute("""
CREATE TABLE price_data_daily (
    symbol       VARCHAR(20),
    date         DATE,
    open         DECIMAL(20,4),
    high         DECIMAL(20,4),
    low          DECIMAL(20,4),
    close        DECIMAL(20,4),
    volume       BIGINT,
    dividends    DECIMAL(20,4),
    stock_splits DECIMAL(20,4),
    PRIMARY KEY (symbol, date)
);
""")
conn.commit()
print("Table 'price_data_daily' created.")

# -------------------------------
# Load Symbols
# -------------------------------
cursor.execute("SELECT symbol FROM stock_symbols;")
symbols = [row['symbol'] for row in cursor.fetchall()]
print(f"Found {len(symbols)} symbols.")

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
            df.setdefault('dividends',    0.0)
            df.setdefault('stock_splits', 0.0)
            return df
        except Exception as e:
            logging.error(f"Error fetching {symbol} (attempt {attempt}): {e}")
            print(f"Error fetching {symbol} (attempt {attempt}), retrying in {RETRY_DELAY}s…")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    logging.error(f"Failed to fetch {symbol} after {MAX_RETRIES} attempts.")
    return None

# -------------------------------
# Main Loop
# -------------------------------
start = datetime(1800,1,1).strftime("%Y-%m-%d")
end   = datetime.now().strftime("%Y-%m-%d")

for idx, sym in enumerate(symbols, start=1):
    print(f"[{idx}/{len(symbols)}] {sym}")
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
        conn.commit()
        print(f"  Inserted {len(rows)} rows for {sym}.")
    except Exception as e:
        logging.error(f"DB error for {sym}: {e}")
        print(f"  Error inserting {sym} – see log.")

    time.sleep(RATE_LIMIT_DELAY)

# -------------------------------
# Record this run in last_updated
# -------------------------------
now = datetime.now()
cursor.execute("""
INSERT INTO last_updated (script_name, last_run)
VALUES (%s, %s)
ON DUPLICATE KEY UPDATE last_run = VALUES(last_run);
""", (SCRIPT_NAME, now))
conn.commit()

# -------------------------------
# Clean up
# -------------------------------
cursor.close()
conn.close()
print("Done.")
