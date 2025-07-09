#!/usr/bin/env python3
# Updated for deployment verification test
import sys
import time
import logging
import json
import os
import gc
import resource
import math

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import yfinance as yf

SCRIPT_NAME = "loadanalystupgradedowngrade.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

def create_table(cur):
    logging.info("Recreating analyst_upgrade_downgrade table…")
    cur.execute("DROP TABLE IF EXISTS analyst_upgrade_downgrade;")
    cur.execute("""
        CREATE TABLE analyst_upgrade_downgrade (
            id           SERIAL PRIMARY KEY,
            symbol       VARCHAR(20) NOT NULL,
            firm         VARCHAR(128),
            action       VARCHAR(32),
            from_grade   VARCHAR(64),
            to_grade     VARCHAR(64),
            date         DATE NOT NULL,
            details      TEXT,
            fetched_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

def fetch_analyst_actions(symbol):
    # yfinance: Ticker(symbol).get_analyst_price_target_history() is not available, but recommendations is
    ticker = yf.Ticker(symbol)
    try:
        df = ticker.recommendations
    except Exception as e:
        logging.warning(f"Failed to fetch recommendations for {symbol}: {e}")
        return None
    if df is None or df.empty:
        return None
    # Only keep upgrade/downgrade actions
    df = df[df["To Grade"].notna() | df["From Grade"].notna()]
    return df

def load_analyst_actions(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading analyst upgrades/downgrades: {total} symbols")
    inserted, failed = 0, []
    for idx, symbol in enumerate(symbols):
        log_mem(f"{symbol} ({idx+1}/{total})")
        df = fetch_analyst_actions(symbol)
        if df is None or df.empty:
            logging.info(f"No analyst upgrades/downgrades for {symbol}")
            continue
        rows = []
        for dt, row in df.iterrows():
            rows.append([
                symbol,
                row.get("Firm"),
                row.get("Action"),
                row.get("From Grade"),
                row.get("To Grade"),
                dt.date() if hasattr(dt, 'date') else dt,
                row.get("Details") if "Details" in row else None
            ])
        if not rows:
            continue
        sql = """
            INSERT INTO analyst_upgrade_downgrade
            (symbol, firm, action, from_grade, to_grade, date, details)
            VALUES %s
        """
        try:
            execute_values(cur, sql, rows)
            conn.commit()
            inserted += len(rows)
            logging.info(f"{symbol}: batch-inserted {len(rows)} rows")
        except Exception as e:
            logging.error(f"Failed to insert for {symbol}: {e}")
            conn.rollback()
            failed.append(symbol)
        gc.collect()
        time.sleep(0.05)
    return total, inserted, failed


def lambda_handler(event, context):
    log_mem("startup")
    cfg  = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    create_table(cur)
    conn.commit()

    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t, i, f = load_analyst_actions(stock_syms, cur, conn)

    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Analyst Upgrades/Downgrades — total: {t}, inserted: {i}, failed: {len(f)}")

    cur.close()
    conn.close()
    logging.info("All done.")
    return {
        "total": t,
        "inserted": i,
        "failed": f,
        "peak_rss_mb": peak
    }
