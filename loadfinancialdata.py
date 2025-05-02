#!/usr/bin/env python3
import json
import time
import logging
import functools
import os

import boto3
import psycopg2
from psycopg2.extras import DictCursor
import requests
from yahooquery import Ticker
import pandas as pd
import math

# -------------------------------
# Script metadata
# -------------------------------
SCRIPT_NAME = "loadfinancialdata.py"

# -------------------------------
# Environment-driven configuration
# -------------------------------
DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")

# --- Logging setup ---
logging.basicConfig(
    filename="loadfinancialdata.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(message)s"
)

def get_db_config():
    """Fetch host, port, dbname, username & password from Secrets Manager."""
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

def retry(max_attempts=3, initial_delay=2, backoff=2):
    """Retry decorator with exponential backoff."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(symbol, *args, **kwargs):
            attempts, delay = 0, initial_delay
            while attempts < max_attempts:
                try:
                    return f(symbol, *args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logging.error(f"{f.__name__} failed for {symbol} (attempt {attempts}): {e}", exc_info=True)
                    time.sleep(delay)
                    delay *= backoff
            raise RuntimeError(f"All {max_attempts} attempts failed for {f.__name__} with symbol {symbol}")
        return wrapper
    return decorator

def ensure_tables(conn):
    """Create tables if they don't exist, with upsert support on symbol."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS financial_data (
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS last_updated (
              script_name   VARCHAR(255) PRIMARY KEY,
              last_run      TIMESTAMPTZ NOT NULL
            );
        """)
    conn.commit()

def clean_row(row):
    """Convert NaN or pandas NAs to None."""
    clean = {}
    for k, v in row.items():
        if isinstance(v, float) and math.isnan(v):
            clean[k] = None
        elif pd.isna(v):
            clean[k] = None
        else:
            clean[k] = v
    return clean

@retry(max_attempts=3)
def process_symbol(symbol, conn):
    """Fetch from YahooQuery & upsert into PostgreSQL."""
    yq_symbol = symbol.replace(".", "-").lower()
    ticker = Ticker(yq_symbol)
    data = ticker.financial_data.get(yq_symbol)
    if not isinstance(data, dict):
        raise ValueError(f"Bad payload for {symbol}: {data!r}")

    row = clean_row(data)
    cols = [
        "symbol","maxage","currentprice","targethighprice","targetlowprice",
        "targetmeanprice","targetmedianprice","recommendationmean","recommendationkey",
        "numberofanalystopinions","totalcash","totalcashpershare","ebitda","totaldebt",
        "quickratio","currentratio","totalrevenue","debttoequity","revenuepershare",
        "returnonassets","returnonequity","grossprofits","freecashflow","operatingcashflow",
        "earningsgrowth","revenuegrowth","grossmargins","ebitdamargins","operatingmargins",
        "profitmargins","financialcurrency"
    ]
    values = [ row.get(c) for c in cols[1:] ]
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join([f"{c}=EXCLUDED.{c}" for c in cols[1:]])
    sql = f"""
        INSERT INTO financial_data ({','.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(symbol) DO UPDATE
          SET {updates}, fetched_at = NOW();
    """
    with conn.cursor() as cur:
        cur.execute(sql, [symbol] + values)
    conn.commit()

def update_last_run(conn):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE
              SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME,))
    conn.commit()

def main():
    # 1) get all DB connection info from Secrets Manager
    user, pwd, host, port, dbname = get_db_config()

    # 2) open a TCP connection (no local socket)
    conn = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=pwd,
        dbname=dbname,
        sslmode="require",
        cursor_factory=DictCursor
    )

    ensure_tables(conn)

    # 3) fetch symbols
    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM stock_symbols;")
        symbols = [r["symbol"] for r in cur.fetchall()]

    # 4) process each symbol
    for s in symbols:
        try:
            process_symbol(s, conn)
        except Exception as e:
            logging.error(f"Failed symbol {s}: {e}", exc_info=True)

    # 5) record run time
    update_last_run(conn)
    conn.close()
    print("loadfinancialdata complete.")

if __name__ == "__main__":
    main()
