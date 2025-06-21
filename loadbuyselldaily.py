#!/usr/bin/env python3
"""
Optimized Buy/Sell Signal Generator
- Ultra-fast vectorized operations with NumPy/Pandas
- Parallel processing with ThreadPoolExecutor
- Memory-optimized data types and aggressive garbage collection
- Database optimizations with psutil monitoring
"""

import sys
import time
import logging
import json
import os
import gc
import resource
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
import warnings
warnings.filterwarnings('ignore')

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import requests
import pandas as pd
import numpy as np
import psutil

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadbuyselldaily.py"
TIMEFRAME = "daily"
PRICE_TABLE = "price_daily"
TECH_TABLE = "technical_data_daily"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Performance monitoring
# -------------------------------
def retry_with_timeout_reduction(func, *args, max_retries=3, **kwargs):
    """Retry wrapper with progressive timeout reduction for database operations"""
    for retry_count in range(max_retries):
        try:
            if 'retry_count' in func.__code__.co_varnames:
                return func(*args, retry_count=retry_count, **kwargs)
            else:
                return func(*args, **kwargs)
        except psycopg2.OperationalError as e:
            error_msg = str(e).lower()
            if 'canceling statement due to statement timeout' in error_msg:
                if retry_count < max_retries - 1:
                    timeout_val = max(300, 900 - (retry_count * 200))
                    next_timeout = max(300, 900 - ((retry_count + 1) * 200))
                    logging.warning(f"Database timeout after {timeout_val}s, retrying with {next_timeout}s timeout (attempt {retry_count + 2}/{max_retries})")
                    time.sleep(2)  # Brief pause before retry
                    continue
                else:
                    logging.error(f"Database timeout after {max_retries} attempts, skipping batch")
                    raise
            else:
                # Non-timeout operational error, don't retry
                logging.error(f"Database operational error: {e}")
                raise
        except Exception as e:
            # Non-database errors, don't retry
            logging.error(f"Non-database error: {e}")
            raise
    
    # If all retries exhausted
    raise Exception(f"All {max_retries} retry attempts failed")

def get_rss_mb():
    """Get RSS memory in MB"""
    return psutil.Process().memory_info().rss / 1024 / 1024

def get_cpu_percent():
    """Get current CPU usage"""
    return psutil.cpu_percent(interval=0.1)

def log_performance(stage: str):
    """Log memory and CPU usage"""
    rss = get_rss_mb()
    cpu = get_cpu_percent()
    logging.info(f"[PERF] {stage}: {rss:.1f} MB RSS, {cpu:.1f}% CPU")

def optimize_dataframe(df):
    """Optimize DataFrame memory usage with proper data types"""
    if df.empty:
        return df
    
    # Optimize numeric columns
    for col in df.select_dtypes(include=[np.number]).columns:
        if df[col].dtype == 'float64':
            df[col] = pd.to_numeric(df[col], downcast='float')
        elif df[col].dtype == 'int64':
            df[col] = pd.to_numeric(df[col], downcast='integer')
    
    # Optimize object columns
    for col in df.select_dtypes(include=['object']).columns:
        if col != 'date':  # Don't touch date columns
            df[col] = df[col].astype('category')
    
    return df

# -------------------------------
# Database configuration with connection pooling
# -------------------------------
def get_db_config():
    """Get database configuration from AWS Secrets Manager"""
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

def get_optimized_connection(retry_count=0):
    """Get database connection with performance optimizations and dynamic timeouts"""
    cfg = get_db_config()
    
    # Progressive connection timeout: 60s initially, increase by 30s per retry
    connection_timeout = 60 + (retry_count * 30)
    
    try:
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"],
            # Extended timeout for connection establishment
            connect_timeout=connection_timeout,
            application_name=f"{SCRIPT_NAME}_daily",
            # Additional connection parameters for reliability
            keepalives_idle=600,
            keepalives_interval=30,
            keepalives_count=3
        )
    except psycopg2.OperationalError as e:
        if "timeout expired" in str(e) and retry_count < 2:
            logging.warning(f"Connection timeout (attempt {retry_count + 1}), retrying with longer timeout...")
            time.sleep(10 * (retry_count + 1))  # Exponential backoff
            return get_optimized_connection(retry_count + 1)
        else:
            logging.error(f"Failed to connect to database after {retry_count + 1} attempts: {e}")
            raise
    
    # Set performance parameters with dynamic timeout based on retry count
    with conn.cursor() as cur:
        cur.execute("SET work_mem = '256MB'")
        # cur.execute("SET shared_buffers = '1GB'")  # Cannot be changed at runtime
        cur.execute("SET effective_cache_size = '4GB'")
        cur.execute("SET random_page_cost = 1.1")
        
        # Dynamic timeout: 900s initially, reduced by 200s per retry (900s -> 700s -> 500s)
        timeout_seconds = max(300, 900 - (retry_count * 200))
        cur.execute(f"SET statement_timeout = '{timeout_seconds}s'")
        cur.execute("SET lock_timeout = '60s'")
    
    conn.commit()
    logging.info(f"✅ Database connection established (timeout: {connection_timeout}s, statement_timeout: {timeout_seconds}s)")
    return conn

# -------------------------------
# FRED API Key
# -------------------------------
FRED_API_KEY = os.environ["FRED_API_KEY"]

###############################################################################
# 1) DATABASE FUNCTIONS (Ultra-optimized)
###############################################################################
def get_symbols_batch(batch_size=1000):
    """Get symbols in batches for memory efficiency"""
    conn = get_optimized_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol 
                FROM stock_symbols 
                WHERE exchange IN ('NASDAQ','New York Stock Exchange')
                ORDER BY symbol
            """)
            
            symbols = []
            while True:
                batch = cur.fetchmany(batch_size)
                if not batch:
                    break
                symbols.extend([row[0] for row in batch])
            
            return symbols
    finally:
        conn.close()

def create_buy_sell_table_optimized(cur):
    """Create optimized buy_sell_daily table with proper indexing"""
    table_name = f"buy_sell_{TIMEFRAME}"
    sequence_name = f"{table_name}_id_seq"
    
    # Explicitly drop sequence and table to avoid conflicts
    cur.execute(f"DROP SEQUENCE IF EXISTS {sequence_name} CASCADE;")
    cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")
    cur.connection.commit()  # Commit the drops immediately
    
    # Create new table
    cur.execute(f"""
        CREATE TABLE {table_name} (
            id           SERIAL PRIMARY KEY,
            symbol       VARCHAR(20)    NOT NULL,
            timeframe    VARCHAR(10)    NOT NULL, 
            date         DATE           NOT NULL,
            signal       VARCHAR(10),
            buylevel     REAL,
            stoplevel    REAL,            inposition   BOOLEAN,
            UNIQUE(symbol, timeframe, date)
        );
    """)
    cur.connection.commit()
      # Create optimized indexes 
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_symbol_tf_date ON {table_name}(symbol, timeframe, date);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_signal ON {table_name}(signal) WHERE signal IS NOT NULL;")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_timeframe ON {table_name}(timeframe);")
    cur.connection.commit()
    
    logging.info(f"✅ {table_name} table and indexes created successfully")

def bulk_insert_results(cur, symbol_results):
    """Ultra-fast bulk insert using execute_values"""
    if not symbol_results:
        print("DEBUG: No symbol results to insert")
        return 0
    
    print(f"DEBUG: Processing {len(symbol_results)} symbol results for insertion")
    
    # Prepare data for bulk insert
    insert_data = []
    for symbol, timeframe, df in symbol_results:
        if df.empty:
            print(f"DEBUG: Empty DataFrame for {symbol}")
            continue
            
        print(f"DEBUG: Processing {symbol} with {len(df)} rows")
        signal_rows = 0
        for _, row in df.iterrows():
            # Skip rows with NaN values
            vals = [row.get('Signal'), row.get('buyLevel'), 
                   row.get('stopLevel'), row.get('inPosition')]
            if any(pd.isnull(v) for v in vals):
                continue
            
            signal_rows += 1
            insert_data.append((
                symbol,
                timeframe,
                row['date'].date(),
                row['Signal'],
                float(row['buyLevel']) if not pd.isnull(row['buyLevel']) else None,
                float(row['stopLevel']) if not pd.isnull(row['stopLevel']) else None,
                bool(row['inPosition'])            ))
        
        print(f"DEBUG: {symbol} has {signal_rows} valid signal rows out of {len(df)} total rows")
    
    if not insert_data:
        print("DEBUG: No valid insert data after processing all symbols")
        return 0
    
    print(f"DEBUG: Attempting to insert {len(insert_data)} rows into database")
    
    # Bulk insert with ON CONFLICT handling
    table_name = f"buy_sell_{TIMEFRAME}"
    insert_query = f"""
        INSERT INTO {table_name} (
            symbol, timeframe, date, signal, buylevel, stoplevel, inposition
        ) VALUES %s
        ON CONFLICT (symbol, timeframe, date) DO NOTHING
    """
    
    execute_values(
        cur, insert_query, insert_data,
        template=None,
        page_size=1000,
        fetch=False
    )
    
    return len(insert_data)

###############################################################################
# 2) RISK-FREE RATE (FRED) with caching
###############################################################################
_cached_rfr = None
_rfr_cache_time = None

def get_risk_free_rate_fred(api_key):
    """Get risk-free rate with caching to avoid repeated API calls"""
    global _cached_rfr, _rfr_cache_time
    
    # Use cache if less than 1 hour old
    if _cached_rfr is not None and _rfr_cache_time is not None:
        if time.time() - _rfr_cache_time < 3600:
            return _cached_rfr
    
    try:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id=DGS3MO&api_key={api_key}&file_type=json"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
        rfr = float(obs[-1]["value"]) / 100.0 if obs else 0.0
        
        # Cache the result
        _cached_rfr = rfr
        _rfr_cache_time = time.time()
        
        return rfr
    except Exception as e:
        logging.warning(f"Failed to get risk-free rate: {e}")
        return 0.0

###############################################################################
# 3) ULTRA-FAST DATA FETCHING with vectorized operations
###############################################################################
def fetch_symbol_data_vectorized(symbols_batch, retry_count=0):
    """Fetch multiple symbols with single query for maximum efficiency"""
    if not symbols_batch:
        return {}
    
    print(f"DEBUG: Fetching data for symbols: {symbols_batch}")
    
    conn = get_optimized_connection(retry_count)
    symbol_data = {}
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Use parameterized query with ANY for batch processing
            sql = f"""
                SELECT
                    p.symbol, p.date, p.open, p.high, p.low, p.close, p.volume,
                    COALESCE(t.rsi, 50.0) as rsi,                    COALESCE(t.atr, 1.0) as atr,  
                    COALESCE(t.adx, 25.0) as adx,
                    COALESCE(t.sma_50, p.close) AS "TrendMA",
                    t.pivot_high AS "PivotHighRaw",
                    t.pivot_low AS "PivotLowRaw"
                FROM {PRICE_TABLE} p
                LEFT JOIN {TECH_TABLE} t
                    ON p.symbol = t.symbol AND p.date = t.date
                WHERE p.symbol = ANY(%s)
                    AND p.date >= CURRENT_DATE - INTERVAL '2 years'
                ORDER BY p.symbol, p.date ASC
            """
            
            print(f"DEBUG: Executing query on tables {PRICE_TABLE} and {TECH_TABLE}")
            cur.execute(sql, (symbols_batch,))
            rows = cur.fetchall()
            print(f"DEBUG: Query returned {len(rows)} rows")
            
            # Group by symbol using vectorized operations
            df_all = pd.DataFrame(rows)
            if not df_all.empty:
                df_all['date'] = pd.to_datetime(df_all['date'])
                
                # Optimize data types
                numeric_cols = ['open','high','low','close','volume',
                              'rsi','atr','adx','TrendMA','PivotHighRaw','PivotLowRaw']
                for col in numeric_cols:
                    df_all[col] = pd.to_numeric(df_all[col], errors='coerce')
                
                # Group by symbol efficiently
                for symbol in symbols_batch:
                    symbol_df = df_all[df_all['symbol'] == symbol].copy()
                    if not symbol_df.empty:
                        symbol_df = symbol_df.drop('symbol', axis=1).reset_index(drop=True)
                        symbol_data[symbol] = optimize_dataframe(symbol_df)
                        print(f"DEBUG: Symbol {symbol} has {len(symbol_df)} rows")
                    else:
                        print(f"DEBUG: No data for symbol {symbol}")
            else:
                print("DEBUG: DataFrame is empty after query")
    
    except Exception as e:
        logging.error(f"Batch fetch error: {e}")
        print(f"DEBUG: Fetch error: {e}")
    finally:
        conn.close()
    
    print(f"DEBUG: Returning data for {len(symbol_data)} symbols")
    return symbol_data

###############################################################################
# 4) ULTRA-FAST SIGNAL GENERATION (Pure NumPy/Pandas vectorized)
###############################################################################
def generate_signals_vectorized(df, atrMult=1.0, useADX=True, adxThreshold=25):
    """Ultra-fast signal generation using pure NumPy vectorization"""
    if df.empty:
        return df
    
    # Convert to NumPy arrays for maximum speed
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    rsi = df['rsi'].values
    atr = df['atr'].values
    adx = df['adx'].values
    trend_ma = df['TrendMA'].values
    pivot_high = df['PivotHighRaw'].values
    pivot_low = df['PivotLowRaw'].values
    
    n = len(df)
    
    # Vectorized calculations
    trend_ok = close > trend_ma
    rsi_prev = np.roll(rsi, 1)
    rsi_prev[0] = rsi[0]  # Handle first element
    
    rsi_buy = (rsi > 50) & (rsi_prev <= 50)
    rsi_sell = (rsi < 50) & (rsi_prev >= 50)
      # Pivot levels using forward fill - handle NaN values properly
    last_ph = pivot_high.copy()
    last_pl = pivot_low.copy()
    
    # Forward fill using pandas-style logic
    for i in range(1, n):
        if pd.isna(last_ph[i]) and i > 0:
            last_ph[i] = last_ph[i-1] if not pd.isna(last_ph[i-1]) else high[i]
        if pd.isna(last_pl[i]) and i > 0:
            last_pl[i] = last_pl[i-1] if not pd.isna(last_pl[i-1]) else low[i]
    
    # Handle first elements if they're NaN
    if pd.isna(last_ph[0]):
        last_ph[0] = high[0]
    if pd.isna(last_pl[0]):
        last_pl[0] = low[0]
    
    # Stop and buy levels
    stop_buffer = atr * atrMult
    stop_level = last_pl - stop_buffer
    buy_level = last_ph
    
    # Breakout signals
    breakout_buy = high > buy_level
    breakout_sell = low < stop_level
    
    # Final signals with ADX
    if useADX:
        adx_strong = adx > adxThreshold
        final_buy = ((rsi_buy & trend_ok & adx_strong) | breakout_buy)
        final_sell = (rsi_sell | breakout_sell)
    else:
        final_buy = ((rsi_buy & trend_ok) | breakout_buy)
        final_sell = (rsi_sell | breakout_sell)
    
    # Ultra-fast position tracking with NumPy
    signals = np.full(n, 'None', dtype='U4')
    in_position = np.zeros(n, dtype=bool)
    
    pos = False
    for i in range(n):
        if pos and final_sell[i]:
            signals[i] = 'Sell'
            pos = False
        elif not pos and final_buy[i]:
            signals[i] = 'Buy'
            pos = True
        in_position[i] = pos
    
    # Add results back to DataFrame
    df = df.copy()
    df['TrendOK'] = trend_ok
    df['stopLevel'] = stop_level
    df['buyLevel'] = buy_level
    df['Signal'] = signals
    df['inPosition'] = in_position
    
    return optimize_dataframe(df)

###############################################################################
# 5) PARALLEL PROCESSING ENGINE
###############################################################################
def process_symbol_batch(symbols_batch):
    """Process a batch of symbols in parallel with timeout retry logic"""
    log_performance(f"Processing batch of {len(symbols_batch)} symbols")
    
    # Fetch all data for batch in single query with retry logic
    try:
        symbol_data = retry_with_timeout_reduction(fetch_symbol_data_vectorized, symbols_batch)
    except Exception as e:
        logging.error(f"Failed to fetch data for batch after retries: {e}")
        return []  # Return empty results for this batch
    
    # Process signals for each symbol
    results = []
    for symbol in symbols_batch:
        if symbol in symbol_data:
            df = symbol_data[symbol]
            if not df.empty:
                try:
                    df_signals = generate_signals_vectorized(df)
                    results.append((symbol, TIMEFRAME.title(), df_signals))
                except Exception as e:
                    logging.error(f"Signal generation failed for {symbol}: {e}")
        else:
            logging.warning(f"No data for symbol: {symbol}")
    
    # Force garbage collection
    del symbol_data
    gc.collect()
    
    return results

def parallel_process_symbols(symbols, batch_size=40, max_workers=2):
    """Process symbols in parallel batches for maximum throughput - optimized for reduced database load"""
    log_performance("Starting parallel processing")
    
    # Split into batches
    symbol_batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    all_results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all batches
        future_to_batch = {
            executor.submit(process_symbol_batch, batch): batch 
            for batch in symbol_batches
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_batch):
            batch = future_to_batch[future]
            try:
                batch_results = future.result()
                all_results.extend(batch_results)
                log_performance(f"Completed batch with {len(batch)} symbols")
            except Exception as e:
                logging.error(f"Batch processing failed: {e}")
    
    log_performance("Parallel processing complete")
    return all_results

###############################################################################
# 6) OPTIMIZED MAIN EXECUTION
###############################################################################
def main():
    """Main execution with full optimization"""
    start_time = time.time()
    log_performance("Startup")
    
    print("=== DEBUG: Starting loadbuyselldaily.py ===")
    
    try:
        # Get risk-free rate with caching
        annual_rfr = get_risk_free_rate_fred(FRED_API_KEY)
        logging.info(f"Annual RFR: {annual_rfr:.2%}")
        print(f"DEBUG: Got RFR: {annual_rfr}")
    except Exception as e:
        logging.warning(f"Failed to get risk-free rate: {e}")
        print(f"DEBUG: RFR error: {e}")
        annual_rfr = 0.0
      # Get symbols efficiently
    symbols = get_symbols_batch()
    print(f"DEBUG: Got {len(symbols)} symbols from database")
    if not symbols:
        logging.info("No symbols found in database")
        return
    
    logging.info(f"Processing {len(symbols)} symbols for {TIMEFRAME} timeframe")
    
    # Setup database connection
    conn = get_optimized_connection()
    try:
        with conn.cursor() as cur:
            # Create table with optimizations
            create_buy_sell_table_optimized(cur)
            conn.commit()
            log_performance("Database setup complete")
            print("DEBUG: Database table created")
              # Process symbols in parallel batches
            all_results = parallel_process_symbols(symbols)
            print(f"DEBUG: Got {len(all_results)} results from processing")
            log_performance(f"Generated signals for {len(all_results)} symbols")
            
            # Bulk insert all results
            if all_results:
                total_inserted = bulk_insert_results(cur, all_results)
                conn.commit()
                logging.info(f"Bulk inserted {total_inserted} records")
                print(f"DEBUG: Inserted {total_inserted} records")
                log_performance("Database insertion complete")
            else:
                print("DEBUG: No results to insert!")
            
            # Record completion
            cur.execute("""
                INSERT INTO last_updated (script_name, last_run)
                VALUES (%s, NOW())
                ON CONFLICT (script_name) DO UPDATE
                SET last_run = EXCLUDED.last_run
            """, (SCRIPT_NAME,))
            conn.commit()
            
    finally:
        conn.close()
      # Final cleanup and reporting
    gc.collect()
    end_time = time.time()
    execution_time = end_time - start_time
    
    log_performance("Final")
    logging.info(f"Processing complete in {execution_time:.2f} seconds")
    logging.info(f"Processed {len(symbols)} symbols")
    logging.info(f"Generated signals for {len(all_results)} symbols")
    print(f"DEBUG: Completed in {execution_time:.2f} seconds")

if __name__ == "__main__":
    main()
