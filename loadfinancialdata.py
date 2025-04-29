#!/usr/bin/env python3
import json
import time
import logging
import functools

import boto3
import psycopg2
from psycopg2.extras import DictCursor
import requests
from yahooquery import Ticker
import pandas as pd
import math
import re
from os import getenv

# -------------------------------
# Script metadata
# -------------------------------
SCRIPT_NAME = "loadfinancialdata.py"

# -------------------------------
# Environment-driven configuration
# -------------------------------
PG_HOST       = getenv("DB_ENDPOINT")
PG_PORT       = int(getenv("DB_PORT", "5432"))
PG_DB         = getenv("DB_NAME")
DB_SECRET_ARN = getenv("DB_SECRET_ARN")

# --- Logging setup ---
logging.basicConfig(
    filename="loadfinancialdata.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(message)s"
)

def get_db_creds():
    """Fetch username/password from Secrets Manager."""
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return sec["username"], sec["password"]

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
    # build upsert
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
    # 1. get creds & open connection
    user, pwd = get_db_creds()
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=user, password=pwd,
        dbname=PG_DB, sslmode="require",
        cursor_factory=DictCursor
    )
    ensure_tables(conn)

    # 2. fetch symbols
    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM stock_symbols;")
        symbols = [r["symbol"] for r in cur.fetchall()]

    # 3. process each
    for s in symbols:
        try:
            process_symbol(s, conn)
        except Exception as e:
            logging.error(f"Failed symbol {s}: {e}", exc_info=True)

    # 4. record run time
    update_last_run(conn)
    conn.close()
    print("loadfinancialdata complete.")

if __name__ == "__main__":
    main()
