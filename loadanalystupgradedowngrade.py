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
    
    # Debug: Log available columns for first symbol
    if symbol == "AAL":  # Log columns for debugging
        logging.info(f"Available columns for {symbol}: {list(df.columns)}")
    
    # Check if the expected columns exist, if not try alternatives
    grade_columns = []
    if "To Grade" in df.columns:
        grade_columns.append("To Grade")
    elif "toGrade" in df.columns:
        grade_columns.append("toGrade")
    elif "To" in df.columns:
        grade_columns.append("To")
        
    if "From Grade" in df.columns:
        grade_columns.append("From Grade")
    elif "fromGrade" in df.columns:
        grade_columns.append("fromGrade")
    elif "From" in df.columns:
        grade_columns.append("From")
    
    # If no grade columns found, return all recommendations
    if not grade_columns:
        logging.warning(f"No grade columns found for {symbol}, returning all recommendations")
        return df
    
    # Filter for rows that have grade information
    condition = pd.Series([False] * len(df))
    for col in grade_columns:
        if col in df.columns:
            condition = condition | df[col].notna()
    
    df_filtered = df[condition] if condition.any() else df
    return df_filtered

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
            # Handle flexible column names
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
                date_value = None  # Default to NULL instead of invalid value
            
            rows.append([
                symbol,
                row.get("Firm"),
                row.get("Action"),
                from_grade,
                to_grade,
                date_value,
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

# Test function to debug column names (remove after testing)
def test_recommendation_columns():
    """Test function to see what columns are available in recommendations data"""
    try:
        import yfinance as yf
        ticker = yf.Ticker("AAPL")
        df = ticker.recommendations
        if df is not None and not df.empty:
            print(f"Available columns: {list(df.columns)}")
            print(f"Sample data:")
            print(df.head())
        else:
            print("No recommendations data available")
    except Exception as e:
        print(f"Error: {e}")

# Uncomment to test: test_recommendation_columns()

if __name__ == "__main__":
    # Run the same logic as lambda_handler when executed directly
    lambda_handler(None, None)
