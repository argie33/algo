#!/usr/bin/env python3 
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
import pandas as pd

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadrecommendations.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings
# -------------------------------
MAX_BATCH_RETRIES = 2
RETRY_DELAY = 0.5  # seconds between download retries

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

def clean_value(value):
    """Convert NaN or pandas NAs to None."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    return value

def load_recommendations(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading analyst recommendations for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 3, 0.5
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping = dict(zip(yq_batch, batch))

        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")
        for yq_sym, orig_sym in mapping.items():
            recommendations = None
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    recommendations = ticker.recommendations
                    if recommendations is None or recommendations.empty:
                        raise ValueError("No recommendations data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        break
                    time.sleep(RETRY_DELAY)
            
            if recommendations is None or recommendations.empty:
                logging.error(f"Skipping {orig_sym} - failed to retrieve recommendations after {MAX_BATCH_RETRIES} attempts")
                continue
            
            try:
                data_to_insert = []
                for period, row in recommendations.iterrows():
                    strong_buy = clean_value(row.get('strongBuy', 0))
                    buy = clean_value(row.get('buy', 0))
                    hold = clean_value(row.get('hold', 0))
                    sell = clean_value(row.get('sell', 0))
                    strong_sell = clean_value(row.get('strongSell', 0))
                    
                    data_to_insert.append((
                        orig_sym, period, strong_buy, buy, hold, sell, strong_sell
                    ))

                if data_to_insert:
                    execute_values(cur, """
                        INSERT INTO analyst_recommendations (symbol, period, strong_buy, buy, hold, sell, strong_sell)
                        VALUES %s
                        ON CONFLICT (symbol, period, collected_date) DO UPDATE SET
                            strong_buy = EXCLUDED.strong_buy,
                            buy = EXCLUDED.buy,
                            hold = EXCLUDED.hold,
                            sell = EXCLUDED.sell,
                            strong_sell = EXCLUDED.strong_sell,
                            created_at = NOW()
                    """, data_to_insert)

                conn.commit()
                processed += 1
                logging.info(f"Successfully processed {orig_sym} with {len(data_to_insert)} records")

            except Exception as e:
                logging.error(f"Failed to process {orig_sym}: {str(e)}")
                failed.append(orig_sym)
                conn.rollback()

        del batch, yq_batch, mapping
        gc.collect()
        log_mem(f"Batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, processed, failed

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    log_mem("startup")

    # Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Recreate table
    logging.info("Recreating analyst_recommendations table...")
    cur.execute("DROP TABLE IF EXISTS analyst_recommendations CASCADE;")
    cur.execute("""
        CREATE TABLE analyst_recommendations (
            symbol VARCHAR(10) NOT NULL,
            period VARCHAR(10) NOT NULL,
            strong_buy INTEGER,
            buy INTEGER,
            hold INTEGER,
            sell INTEGER,
            strong_sell INTEGER,
            collected_date DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, period, collected_date)
        );
    """)
    
    # Create index for better performance
    cur.execute("CREATE INDEX idx_analyst_recommendations_symbol ON analyst_recommendations(symbol);")
    
    # Ensure last_updated table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(255) PRIMARY KEY,
            last_run    TIMESTAMPTZ NOT NULL
        );
    """)
    conn.commit()

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_recommendations(stock_syms, cur, conn)

    # Record last run
    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Stocks — total: {t_s}, processed: {p_s}, failed: {len(f_s)}")

    cur.close()
    conn.close()
    logging.info("All done.")
