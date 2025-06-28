#!/usr/bin/env python3
import sys
import time
import logging
from datetime import datetime, timedelta
import json
import os
import concurrent.futures
from functools import partial
import gc

import numpy as np
import numpy

# ───────────────────────────────────────────────────────────────────
# Monkey-patch numpy so that "from numpy import NaN" in pandas_ta will succeed 
numpy.NaN = numpy.nan
np.NaN    = np.nan
# ───────────────────────────────────────────────────────────────────

import boto3
import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values

import pandas as pd
import yfinance as yf

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = os.path.basename(__file__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
    stream=sys.stdout
)

# Configure these based on your ECS task size
MAX_WORKERS = min(os.cpu_count() or 1, 4)  # Limit to available CPUs or 4, whichever is smaller
BATCH_SIZE = 100  # Number of symbols to process in each batch
DB_POOL_MIN = 2
DB_POOL_MAX = 10

def get_db_config():
    """
    Fetch host, port, dbname, username & password from Secrets Manager.
    SecretString must be JSON with keys: username, password, host, port, dbname.
    """
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"]
    )

def sanitize_value(x):
    if isinstance(x, float) and np.isnan(x):
        return None
    return x

def calculate_eps_growth(eps_series, quarters):
    """Calculate EPS growth over specified number of quarters"""
    if len(eps_series) < quarters + 1:
        return None
    
    current = eps_series.iloc[-1]
    past = eps_series.iloc[-quarters-1]
    
    if past == 0 or np.isnan(past) or np.isnan(current):
        return None
    
    return ((current - past) / abs(past)) * 100

def calculate_eps_acceleration(eps_series):
    """Calculate EPS acceleration (change in growth rate)"""
    if len(eps_series) < 4:
        return None
    
    # Calculate growth rates for last 2 quarters
    growth_1q = calculate_eps_growth(eps_series, 1)
    growth_2q = calculate_eps_growth(eps_series, 2)
    
    if growth_1q is None or growth_2q is None:
        return None
    
    return growth_1q - growth_2q

def calculate_annual_eps_growth(eps_series, years):
    """Calculate annual EPS growth over specified years"""
    quarters = years * 4
    if len(eps_series) < quarters + 1:
        return None
    
    current_annual = eps_series.iloc[-4:].sum() if len(eps_series) >= 4 else eps_series.iloc[-1] * 4
    past_annual = eps_series.iloc[-quarters-4:-quarters].sum() if len(eps_series) >= quarters + 4 else eps_series.iloc[-quarters-1] * 4
    
    if past_annual == 0 or np.isnan(past_annual) or np.isnan(current_annual):
        return None
    
    return ((current_annual - past_annual) / abs(past_annual)) * 100

def calculate_consecutive_eps_growth_years(eps_series):
    """Calculate consecutive years of EPS growth"""
    if len(eps_series) < 8:  # Need at least 2 years of data
        return 0
    
    years = 0
    for i in range(4, len(eps_series), 4):
        if i + 4 <= len(eps_series):
            current_annual = eps_series.iloc[i:i+4].sum()
            past_annual = eps_series.iloc[i-4:i].sum()
            
            if past_annual > 0 and current_annual > past_annual:
                years += 1
            else:
                break
    
    return years

def calculate_estimate_revisions(symbol, months):
    """Calculate EPS estimate revisions over specified months"""
    try:
        # Get analyst estimates from yfinance
        ticker = yf.Ticker(symbol)
        earnings_dates = ticker.earnings_dates
        
        if earnings_dates is None or earnings_dates.empty:
            return None
        
        # Get current and historical estimates
        current_date = datetime.now()
        past_date = current_date - timedelta(days=months*30)
        
        # Filter for recent estimates
        recent_estimates = earnings_dates[
            (earnings_dates.index >= past_date) & 
            (earnings_dates.index <= current_date)
        ]
        
        if len(recent_estimates) < 2:
            return None
        
        # Calculate revision percentage
        latest_estimate = recent_estimates['EPS Estimate'].iloc[-1]
        earliest_estimate = recent_estimates['EPS Estimate'].iloc[0]
        
        if earliest_estimate == 0 or np.isnan(earliest_estimate) or np.isnan(latest_estimate):
            return None
        
        return ((latest_estimate - earliest_estimate) / abs(earliest_estimate)) * 100
        
    except Exception as e:
        logging.warning(f"Failed to calculate estimate revisions for {symbol}: {e}")
        return None

def get_earnings_surprise(symbol):
    """Get the most recent earnings surprise percentage"""
    try:
        ticker = yf.Ticker(symbol)
        earnings_dates = ticker.earnings_dates
        
        if earnings_dates is None or earnings_dates.empty:
            return None
        
        # Get the most recent earnings
        latest_earnings = earnings_dates.iloc[0]  # Most recent is first
        
        if 'Surprise %' in latest_earnings and not np.isnan(latest_earnings['Surprise %']):
            return latest_earnings['Surprise %']
        
        return None
        
    except Exception as e:
        logging.warning(f"Failed to get earnings surprise for {symbol}: {e}")
        return None

def prepare_db():
    """Set up the database tables"""
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=pwd, dbname=db
    )
    conn.autocommit = True
    cursor = conn.cursor()
    logging.info("Connected to PostgreSQL database.")

    # Create last_updated table if it doesn't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS last_updated (
        script_name VARCHAR(255) PRIMARY KEY,
        last_run    TIMESTAMP
    );
    """)

    # Drop and recreate earnings_metrics table
    logging.info("Recreating earnings_metrics table...")
    cursor.execute("DROP TABLE IF EXISTS earnings_metrics;")
    cursor.execute("""
    CREATE TABLE earnings_metrics (
        symbol                      VARCHAR(50),
        report_date                 DATE,
        eps_growth_1q               DOUBLE PRECISION,
        eps_growth_2q               DOUBLE PRECISION,
        eps_growth_4q               DOUBLE PRECISION,
        eps_growth_8q               DOUBLE PRECISION,
        eps_acceleration_qtrs       DOUBLE PRECISION,
        eps_surprise_last_q         DOUBLE PRECISION,
        eps_estimate_revision_1m    DOUBLE PRECISION,
        eps_estimate_revision_3m    DOUBLE PRECISION,
        eps_estimate_revision_6m    DOUBLE PRECISION,
        annual_eps_growth_1y        DOUBLE PRECISION,
        annual_eps_growth_3y        DOUBLE PRECISION,
        annual_eps_growth_5y        DOUBLE PRECISION,
        consecutive_eps_growth_years INTEGER,
        eps_estimated_change_this_year DOUBLE PRECISION,
        fetched_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, report_date)
    );
    """)
    logging.info("Table 'earnings_metrics' ready.")
    
    cursor.execute("SELECT symbol FROM stock_symbols;")
    symbols = [r[0] for r in cursor.fetchall()]
    logging.info(f"Found {len(symbols)} symbols.")
    
    cursor.close()
    conn.close()
    
    return symbols

def create_connection_pool():
    """Create a connection pool for better database performance"""
    user, pwd, host, port, db = get_db_config()
    return pool.ThreadedConnectionPool(
        DB_POOL_MIN, DB_POOL_MAX,
        host=host, port=port, user=user, password=pwd, dbname=db
    )

def process_symbol(symbol, conn_pool):
    """Process a single symbol and return the number of rows inserted"""
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()
        
        logging.info(f"Processing earnings metrics for {symbol}...")
        
        # Get earnings data from yfinance
        ticker = yf.Ticker(symbol)
        earnings = ticker.earnings
        
        if earnings is None or earnings.empty:
            logging.warning(f"No earnings data for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0
        
        # Get quarterly earnings data
        quarterly_earnings = ticker.quarterly_earnings
        
        if quarterly_earnings is None or quarterly_earnings.empty:
            logging.warning(f"No quarterly earnings data for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0
        
        # Sort by date (most recent first)
        quarterly_earnings = quarterly_earnings.sort_index()
        
        # Calculate metrics for each quarter
        data = []
        for i, (date, row) in enumerate(quarterly_earnings.iterrows()):
            if i >= 20:  # Limit to last 20 quarters for performance
                break
            
            # Get EPS series up to this point
            eps_series = quarterly_earnings['Earnings'].iloc[:i+1]
            
            # Calculate various metrics
            eps_growth_1q = calculate_eps_growth(eps_series, 1)
            eps_growth_2q = calculate_eps_growth(eps_series, 2)
            eps_growth_4q = calculate_eps_growth(eps_series, 4)
            eps_growth_8q = calculate_eps_growth(eps_series, 8)
            eps_acceleration_qtrs = calculate_eps_acceleration(eps_series)
            eps_surprise_last_q = get_earnings_surprise(symbol)
            eps_estimate_revision_1m = calculate_estimate_revisions(symbol, 1)
            eps_estimate_revision_3m = calculate_estimate_revisions(symbol, 3)
            eps_estimate_revision_6m = calculate_estimate_revisions(symbol, 6)
            annual_eps_growth_1y = calculate_annual_eps_growth(eps_series, 1)
            annual_eps_growth_3y = calculate_annual_eps_growth(eps_series, 3)
            annual_eps_growth_5y = calculate_annual_eps_growth(eps_series, 5)
            consecutive_eps_growth_years = calculate_consecutive_eps_growth_years(eps_series)
            
            # Calculate estimated change this year (current year vs previous year)
            try:
                current_year_eps = earnings.iloc[0]['Earnings'] if not earnings.empty else None
                previous_year_eps = earnings.iloc[1]['Earnings'] if len(earnings) > 1 else None
                
                if current_year_eps and previous_year_eps and previous_year_eps != 0:
                    eps_estimated_change_this_year = ((current_year_eps - previous_year_eps) / abs(previous_year_eps)) * 100
                else:
                    eps_estimated_change_this_year = None
            except:
                eps_estimated_change_this_year = None
            
            data.append((
                symbol,
                date.date(),
                sanitize_value(eps_growth_1q),
                sanitize_value(eps_growth_2q),
                sanitize_value(eps_growth_4q),
                sanitize_value(eps_growth_8q),
                sanitize_value(eps_acceleration_qtrs),
                sanitize_value(eps_surprise_last_q),
                sanitize_value(eps_estimate_revision_1m),
                sanitize_value(eps_estimate_revision_3m),
                sanitize_value(eps_estimate_revision_6m),
                sanitize_value(annual_eps_growth_1y),
                sanitize_value(annual_eps_growth_3y),
                sanitize_value(annual_eps_growth_5y),
                consecutive_eps_growth_years if consecutive_eps_growth_years is not None else None,
                sanitize_value(eps_estimated_change_this_year),
                datetime.now()
            ))
        
        # Insert data
        if data:
            insert_q = """
            INSERT INTO earnings_metrics (
                symbol, report_date, eps_growth_1q, eps_growth_2q, eps_growth_4q, eps_growth_8q,
                eps_acceleration_qtrs, eps_surprise_last_q, eps_estimate_revision_1m,
                eps_estimate_revision_3m, eps_estimate_revision_6m, annual_eps_growth_1y,
                annual_eps_growth_3y, annual_eps_growth_5y, consecutive_eps_growth_years,
                eps_estimated_change_this_year, fetched_at
            ) VALUES %s;
            """
            
            execute_values(cursor, insert_q, data)
            conn.commit()
            num_inserted = len(data)
            logging.info(f"✅ {symbol}: Inserted {num_inserted} rows")
        else:
            num_inserted = 0
            logging.warning(f"⚠️ {symbol}: No data to insert")
        
        cursor.close()
        conn_pool.putconn(conn)
        
        # Free memory
        del ticker, earnings, quarterly_earnings, data
        gc.collect()
        
        return num_inserted
        
    except Exception as e:
        logging.error(f"❌ {symbol}: Failed - {str(e)}")
        if 'conn' in locals() and conn:
            conn_pool.putconn(conn)
        return 0

def process_symbol_batch(symbols):
    """Process a batch of symbols and return the total rows inserted"""
    # Create a connection pool within this process
    conn_pool = create_connection_pool()
    
    total_inserted = 0
    success_count = 0
    failed_count = 0
    
    try:
        for symbol in symbols:
            try:
                inserted = process_symbol(symbol, conn_pool)
                total_inserted += inserted
                if inserted > 0:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logging.error(f"❌ Batch error for {symbol}: {str(e)}")
                failed_count += 1
    finally:
        # Make sure to close all connections in this pool
        conn_pool.closeall()
    
    return total_inserted, success_count, failed_count

def main():
    logging.info(f"Starting {SCRIPT_NAME}")
    try:
        # Prepare database and get symbols
        symbols = prepare_db()
        
        start = time.time()
        total_inserted = 0
        symbols_processed = 0
        symbols_failed = 0
        
        # Process symbols in parallel using worker pool
        with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Split symbols into batches
            symbol_batches = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
            # Process each batch with a worker
            futures = []
            for batch in symbol_batches:
                future = executor.submit(process_symbol_batch, batch)
                futures.append(future)
            # Collect results
            for future in concurrent.futures.as_completed(futures):
                batch_inserted, batch_success, batch_failed = future.result()
                total_inserted += batch_inserted
                symbols_processed += batch_success
                symbols_failed += batch_failed

        elapsed = time.time() - start
        logging.info(f"Summary: Processed {symbols_processed + symbols_failed} symbols in {elapsed:.2f} seconds")
        logging.info(f"Success: {symbols_processed} symbols ({total_inserted} rows inserted)")
        if symbols_failed > 0:
            logging.warning(f"Failed: {symbols_failed} symbols")
        else:
            logging.info("✨ All symbols processed successfully")

        # Update last_run timestamp
        main_conn_pool = create_connection_pool()
        conn = main_conn_pool.getconn()
        cursor = conn.cursor()
        now = datetime.now()
        cursor.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, %s)
        ON CONFLICT (script_name) DO UPDATE
          SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME, now))
        conn.commit()
        cursor.close()
        main_conn_pool.putconn(conn)
        # Close the connection pool
        main_conn_pool.closeall()
    
    except Exception as e:
        logging.exception(f"Unhandled error in script: {e}")
        sys.exit(1)
    finally:
        logging.info("Done.")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Unhandled error in script")
        sys.exit(1) 