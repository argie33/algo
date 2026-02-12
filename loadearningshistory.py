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
MAX_BATCH_RETRIES = 3
INITIAL_RETRY_DELAY = 0.5  # seconds, exponential backoff
BATCH_PAUSE = 0.1  # minimal pause - yfinance handles rate limiting internally
# Optimized for speed: ~10,000 symbols * 0.1s pause = ~1000s = 16 minutes

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    """Get database configuration - works in AWS and locally.

    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    # Try AWS Secrets Manager first
    if db_secret_arn and aws_region:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logging.info(f"Using AWS Secrets Manager for database config")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")

    # Fall back to environment variables
    logging.info("Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

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

def load_earnings_history(symbols, cur, conn, cfg):
    # Load earnings data for ALL symbols - no filtering
    # yfinance will return empty if no data available

    total = len(symbols)
    logging.info(f"Loading earnings history for {total} symbols (no filtering)")
    processed, failed = 0, []
    CHUNK_SIZE = 20
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        # Handle symbol conversion for yfinance
        yq_batch = []
        for s in batch:
            # Convert to yfinance format (. -> -, uppercase)
            yq_sym = s.replace('.', '-').upper()
            yq_batch.append(yq_sym)
        mapping = dict(zip(yq_batch, batch))

        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")

        for yq_sym, orig_sym in mapping.items():
            earnings_history = None
            for attempt in range(1, 4):  # Retry up to 3 times for HTTP errors
                try:
                    ticker = yf.Ticker(yq_sym)
                    earnings_history = ticker.earnings_history
                    if earnings_history is None or earnings_history.empty:
                        logging.debug(f"No data for {orig_sym}")
                        break
                    break
                except Exception as e:
                    error_str = str(e).lower()
                    # Retry on HTTP 500, 429 (rate limit), or connection errors
                    if ('500' in error_str or '429' in error_str or 'connection' in error_str) and attempt < 3:
                        logging.debug(f"Attempt {attempt}/3 failed for {orig_sym}: {e}. Retrying in 2s...")
                        time.sleep(2)
                        continue
                    else:
                        logging.debug(f"Failed to fetch {orig_sym}: {e}")
                        break

            if earnings_history is None or (isinstance(earnings_history, object) and (hasattr(earnings_history, 'empty') and earnings_history.empty)):
                failed.append(orig_sym)
                continue

            if earnings_history is not None and not earnings_history.empty:
                try:
                    history_data = []
                    for quarter, row in earnings_history.iterrows():
                        # Parse the quarter index which is typically in the format YYYY-MM-DD
                        quarter_date = str(quarter)

                        # Get all EPS values from yfinance - no filtering
                        eps_actual = pyval(row.get('epsActual'))
                        eps_estimate = pyval(row.get('epsEstimate'))
                        eps_difference = pyval(row.get('epsDifference'))
                        surprise_percent = pyval(row.get('surprisePercent'))

                        # Load ALL data as-is from yfinance
                        history_data.append((
                            orig_sym, quarter_date,
                            eps_actual,
                            eps_estimate,
                            eps_difference,
                            surprise_percent
                        ))

                    if history_data:
                        # Retry logic for database inserts
                        for db_attempt in range(1, 4):
                            try:
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
                                conn.commit()
                                processed += 1
                                logging.info(f"Successfully processed {orig_sym}")
                                break
                            except psycopg2.errors.InFailedSqlTransaction:
                                # Transaction aborted - reconnect
                                conn.rollback()
                                if db_attempt < 3:
                                    logging.debug(f"Transaction error for {orig_sym}, reconnecting...")
                                    conn.close()
                                    conn = psycopg2.connect(**cfg)
                                    cur = conn.cursor(cursor_factory=RealDictCursor)
                                    time.sleep(1)
                                else:
                                    raise
                except Exception as e:
                    logging.error(f"Failed to insert data for {orig_sym}: {e}")
                    try:
                        conn.rollback()
                    except:
                        pass
                    failed.append(orig_sym)

            gc.collect()
            time.sleep(BATCH_PAUSE)
    
    return total, processed, failed

def lambda_handler(event, context):
    try:
        log_mem("startup")
        cfg = get_db_config()
        logging.info(f"Connecting to {cfg['host']}:{cfg.get('port', 5432)}/{cfg['dbname']} as {cfg['user']}")

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

        logging.info("Database connected successfully")

        create_tables(cur)
        conn.commit()

        cur.execute("SELECT symbol FROM stock_symbols;")
        stock_syms = [r["symbol"] for r in cur.fetchall()]
        logging.info(f"Loaded {len(stock_syms)} symbols from database")

        t, p, f = load_earnings_history(stock_syms, cur, conn, cfg)

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
    except Exception as e:
        logging.error(f"FATAL ERROR in lambda_handler: {type(e).__name__}: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        lambda_handler(None, None)
    except Exception as e:
        logging.error(f"FATAL ERROR: {type(e).__name__}: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
