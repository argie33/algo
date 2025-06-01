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

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadearnings.py"
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
    logging.info("Recreating earnings tables...")
    
    # Drop tables in reverse dependency order
    cur.execute("""
        DROP TABLE IF EXISTS eps_trend CASCADE;
        DROP TABLE IF EXISTS eps_revisions CASCADE;
        DROP TABLE IF EXISTS earnings_history CASCADE;
        DROP TABLE IF EXISTS revenue_estimates CASCADE;
        DROP TABLE IF EXISTS earnings_estimates CASCADE;
    """)

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

    # Create revenue_estimates table
    cur.execute("""
        CREATE TABLE revenue_estimates (
            symbol VARCHAR(20) NOT NULL,
            period VARCHAR(3) NOT NULL,
            avg_estimate BIGINT,
            low_estimate BIGINT,
            high_estimate BIGINT,
            number_of_analysts INTEGER,
            year_ago_revenue BIGINT,
            growth NUMERIC,
            fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, period)
        );
    """)

    # Create earnings_history table
    cur.execute("""
        CREATE TABLE earnings_history (
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

    # Create eps_revisions table
    cur.execute("""
        CREATE TABLE eps_revisions (
            symbol VARCHAR(20) NOT NULL,
            period VARCHAR(3) NOT NULL,
            up_last_7_days INTEGER,
            up_last_30_days INTEGER,
            down_last_30_days INTEGER,
            down_last_7_days INTEGER,
            fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, period)
        );
    """)

    # Create eps_trend table
    cur.execute("""
        CREATE TABLE eps_trend (
            symbol VARCHAR(20) NOT NULL,
            period VARCHAR(3) NOT NULL,
            current NUMERIC,
            days_7_ago NUMERIC,
            days_30_ago NUMERIC,
            days_60_ago NUMERIC,
            days_90_ago NUMERIC,
            fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, period)
        );
    """)

def load_earnings_data(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading earnings data for {total} symbols")
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
                    
                    # Get all earnings data
                    earnings_est = ticker.earnings_estimate
                    revenue_est = ticker.revenue_estimate
                    earnings_hist = ticker.earnings_history
                    eps_rev = ticker.eps_revisions
                    eps_tr = ticker.eps_trend
                    
                    if all(x is None for x in [earnings_est, revenue_est, earnings_hist, eps_rev, eps_tr]):
                        raise ValueError("No earnings data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        continue
                    time.sleep(RETRY_DELAY)

            try:
                # Insert earnings estimates
                if earnings_est is not None and not earnings_est.empty:
                    earnings_data = []
                    for period, row in earnings_est.iterrows():
                        earnings_data.append((
                            orig_sym, period,
                            row.get('avg'), row.get('low'), row.get('high'),
                            row.get('yearAgoEps'), row.get('numberOfAnalysts'),
                            row.get('growth')
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

                # Insert revenue estimates
                if revenue_est is not None and not revenue_est.empty:
                    revenue_data = []
                    for period, row in revenue_est.iterrows():
                        revenue_data.append((
                            orig_sym, period,
                            row.get('avg'), row.get('low'), row.get('high'),
                            row.get('numberOfAnalysts'),
                            row.get('yearAgoRevenue'), row.get('growth')
                        ))
                    
                    if revenue_data:
                        execute_values(cur, """
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
                        """, revenue_data)

                # Insert earnings history
                if earnings_hist is not None and not earnings_hist.empty:
                    history_data = []
                    for quarter, row in earnings_hist.iterrows():
                        history_data.append((
                            orig_sym, quarter,
                            row.get('epsActual'), row.get('epsEstimate'),
                            row.get('epsDifference'), row.get('surprisePercent')
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

                # Insert EPS revisions
                if eps_rev is not None and not eps_rev.empty:
                    revision_data = []
                    for period, row in eps_rev.iterrows():
                        revision_data.append((
                            orig_sym, period,
                            row.get('upLast7days'), row.get('upLast30days'),
                            row.get('downLast30days'), row.get('downLast7Days')
                        ))
                    
                    if revision_data:
                        execute_values(cur, """
                            INSERT INTO eps_revisions (
                                symbol, period, up_last_7_days, up_last_30_days,
                                down_last_30_days, down_last_7_days
                            ) VALUES %s
                            ON CONFLICT (symbol, period) DO UPDATE SET
                                up_last_7_days = EXCLUDED.up_last_7_days,
                                up_last_30_days = EXCLUDED.up_last_30_days,
                                down_last_30_days = EXCLUDED.down_last_30_days,
                                down_last_7_days = EXCLUDED.down_last_7_days,
                                fetched_at = CURRENT_TIMESTAMP
                        """, revision_data)

                # Insert EPS trend
                if eps_tr is not None and not eps_tr.empty:
                    trend_data = []
                    for period, row in eps_tr.iterrows():
                        trend_data.append((
                            orig_sym, period,
                            row.get('current'), row.get('7daysAgo'),
                            row.get('30daysAgo'), row.get('60daysAgo'),
                            row.get('90daysAgo')
                        ))
                    
                    if trend_data:
                        execute_values(cur, """
                            INSERT INTO eps_trend (
                                symbol, period, current, days_7_ago,
                                days_30_ago, days_60_ago, days_90_ago
                            ) VALUES %s
                            ON CONFLICT (symbol, period) DO UPDATE SET
                                current = EXCLUDED.current,
                                days_7_ago = EXCLUDED.days_7_ago,
                                days_30_ago = EXCLUDED.days_30_ago,
                                days_60_ago = EXCLUDED.days_60_ago,
                                days_90_ago = EXCLUDED.days_90_ago,
                                fetched_at = CURRENT_TIMESTAMP
                        """, trend_data)

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
        dbname=cfg["dbname"]
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
    logging.info(f"Earnings Data — total: {t}, processed: {p}, failed: {len(f)}")

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