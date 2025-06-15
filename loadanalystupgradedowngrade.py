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
                    recommendations_df = ticker.recommendations
                    if recommendations_df is None or recommendations_df.empty:
                        logging.info(f"No analyst upgrades/downgrades for {orig_sym}")
                        break  # No data available, not an error
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        break  # Break instead of continue to skip processing
                    time.sleep(RETRY_DELAY)
            
            # Skip processing if recommendations were not successfully retrieved
            if recommendations_df is None:
                logging.error(f"Skipping {orig_sym} - failed to retrieve recommendations after {MAX_BATCH_RETRIES} attempts")
                continue
                
            # Skip if no data
            if recommendations_df.empty:
                continue
            
            try:
                # Check available columns and filter data
                grade_columns = []
                if "To Grade" in recommendations_df.columns:
                    grade_columns.append("To Grade")
                elif "toGrade" in recommendations_df.columns:
                    grade_columns.append("toGrade")
                elif "To" in recommendations_df.columns:
                    grade_columns.append("To")
                    
                if "From Grade" in recommendations_df.columns:
                    grade_columns.append("From Grade")
                elif "fromGrade" in recommendations_df.columns:
                    grade_columns.append("fromGrade")
                elif "From" in recommendations_df.columns:
                    grade_columns.append("From")
                
                # If no grade columns found, use all recommendations
                if not grade_columns:
                    logging.warning(f"No grade columns found for {orig_sym}, returning all recommendations")
                    df_filtered = recommendations_df
                else:
                    # Filter for rows that have grade information
                    condition = pd.Series([False] * len(recommendations_df))
                    for col in grade_columns:
                        if col in recommendations_df.columns:
                            condition = condition | recommendations_df[col].notna()
                    df_filtered = recommendations_df[condition] if condition.any() else recommendations_df

                # Process each recommendation
                rows_to_insert = []
                for dt, row in df_filtered.iterrows():
                    # Handle flexible column names for grades
                    from_grade = (row.get("From Grade") or 
                                 row.get("fromGrade") or 
                                 row.get("From") or 
                                 None)
                    to_grade = (row.get("To Grade") or 
                               row.get("toGrade") or 
                               row.get("To") or 
                               None)
                    
                    # Handle date conversion properly
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
                        row.get("Action"),
                        from_grade,
                        to_grade,
                        date_value,
                        row.get("Details") if "Details" in row else None
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
