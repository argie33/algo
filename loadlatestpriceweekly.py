#!/usr/bin/env python3
import sys
import time
import logging
import os
import json
import boto3
import psycopg2
from psycopg2.extras import DictCursor
import yfinance as yf
import pandas as pd

SCRIPT_NAME = "loadlatestpriceweekly.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")
if not DB_SECRET_ARN:
    logger.error("DB_SECRET_ARN environment variable is not set")
    sys.exit(1)

def get_db_config():
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

def ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS latest_price_weekly (
                symbol VARCHAR(10) NOT NULL,
                price DOUBLE PRECISION,
                currency VARCHAR(10),
                price_date DATE NOT NULL,
                fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(symbol, price_date)
            );
        """)
    conn.commit()

def fetch_and_store(symbol, conn):
    ticker = yf.Ticker(symbol)
    try:
        df = ticker.history(period="1wk", interval="1wk")
        if not df.empty:
            price = df["Close"].iloc[-1]
            price_date = df.index[-1].date()
            currency = ticker.info.get("currency", None)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO latest_price_weekly (symbol, price, currency, price_date, fetched_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (symbol, price_date) DO UPDATE SET price=EXCLUDED.price, currency=EXCLUDED.currency, fetched_at=NOW();
                """, (symbol, price, currency, price_date))
            conn.commit()
            logger.info(f"Inserted/Updated {symbol} for {price_date} with price {price}")
    except Exception as e:
        logger.error(f"Error fetching/storing {symbol}: {e}")

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
    ensure_table(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM stock_symbols WHERE is_active = true ORDER BY symbol;")
        symbols = [r["symbol"] for r in cur.fetchall()]
    for symbol in symbols:
        fetch_and_store(symbol, conn)
    conn.close()

if __name__ == "__main__":
    main()
