#!/usr/bin/env python3
# Updated: 2025-10-02 17:25 - Change BIGINT to NUMERIC to handle large revenue values
import gc
import json
import logging
import math
import os
import resource
import sys
import time
from datetime import datetime

import boto3
import numpy as np
import psycopg2
import psycopg2.extensions
import yfinance as yf
from psycopg2.extras import RealDictCursor, execute_values

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadrevenueestimate.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Register numpy type adapters for psycopg2
def adapt_numpy_int64(numpy_int64):
    return psycopg2.extensions.AsIs(int(numpy_int64))

def adapt_numpy_float64(numpy_float64):
    return psycopg2.extensions.AsIs(float(numpy_float64))

psycopg2.extensions.register_adapter(np.int64, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.int32, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.float64, adapt_numpy_float64)
psycopg2.extensions.register_adapter(np.float32, adapt_numpy_float64)


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
# Safe numeric conversion
# -------------------------------
def safe_int(value):
    """Safely convert value to int, handling None, NaN, numpy types, and invalid values"""
    if value is None:
        return None
    # Handle numpy types first before NaN checks
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if np.isnan(value) or np.isinf(value):
            return None
        return int(value)
    # Handle Python floats
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return int(value)
    # Handle Python ints
    if isinstance(value, int):
        return int(value)
    # Handle strings
    if isinstance(value, str):
        value = value.strip()
        if value in ["", "N/A", "null", "NULL", "nan", "NaN"]:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None
    return None


def safe_float(value):
    """Safely convert value to float, handling None, NaN, numpy types, and invalid values"""
    if value is None:
        return None
    # Handle numpy floating types first
    if isinstance(value, np.floating):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    # Handle numpy integers
    if isinstance(value, np.integer):
        return float(value)
    # Handle Python floats
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)
    # Handle Python ints
    if isinstance(value, int):
        return float(value)
    # Handle strings
    if isinstance(value, str):
        value = value.strip()
        if value in ["", "N/A", "null", "NULL", "nan", "NaN"]:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    return None


# -------------------------------
# Retry settings
# -------------------------------
MAX_BATCH_RETRIES = 3
RETRY_DELAY = 0.2  # seconds between download retries


# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager").get_secret_value(
        SecretId=os.environ["DB_SECRET_ARN"]
    )["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"],
    }


def create_tables(cur):
    logging.info("Recreating revenue estimates table...")

    # Drop and recreate revenue estimates table
    cur.execute("DROP TABLE IF EXISTS revenue_estimates CASCADE;")

    # Create revenue_estimates table with NUMERIC for large values
    cur.execute(
        """
        CREATE TABLE revenue_estimates (
            symbol VARCHAR(20) NOT NULL,
            period VARCHAR(3) NOT NULL,
            avg_estimate NUMERIC,
            low_estimate NUMERIC,
            high_estimate NUMERIC,
            number_of_analysts INTEGER,
            year_ago_revenue NUMERIC,
            growth NUMERIC,
            fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, period)
        );
    """
    )


def load_revenue_data(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading revenue estimates for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx * CHUNK_SIZE : (batch_idx + 1) * CHUNK_SIZE]
        yq_batch = [s.replace(".", "-").replace("$", "-").upper() for s in batch]
        mapping = dict(zip(yq_batch, batch))

        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")

        for yq_sym, orig_sym in mapping.items():
            for attempt in range(1, MAX_BATCH_RETRIES + 1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    revenue_est = ticker.revenue_estimate
                    if revenue_est is None or revenue_est.empty:
                        raise ValueError("No revenue estimate data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        continue
                    time.sleep(RETRY_DELAY)

            try:
                if revenue_est is not None and not revenue_est.empty:
                    revenue_data = []
                    for period, row in revenue_est.iterrows():
                        # Use safe_float for NUMERIC columns (handles large values better)
                        # Convert period to string to avoid numpy type issues
                        revenue_data.append(
                            (
                                orig_sym,
                                str(period),  # Convert period to string (was numpy type from pandas index)
                                safe_float(row.get("avg")),
                                safe_float(row.get("low")),
                                safe_float(row.get("high")),
                                safe_int(row.get("numberOfAnalysts")),
                                safe_float(row.get("yearAgoRevenue")),
                                safe_float(row.get("growth")),
                            )
                        )

                    if revenue_data:
                        execute_values(
                            cur,
                            """
                            INSERT INTO revenue_estimates (
                                symbol, period, avg_estimate, low_estimate,
                                high_estimate, number_of_analysts,
                                year_ago_revenue, growth
                            ) VALUES %s
                            ON CONFLICT (symbol, period) DO UPDATE SET
                                avg_estimate = EXCLUDED.avg_estimate,
                                low_estimate = EXCLUDED.low_estimate,
                                high_estimate = EXCLUDED.high_estimate,
                                number_of_analysts = EXCLUDED.number_of_analysts,
                                year_ago_revenue = EXCLUDED.year_ago_revenue,
                                growth = EXCLUDED.growth,
                                fetched_at = CURRENT_TIMESTAMP
                        """,
                            revenue_data,
                        )
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
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    create_tables(cur)
    conn.commit()

    cur.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y');")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t, p, f = load_revenue_data(stock_syms, cur, conn)

    cur.execute(
        """
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """,
        (SCRIPT_NAME,),
    )
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Revenue Estimates — total: {t}, processed: {p}, failed: {len(f)}")

    cur.close()
    conn.close()
    logging.info("All done.")
    return {"total": t, "processed": p, "failed": f, "peak_rss_mb": peak}


if __name__ == "__main__":
    lambda_handler(None, None)
# Trigger deployment: revenueestimate and sectordata loaders
