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
import pandas as pd
from urllib.error import HTTPError

import boto3
import yfinance as yf

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadanalystupgradedowngrade.py"
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

def load_analyst_actions(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading analyst upgrades/downgrades for {total} symbols")
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
            recommendations_df = None  # Initialize recommendations variable
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    # Use upgrades_downgrades instead of recommendations
                    recommendations_df = ticker.upgrades_downgrades
                    if recommendations_df is None or recommendations_df.empty:
                        logging.info(f"No analyst upgrades/downgrades for {orig_sym}")
                        break  # No data available, not an error
                    break
                except HTTPError as e:
                    if e.code == 404:
                        logging.info(f"No analyst upgrades/downgrades for {orig_sym} (404)")
                        break  # No data available for this symbol, not a retry-able error
                    else:
                        logging.warning(f"HTTP Error {e.code} for {orig_sym} (attempt {attempt}): {e}")
                        if attempt == MAX_BATCH_RETRIES:
                            failed.append(orig_sym)
                            break
                        time.sleep(RETRY_DELAY)
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        break  # Break instead of continue to skip processing
                    time.sleep(RETRY_DELAY)
            
            # Skip processing if recommendations were not successfully retrieved
            if recommendations_df is None:
                continue
                
            # Skip if no data
            if recommendations_df.empty:
                continue
            
            try:
                # upgrades_downgrades has columns: Firm, ToGrade, FromGrade, Action, priceTargetAction, currentPriceTarget
                # The date is in the index as 'GradeDate'
                
                # Process each recommendation
                rows_to_insert = []
                for dt, row in recommendations_df.iterrows():
                    # Handle date from index (GradeDate)
                    if hasattr(dt, 'date'):
                        date_value = dt.date()
                    elif hasattr(dt, 'to_pydatetime'):
                        date_value = dt.to_pydatetime().date()
                    elif isinstance(dt, str):
                        try:
                            date_value = pd.to_datetime(dt).date()
                        except:
                            date_value = None
                    else:
                        date_value = None
                      # Skip rows with invalid/missing dates since the column is NOT NULL
                    if date_value is None:
                        logging.warning(f"Skipping {orig_sym} row due to invalid/missing date")
                        continue
                    
                    rows_to_insert.append((
                        orig_sym,
                        row.get("Firm"),
                        row.get("priceTargetAction"),  # Use priceTargetAction instead of Action
                        row.get("FromGrade"),
                        row.get("ToGrade"),
                        date_value,
                        None  # No details column in upgrades_downgrades
                    ))
                
                # Insert data if we have valid rows
                if rows_to_insert:
                    execute_values(cur, """
                        INSERT INTO analyst_upgrade_downgrade
                        (symbol, firm, action, from_grade, to_grade, date, details)
                        VALUES %s
                    """, rows_to_insert)
                    conn.commit()
                    logging.info(f"{orig_sym}: inserted {len(rows_to_insert)} recommendations")
                
                processed += 1
                
            except Exception as e:
                logging.error(f"Failed to insert for {orig_sym}: {e}")
                conn.rollback()
                failed.append(orig_sym)
        
        # Cleanup and pause between batches
        gc.collect()
        time.sleep(PAUSE)
        log_mem(f"Batch {batch_idx+1} complete")
    
    return total, processed, failed

def create_all_tables(cur):
    """Create all required tables for analyst upgrade/downgrade data"""
    logging.info("Creating analyst_upgrade_downgrade table...")
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
            fetched_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT analyst_upgrade_downgrade_symbol_date_key
                UNIQUE (symbol, firm, date, action)
        );
    """)
    
    # Create indexes for performance
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_analyst_upgrade_downgrade_symbol 
        ON analyst_upgrade_downgrade (symbol);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_analyst_upgrade_downgrade_date 
        ON analyst_upgrade_downgrade (date);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_analyst_upgrade_downgrade_firm 
        ON analyst_upgrade_downgrade (firm);
    """)

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

    create_all_tables(cur)
    conn.commit()

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_analyst_actions(stock_syms, cur, conn)

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
    logging.info(f"Analyst Actions — total: {t_s}, processed: {p_s}, failed: {len(f_s)}")

    cur.close()
    conn.close()
    logging.info("All done.")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "total": t_s,
            "processed": p_s,
            "failed": len(f_s),
            "failed_symbols": f_s,
            "peak_rss_mb": peak
        })
    }

if __name__ == "__main__":
    lambda_handler({}, {})
