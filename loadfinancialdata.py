#!/usr/bin/env python3
import sys
import time
import os
import json
import logging
import functools
import math

import pandas as pd
from yahooquery import Ticker

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadfinancialdata.py"
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

def pg_connect():
    """Open a new PostgreSQL connection (with SSL)."""
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=pwd,
        dbname=db,
        sslmode="require"
    )
    conn.autocommit = True
    return conn

# -------------------------------
# Create financial_data table
# -------------------------------
def create_financial_data_table():
    conn = pg_connect()
    cur = conn.cursor()
    logging.info("Dropping table financial_data if it exists.")
    cur.execute("DROP TABLE IF EXISTS financial_data;")
    logging.info("Creating table financial_data.")
    cur.execute("""
        CREATE TABLE financial_data (
          symbol               VARCHAR(20) PRIMARY KEY,
          maxage               INT,
          currentprice         DOUBLE PRECISION,
          targethighprice      DOUBLE PRECISION,
          targetlowprice       DOUBLE PRECISION,
          targetmeanprice      DOUBLE PRECISION,
          targetmedianprice    DOUBLE PRECISION,
          recommendationmean   DOUBLE PRECISION,
          recommendationkey    VARCHAR(20),
          numberofanalystopinions INT,
          totalcash            DOUBLE PRECISION,
          totalcashpershare    DOUBLE PRECISION,
          ebitda               DOUBLE PRECISION,
          totaldebt            DOUBLE PRECISION,
          quickratio           DOUBLE PRECISION,
          currentratio         DOUBLE PRECISION,
          totalrevenue         DOUBLE PRECISION,
          debttoequity         DOUBLE PRECISION,
          revenuepershare      DOUBLE PRECISION,
          returnonassets       DOUBLE PRECISION,
          returnonequity       DOUBLE PRECISION,
          grossprofits         DOUBLE PRECISION,
          freecashflow         DOUBLE PRECISION,
          operatingcashflow    DOUBLE PRECISION,
          earningsgrowth       DOUBLE PRECISION,
          revenuegrowth        DOUBLE PRECISION,
          grossmargins         DOUBLE PRECISION,
          ebitdamargins        DOUBLE PRECISION,
          operatingmargins     DOUBLE PRECISION,
          profitmargins        DOUBLE PRECISION,
          financialcurrency    VARCHAR(10),
          fetched_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    logging.info("Ensuring last_updated table exists.")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS last_updated (
          script_name   VARCHAR(255) PRIMARY KEY,
          last_run      TIMESTAMPTZ NOT NULL
        );
    """)
    cur.close()
    conn.close()
    logging.info("financial_data schema ready.")

# -------------------------------
# Helpers to clean data
# -------------------------------
def clean_row(row):
    """Convert NaN or pandas NAs to None."""
    out = {}
    for k, v in row.items():
        if isinstance(v, float) and math.isnan(v):
            out[k] = None
        elif pd.isna(v):
            out[k] = None
        else:
            out[k] = v
    return out

# -------------------------------
# Retry decorator
# -------------------------------
def retry(max_attempts=3, initial_delay=2, backoff=2):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(symbol):
            attempts = 0
            delay = initial_delay
            while attempts < max_attempts:
                try:
                    return func(symbol)
                except Exception as e:
                    attempts += 1
                    logging.error(
                        f"Attempt {attempts} for {func.__name__}({symbol}) failed: {e}",
                        exc_info=True
                    )
                    time.sleep(delay)
                    delay *= backoff
            logging.error(f"All {max_attempts} attempts failed for {func.__name__} on {symbol}")
        return wrapper
    return decorator

# -------------------------------
# Per-symbol processing
# -------------------------------
@retry(max_attempts=3)
def process_symbol(symbol):
    """Fetch financial_data via yahooquery and insert into PostgreSQL."""
    yq_sym = symbol.upper().replace('.', '-')
    logging.info(f"Fetching financial_data for {symbol}")
    raw = Ticker(yq_sym).financial_data.get(yq_sym)
    if not isinstance(raw, dict):
        logging.warning(f"No financial_data for {symbol}; skipping")
        return

    data = {k.lower(): v for k, v in raw.items()}
    row = clean_row(data)

    conn = pg_connect()
    cur = conn.cursor()
    cols = [
        "symbol","maxage","currentprice","targethighprice","targetlowprice",
        "targetmeanprice","targetmedianprice","recommendationmean","recommendationkey",
        "numberofanalystopinions","totalcash","totalcashpershare","ebitda","totaldebt",
        "quickratio","currentratio","totalrevenue","debttoequity","revenuepershare",
        "returnonassets","returnonequity","grossprofits","freecashflow","operatingcashflow",
        "earningsgrowth","revenuegrowth","grossmargins","ebitdamargins","operatingmargins",
        "profitmargins","financialcurrency"
    ]
    placeholders = ", ".join(["%s"] * len(cols))
    values = [symbol] + [row.get(c) for c in cols[1:]]
    sql = f"INSERT INTO financial_data ({','.join(cols)}) VALUES ({placeholders});"
    cur.execute(sql, values)
    cur.close()
    conn.close()
    logging.info(f"Inserted data for {symbol}")

# -------------------------------
# Update last_updated stamp
# -------------------------------
def update_last_updated():
    conn = pg_connect()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
          SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    cur.close()
    conn.close()

# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    create_financial_data_table()

    # load list of symbols
    conn = pg_connect()
    cur  = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT DISTINCT symbol FROM stock_symbols;")
    symbols = [r["symbol"] for r in cur.fetchall()]
    cur.close()
    conn.close()

    # process each
    for sym in symbols:
        process_symbol(sym)
        time.sleep(0.1)

    update_last_updated()
    logging.info("All symbols processed.")
