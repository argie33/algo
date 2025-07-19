#!/usr/bin/env python3 
# Updated for deployment verification test - trigger v1.7 - Circuit breaker database integration
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

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadearningsestimate.py"
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
MAX_BATCH_RETRIES = 3
RETRY_DELAY = 0.2  # seconds between download retries

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

def create_tables(cur):
    logging.info("Recreating earnings estimates table...")
    
    # Drop and recreate earnings estimates table
    cur.execute("DROP TABLE IF EXISTS earnings_estimates CASCADE;")
    
    # Create earnings_estimates table
    cur.execute("""
        CREATE TABLE earnings_estimates (
            symbol VARCHAR(20) NOT NULL,
            period VARCHAR(3) NOT NULL,
            avg_estimate NUMERIC,
            low_estimate NUMERIC,
            high_estimate NUMERIC,
            year_ago_eps NUMERIC,
            number_of_analysts INTEGER,
            growth NUMERIC,
            fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, period)
        );
    """)

def load_earnings_data(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading earnings estimates for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping = dict(zip(yq_batch, batch))

        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")

        for yq_sym, orig_sym in mapping.items():
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    earnings_est = ticker.earnings_estimate
                    if earnings_est is None or earnings_est.empty:
                        raise ValueError("No earnings estimate data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        continue
                    time.sleep(RETRY_DELAY)

            try:
                if earnings_est is not None and not earnings_est.empty:
                    earnings_data = []
                    def pyval(val):
                        # Convert numpy types to native Python types
                        import numpy as np
                        if isinstance(val, (np.generic,)):
                            return val.item()
                        return val
                    for period, row in earnings_est.iterrows():
                        earnings_data.append((
                            orig_sym, str(period),
                            pyval(row.get('avg')),
                            pyval(row.get('low')),
                            pyval(row.get('high')),
                            pyval(row.get('yearAgoEps')),
                            pyval(row.get('numberOfAnalysts')),
                            pyval(row.get('growth'))
                        ))
                    
                    if earnings_data:
                        execute_values(cur, """
                            INSERT INTO earnings_estimates (
                                symbol, period, avg_estimate, low_estimate,
                                high_estimate, year_ago_eps, number_of_analysts,
                                growth
                            ) VALUES %s
                            ON CONFLICT (symbol, period) DO UPDATE SET
                                avg_estimate = EXCLUDED.avg_estimate,
                                low_estimate = EXCLUDED.low_estimate,
                                high_estimate = EXCLUDED.high_estimate,
                                year_ago_eps = EXCLUDED.year_ago_eps,
                                number_of_analysts = EXCLUDED.number_of_analysts,
                                growth = EXCLUDED.growth,
                                fetched_at = CURRENT_TIMESTAMP
                        """, earnings_data)
                        processed += 1
                        conn.commit()
                        logging.info(f"Successfully processed {orig_sym}")
            except Exception as e:
                logging.error(f"Failed to insert data for {orig_sym}: {e}")
                conn.rollback()
                failed.append(orig_sym)
            
            gc.collect()
            time.sleep(PAUSE)
    
    return total, processed, failed

def lambda_handler(event, context):
    log_mem("startup")
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"],
        sslmode="require"
        )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    create_tables(cur)
    conn.commit()

    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t, p, f = load_earnings_data(stock_syms, cur, conn)

    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Earnings Estimates — total: {t}, processed: {p}, failed: {len(f)}")

    cur.close()
    conn.close()
    logging.info("All done.")
    return {
        "total": t,
        "processed": p,
        "failed": f,
        "peak_rss_mb": peak
    }

if __name__ == "__main__":
    lambda_handler(None, None)