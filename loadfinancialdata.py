#!/usr/bin/env python3
import json
import time
import logging
import functools
import os
import sys

import boto3
import psycopg2
from psycopg2.extras import DictCursor
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Timeout
from urllib3.util.retry import Retry

from yahooquery import Ticker
from yahooquery.utils import TimeoutHTTPAdapter

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

# --- Logging setup: output to both file and stdout for ECS to capture ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(message)s",
    handlers=[
        logging.FileHandler("loadfinancialdata.log"),
        logging.StreamHandler(sys.stdout),
    ]
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
                except requests.exceptions.RequestException as e:
                    attempts += 1
                    logging.error(f"{f.__name__} network error for {symbol} (attempt {attempts}): {e}", exc_info=True)
                except Exception as e:
                    attempts += 1
                    logging.error(f"{f.__name__} failed for {symbol} (attempt {attempts}): {e}", exc_info=True)
                time.sleep(delay)
                delay *= backoff
            raise RuntimeError(f"All {max_attempts} attempts failed for {f.__name__} with symbol {symbol}")
        return wrapper
    return decorator

def ensure_tables(conn):
    """Drop and recreate the financial_data table, plus ensure last_updated exists."""
    with conn.cursor() as cur:
        # drop the data table if it exists
        cur.execute("DROP TABLE IF EXISTS financial_data;")
        # now create fresh financial_data
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
        # last_updated we keep around, so only create if missing
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
    """Fetch from yahooquery & upsert into PostgreSQL, skipping symbols with no data."""
    yq_symbol = symbol.upper().replace(".", "-")
    ticker = Ticker(yq_symbol, asynchronous=False)

    # mount adapter with explicit timeout
    adapter = TimeoutHTTPAdapter(
        max_retries=Retry(total=2, backoff_factor=1),
        timeout=10.0
    )
    ticker.session.mount("https://", adapter)
    ticker.session.mount("http://", adapter)

    raw = ticker.financial_data.get(yq_symbol)
    if raw is None:
        logging.warning(f"No financial_data for {symbol}; skipping")
        return

    if not isinstance(raw, dict):
        raise ValueError(f"Bad payload for {symbol}: {raw!r}")

    data = {k.lower(): v for k, v in raw.items()}
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
    values = [row.get(c) for c in cols[1:]]
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join([f"{c}=EXCLUDED.{c}" for c in cols[1:]])

    diff_conds = " OR ".join(
        f"financial_data.{c} IS DISTINCT FROM EXCLUDED.{c}" for c in cols[1:]
    )

    sql = f"""
        INSERT INTO financial_data ({','.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(symbol) DO UPDATE
          SET {updates}, fetched_at = NOW()
          WHERE {diff_conds};
    """
    with conn.cursor() as cur:
        cur.execute(sql, [symbol] + values)
    conn.commit()
    logging.info(f"✅ upserted {symbol}")

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
    user, pwd, host, port, dbname = get_db_config()
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

    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM stock_symbols;")
        symbols = [r["symbol"] for r in cur.fetchall()]

    for s in symbols:
        try:
            process_symbol(s, conn)
        except Exception as e:
            logging.error(f"Failed symbol {s}: {e}", exc_info=True)

    update_last_run(conn)
    conn.close()
    print("loadfinancialdata complete.")

if __name__ == "__main__":
    main()
