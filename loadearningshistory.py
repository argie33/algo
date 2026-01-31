#!/usr/bin/env python3
# FORCE RUN NOW: 2026-01-30_090000 - All task definitions ready - executing earnings history loader NOW
# Database population with full earnings history records
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
import numpy as np

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadearningshistory.py"
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
MAX_BATCH_RETRIES = 5
INITIAL_RETRY_DELAY = 2.0  # seconds, will use exponential backoff - increased to avoid rate limiting
BATCH_PAUSE = 8.0  # pause between symbols in a batch - yfinance free tier MAX ~20 req/min, increased to avoid rate limiting with concurrent loaders
# Total expected processing time: ~5070 symbols * 20 symbols/batch * 8s pause = ~2000s = 33 minutes baseline
# With retries and concurrent loaders, could extend to 60+ minutes

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    """Get database configuration from AWS Secrets Manager.

    REQUIRES AWS_REGION and DB_SECRET_ARN environment variables to be set.
    No fallbacks - fails loudly if AWS is not configured.
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if not aws_region:
        raise EnvironmentError(
            "FATAL: AWS_REGION not set. Real data requires AWS configuration."
        )
    if not db_secret_arn:
        raise EnvironmentError(
            "FATAL: DB_SECRET_ARN not set. Real data requires AWS Secrets Manager configuration."
        )

    try:
        secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
            SecretId=db_secret_arn
        )["SecretString"]
        sec = json.loads(secret_str)
        logging.info(f"Loaded real database credentials from AWS Secrets Manager: {db_secret_arn}")
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception as e:
        raise EnvironmentError(
            f"FATAL: Cannot load database credentials from AWS Secrets Manager ({db_secret_arn}). "
            f"Error: {e.__class__.__name__}: {str(e)[:200]}\n"
            f"Ensure AWS credentials are configured and Secrets Manager is accessible.\n"
            f"Real data requires proper AWS setup - no fallbacks allowed."
        )
def create_tables(cur):
    logging.info("Setting up earnings history table...")

    # Create earnings_history table if not exists (INCREMENTAL, don't drop)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS earnings_history (
            symbol VARCHAR(20) NOT NULL,
            quarter DATE NOT NULL,
            eps_actual NUMERIC,
            eps_estimate NUMERIC,
            eps_difference NUMERIC,
            surprise_percent NUMERIC,
            fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, quarter)
        );
    """)

def pyval(val):
    # Convert numpy types to native Python types
    if isinstance(val, (np.generic,)):
        return val.item()
    return val

def load_earnings_history(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading earnings history for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE = 20
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        # Handle preferred shares (symbols with $): use base ticker for yfinance
        yq_batch = []
        for s in batch:
            if '$' in s:
                # CADE$A -> CADE (use base ticker for preferred shares)
                base_ticker = s.split('$')[0]
                yq_batch.append(base_ticker)
            else:
                # Normal ticker conversion
                yq_batch.append(s.replace('.', '-').upper())
        mapping = dict(zip(yq_batch, batch))

        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")

        for yq_sym, orig_sym in mapping.items():
            earnings_history = None
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    earnings_history = ticker.earnings_history
                    if earnings_history is None or earnings_history.empty:
                        if attempt < MAX_BATCH_RETRIES:
                            # Retry on empty data (might be temporary)
                            retry_delay = INITIAL_RETRY_DELAY * (1.5 ** (attempt - 1))
                            logging.info(f"  ⏳ Waiting {retry_delay:.1f}s before retry {attempt+1}/{MAX_BATCH_RETRIES}...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            raise ValueError("No earnings history data received after retries")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        break
                    # Exponential backoff: 1s, 1.5s, 2.25s, 3.375s, etc.
                    retry_delay = INITIAL_RETRY_DELAY * (1.5 ** (attempt - 1))
                    logging.info(f"  ⏳ Waiting {retry_delay:.1f}s before retry {attempt+1}/{MAX_BATCH_RETRIES}...")
                    time.sleep(retry_delay)

            try:
                if earnings_history is not None and not earnings_history.empty:
                    history_data = []
                    for quarter, row in earnings_history.iterrows():
                        # Parse the quarter index which is typically in the format YYYY-MM-DD
                        quarter_date = str(quarter)

                        history_data.append((
                            orig_sym, quarter_date,
                            pyval(row.get('epsActual')),
                            pyval(row.get('epsEstimate')),
                            pyval(row.get('epsDifference')),
                            pyval(row.get('surprisePercent'))
                        ))

                    if history_data:
                        execute_values(cur, """
                            INSERT INTO earnings_history (
                                symbol, quarter, eps_actual, eps_estimate,
                                eps_difference, surprise_percent
                            ) VALUES %s
                            ON CONFLICT (symbol, quarter) DO UPDATE SET
                                eps_actual = EXCLUDED.eps_actual,
                                eps_estimate = EXCLUDED.eps_estimate,
                                eps_difference = EXCLUDED.eps_difference,
                                surprise_percent = EXCLUDED.surprise_percent,
                                fetched_at = CURRENT_TIMESTAMP
                        """, history_data)
                        processed += 1
                        conn.commit()
                        logging.info(f"Successfully processed {orig_sym}")
            except Exception as e:
                logging.error(f"Failed to insert data for {orig_sym}: {e}")
                conn.rollback()
                failed.append(orig_sym)

            gc.collect()
            time.sleep(BATCH_PAUSE)
    
    return total, processed, failed

def lambda_handler(event, context):
    log_mem("startup")
    cfg = get_db_config()
    if cfg["host"]:
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg.get("port", 5432),
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
    else:
        # Socket connection (peer auth)
        conn = psycopg2.connect(
            dbname=cfg["dbname"],
            user=cfg["user"]
        )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    create_tables(cur)
    conn.commit()

    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t, p, f = load_earnings_history(stock_syms, cur, conn)

    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Earnings History — total: {t}, processed: {p}, failed: {len(f)}")

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
