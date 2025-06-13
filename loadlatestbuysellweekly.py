#!/usr/bin/env python3  
"""
Latest Weekly Buy/Sell Signal Generator (Incremental)
- Processes only symbols with new/changed technical indicators data
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
import warnings
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import boto3
import requests
import pandas as pd
import numpy as np
import psutil

# Suppress warnings for performance
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)

# -------------------------------
# Script metadata & logging setup  
# -------------------------------
SCRIPT_NAME = "loadlatestbuysellweekly.py"
TIMEFRAME = "weekly"
PRICE_TABLE = "price_weekly"
TECH_TABLE = "technical_data_weekly"
BUYSELL_TABLE = "buy_sell_weekly"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

logging.info("🚀 Latest Weekly Buy/Sell Signal Generator - Incremental Processing!")

# -------------------------------
# Memory and performance monitoring
# -------------------------------
def get_rss_mb():
    """Get RSS memory usage in MB - works on all platforms"""
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

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
    
    return df

# -------------------------------
# Database configuration
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

def get_optimized_connection():
    """Get database connection with performance optimizations"""
    cfg = get_db_config()
    
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"],
        connect_timeout=60,
        application_name=f"{SCRIPT_NAME}",
        keepalives_idle=600,
        keepalives_interval=30,
        keepalives_count=3
    )
    
    # Set performance parameters
    with conn.cursor() as cur:
        cur.execute("SET work_mem = '256MB'")
        cur.execute("SET effective_cache_size = '4GB'")
        cur.execute("SET random_page_cost = 1.1")
        cur.execute("SET statement_timeout = '300s'")
        cur.execute("SET lock_timeout = '60s'")
    
    conn.commit()
    logging.info("✅ Database connection established")
    return conn

# -------------------------------
# FRED API for risk-free rate
# -------------------------------
FRED_API_KEY = os.environ["FRED_API_KEY"]

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

# -------------------------------
# Incremental symbol identification
# -------------------------------
def identify_symbols_needing_updates(cur, lookback_weeks=4):
    """
    Identify symbols that have new weekly technical indicators data and need buy/sell signals updated.
    Similar to the technical indicators approach - looks for symbols with technical data newer than buy/sell data.
    """
    logging.info("🔍 Identifying symbols with recent weekly technical indicators updates that need buy/sell signals...")
    
    # Find symbols that have technical indicators data newer than their buy/sell signals
    # OR symbols that have no buy/sell signals at all
    cur.execute("""
        WITH tech_dates AS (
            SELECT symbol, MAX(date) as latest_tech_date
            FROM technical_data_weekly 
            WHERE date >= CURRENT_DATE - INTERVAL '%s weeks'
            GROUP BY symbol
        ),
        buysell_dates AS (
            SELECT symbol, MAX(date) as latest_buysell_date
            FROM buy_sell_weekly 
            GROUP BY symbol
        )
        SELECT 
            t.symbol,
            t.latest_tech_date,
            COALESCE(b.latest_buysell_date, '1900-01-01'::date) as latest_buysell_date,
            (t.latest_tech_date > COALESCE(b.latest_buysell_date, '1900-01-01'::date)) as needs_update
        FROM tech_dates t
        LEFT JOIN buysell_dates b ON t.symbol = b.symbol
        WHERE t.latest_tech_date > COALESCE(b.latest_buysell_date, '1900-01-01'::date)
        ORDER BY t.symbol;
    """, (lookback_weeks,))
    
    results = cur.fetchall()
    symbols_to_update = []
    
    for row in results:
        symbol = row['symbol']
        latest_tech = row['latest_tech_date']
        latest_buysell = row['latest_buysell_date']
        needs_update = row['needs_update']
        
        if needs_update:
            symbols_to_update.append({
                'symbol': symbol,
                'latest_tech_date': latest_tech,
                'latest_buysell_date': latest_buysell
            })
            logging.info(f"📊 {symbol}: Tech data through {latest_tech}, buy/sell through {latest_buysell} → UPDATE NEEDED")
    
    logging.info(f"🎯 Found {len(symbols_to_update)} symbols needing weekly buy/sell signal updates")
    return symbols_to_update

# -------------------------------
# Data fetching for incremental processing
# -------------------------------
def fetch_symbol_data_incremental(symbol_info, db_config, lookback_periods=100):
    """
    Fetch weekly price and technical data for a single symbol with sufficient lookback for signal generation.
    Similar to the technical indicators approach but focused on buy/sell signal generation.
    """
    symbol = symbol_info['symbol']
    latest_tech_date = symbol_info['latest_tech_date']
    latest_buysell_date = symbol_info['latest_buysell_date']
    
    try:
        conn = psycopg2.connect(**db_config)
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Set performance parameters
        cur.execute("SET work_mem = '512MB'")
        cur.execute("SET effective_cache_size = '4GB'")
        cur.execute("SET random_page_cost = 1.0")
        cur.execute("SET statement_timeout = '180s'")
        
        logging.info(f"🔄 Processing {symbol}: Need to update from {latest_buysell_date} to {latest_tech_date}")
        
        # Determine the date range - need enough lookback for signal generation (fewer periods for weekly)
        start_date = latest_tech_date - timedelta(weeks=lookback_periods)
        
        # Load weekly price and technical data with sufficient lookback
        cur.execute(f"""
            SELECT
                p.date, p.open, p.high, p.low, p.close, p.volume,
                COALESCE(t.rsi, 50.0) as rsi,
                COALESCE(t.atr, 1.0) as atr,  
                COALESCE(t.adx, 25.0) as adx,
                COALESCE(t.sma_50, p.close) AS trend_ma,
                COALESCE(t.pivot_high, p.high) AS pivot_high_raw,
                COALESCE(t.pivot_low, p.low) AS pivot_low_raw
            FROM {PRICE_TABLE} p
            LEFT JOIN {TECH_TABLE} t
                ON p.symbol = t.symbol AND p.date = t.date
            WHERE p.symbol = %s
                AND p.date >= %s
                AND p.volume > 100
                AND p.close > 0.01
            ORDER BY p.date ASC
        """, (symbol, start_date))
        
        data_rows = cur.fetchall()
        
        if not data_rows:
            logging.warning(f"⚠️  {symbol}: No weekly data found for date range {start_date} to {latest_tech_date}")
            cur.close()
            conn.close()
            return None
        
        logging.info(f"📈 {symbol}: Loaded {len(data_rows)} weekly records for buy/sell signal analysis")
        
        # Convert to DataFrame
        df = pd.DataFrame(data_rows)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.sort_index(inplace=True)
        
        # Optimize dtypes for memory and speed
        df = df.astype({
            'open': 'float32',
            'high': 'float32',
            'low': 'float32', 
            'close': 'float32',
            'volume': 'int32',
            'rsi': 'float32',
            'atr': 'float32',
            'adx': 'float32',
            'trend_ma': 'float32',
            'pivot_high_raw': 'float32',
            'pivot_low_raw': 'float32'
        })
        
        cur.close()
        conn.close()
        
        return df
        
    except Exception as e:
        logging.error(f"❌ {symbol}: Error fetching weekly data - {str(e)}")
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()
        return None

# -------------------------------
# Ultra-fast signal generation (same as daily but for weekly data)
# -------------------------------
def generate_signals_vectorized(df, atr_mult=1.0, use_adx=True, adx_threshold=25):
    """Ultra-fast weekly signal generation using pure NumPy vectorization"""
    if df.empty:
        return df
    
    # Convert to NumPy arrays for maximum speed
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    rsi = df['rsi'].values
    atr = df['atr'].values
    adx = df['adx'].values
    trend_ma = df['trend_ma'].values
    pivot_high = df['pivot_high_raw'].values
    pivot_low = df['pivot_low_raw'].values
    
    n = len(df)
    
    # Vectorized calculations
    trend_ok = close > trend_ma
    rsi_prev = np.roll(rsi, 1)
    rsi_prev[0] = rsi[0]  # Handle first element
    
    rsi_buy = (rsi > 50) & (rsi_prev <= 50)
    rsi_sell = (rsi < 50) & (rsi_prev >= 50)
    
    # Pivot levels using forward fill
    last_ph = np.roll(pivot_high, 1)
    last_pl = np.roll(pivot_low, 1)
    last_ph[0] = pivot_high[0]
    last_pl[0] = pivot_low[0]
    
    # Forward fill using optimized loop
    for i in range(1, n):
        if np.isnan(last_ph[i]):
            last_ph[i] = last_ph[i-1]
        if np.isnan(last_pl[i]):
            last_pl[i] = last_pl[i-1]
    
    # Stop and buy levels
    stop_buffer = atr * atr_mult
    stop_level = last_pl - stop_buffer
    buy_level = last_ph
    
    # Breakout signals
    breakout_buy = high > buy_level
    breakout_sell = low < stop_level
    
    # Final signals with ADX
    if use_adx:
        adx_strong = adx > adx_threshold
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
    df['trend_ok'] = trend_ok
    df['stop_level'] = stop_level
    df['buy_level'] = buy_level
    df['signal'] = signals
    df['in_position'] = in_position
    
    return optimize_dataframe(df)

# -------------------------------
# Process single symbol incrementally
# -------------------------------
def process_symbol_incremental(symbol_info, db_config):
    """
    Process weekly buy/sell signals for a single symbol incrementally.
    Similar to the technical indicators approach but for buy/sell signals.
    """
    symbol = symbol_info['symbol']
    latest_tech_date = symbol_info['latest_tech_date']
    latest_buysell_date = symbol_info['latest_buysell_date']
    
    try:
        # Fetch data for the symbol
        df = fetch_symbol_data_incremental(symbol_info, db_config)
        
        if df is None or df.empty:
            logging.warning(f"❌ {symbol}: No weekly data available for signal generation")
            return False
        
        # Generate buy/sell signals
        signal_start = time.time()
        df_signals = generate_signals_vectorized(df)
        signal_time = time.time() - signal_start
        
        if df_signals.empty:
            logging.warning(f"❌ {symbol}: Failed to generate weekly signals - empty result")
            return False
        
        logging.info(f"⚡ {symbol}: Generated weekly buy/sell signals in {signal_time:.2f}s")
        
        # Filter to only the NEW dates we need to insert/update
        if latest_buysell_date and latest_buysell_date != datetime(1900, 1, 1).date():
            # Update mode - only process dates newer than existing buy/sell data
            mask = df_signals.index.date > latest_buysell_date
            df_new = df_signals[mask].copy()
            operation = "UPDATE"
        else:
            # New symbol - process all calculated data
            df_new = df_signals.copy()
            operation = "INSERT"
        
        if df_new.empty:
            logging.info(f"✅ {symbol}: No new weekly buy/sell signals to process - already up to date")
            return True
        
        logging.info(f"📊 {symbol}: {operation} - Processing {len(df_new)} new weekly buy/sell signal records")
        
        # Insert into database
        conn = psycopg2.connect(**db_config)
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Delete existing data for the date range we're updating
            if operation == "UPDATE":
                cur.execute(f"""
                    DELETE FROM {BUYSELL_TABLE} 
                    WHERE symbol = %s 
                    AND date >= %s
                """, (symbol, df_new.index.min().date()))
                conn.commit()
            
            # Prepare data for insertion
            insert_start = time.time()
            insert_data = []
            
            df_reset = df_new.reset_index()
            
            for idx in range(len(df_reset)):
                row = df_reset.iloc[idx]
                  # Convert string signal to numeric value
                signal_value = 0  # Default neutral
                if row.get('signal') == 'Buy':
                    signal_value = 1
                elif row.get('signal') == 'Sell':
                    signal_value = -1
                else:
                    continue  # Skip 'None' signals
                
                record = (
                    symbol,
                    TIMEFRAME,
                    row['date'].to_pydatetime() if hasattr(row['date'], 'to_pydatetime') else row['date'],
                    signal_value,
                    float(row.get('buy_level')) if not pd.isna(row.get('buy_level')) else None,
                    float(row.get('stop_level')) if not pd.isna(row.get('stop_level')) else None,
                    bool(row.get('in_position', False))
                )
                insert_data.append(record)
            
            insert_prep_time = time.time() - insert_start
            
            # Bulk insert
            if insert_data:
                bulk_insert_start = time.time()
                insert_query = f"""
                INSERT INTO {BUYSELL_TABLE} (
                    symbol, timeframe, date, signal, buylevel, stoplevel, inposition
                ) VALUES %s
                ON CONFLICT (symbol, timeframe, date) DO UPDATE SET
                    signal = EXCLUDED.signal,
                    buylevel = EXCLUDED.buylevel,
                    stoplevel = EXCLUDED.stoplevel,
                    inposition = EXCLUDED.inposition
                """
                
                execute_values(cur, insert_query, insert_data, page_size=1000)
                conn.commit()
                
                bulk_insert_time = time.time() - bulk_insert_start
                records_per_sec = len(insert_data) / bulk_insert_time if bulk_insert_time > 0 else 0
                
                logging.info(f"🚀 {symbol}: Inserted {len(insert_data)} weekly records in {bulk_insert_time:.2f}s ({records_per_sec:.0f} records/sec)")
            else:
                logging.info(f"📊 {symbol}: No actionable weekly signals to insert (all 'None' signals filtered out)")
            
            # Clean up
            cur.close()
            conn.close()
            
            return True
            
        except Exception as e:
            logging.error(f"❌ {symbol}: Database error during weekly incremental processing - {str(e)}")
            cur.close()
            conn.close()
            return False
        
    except Exception as e:
        logging.error(f"❌ {symbol}: Error during weekly incremental signal processing - {str(e)}")
        return False

# -------------------------------
# Main incremental loader with optimized batch processing
# -------------------------------
def load_latest_buysell_optimized(symbols_to_update):
    """Optimized incremental weekly buy/sell signal loader with parallel execution"""
    total = len(symbols_to_update)
    logging.info(f"🚀 Starting incremental weekly buy/sell signal generation for {total} symbols")
    
    # Dynamic configuration based on total symbols
    if total <= 20:
        MAX_WORKERS = 2
    elif total <= 100:
        MAX_WORKERS = 2
    else:
        MAX_WORKERS = 2  # Conservative for database stability
    
    logging.info(f"⚙️  Configuration: {MAX_WORKERS} parallel workers")
    
    db_config = get_db_config()
    all_processed_symbols = []
    all_failed_symbols = []
    
    log_performance("before incremental processing")
    start_time = time.time()
    
    # Process symbols with controlled parallelization
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all symbol processing tasks
        symbol_futures = {}
        
        for symbol_info in symbols_to_update:
            future = executor.submit(process_symbol_incremental, symbol_info, db_config)
            symbol_futures[future] = symbol_info['symbol']
        
        logging.info(f"📋 Submitted {len(symbol_futures)} weekly buy/sell signal processing tasks")
        
        # Process completed symbols as they finish
        completed_symbols = 0
        
        for future in as_completed(symbol_futures):
            symbol = symbol_futures[future]
            completed_symbols += 1
            
            try:
                success = future.result()
                if success:
                    all_processed_symbols.append(symbol)
                else:
                    all_failed_symbols.append(symbol)
                
                # Calculate progress and ETA
                progress_pct = (completed_symbols / total) * 100
                elapsed_time = time.time() - start_time
                
                if completed_symbols > 1:
                    avg_time_per_symbol = elapsed_time / completed_symbols
                    remaining_symbols = total - completed_symbols
                    eta_seconds = avg_time_per_symbol * remaining_symbols
                    eta_minutes = eta_seconds / 60
                    
                    logging.info(f"📈 Progress: {completed_symbols}/{total} symbols ({progress_pct:.1f}%) | "
                                f"Symbol {symbol}: {'✅ SUCCESS' if success else '❌ FAILED'} | "
                                f"ETA: {eta_minutes:.1f} minutes")
                else:
                    logging.info(f"📊 Symbol {completed_symbols}/{total}: {symbol} "
                                f"{'✅ processed successfully' if success else '❌ processing failed'}")
                
                # Force garbage collection periodically
                if completed_symbols % 10 == 0:
                    gc.collect()
                    log_performance(f"after {completed_symbols} symbols")
                
            except Exception as e:
                logging.error(f"❌ Symbol {symbol} failed completely: {str(e)}")
                all_failed_symbols.append(symbol)
    
    # Final performance summary
    total_time = time.time() - start_time
    successful_count = len(all_processed_symbols)
    failed_count = len(all_failed_symbols)
    
    logging.info(f"🎯 Incremental weekly buy/sell signal update complete!")
    logging.info(f"📊 Results: {successful_count}/{total} symbols processed successfully")
    logging.info(f"⏱️  Total time: {total_time/60:.2f} minutes ({total_time:.1f} seconds)")
    logging.info(f"⚡ Performance: {successful_count/(total_time/60):.1f} symbols/minute")
    
    if failed_count > 0:
        logging.warning(f"⚠️  {failed_count} symbols failed processing:")
        for i, symbol in enumerate(all_failed_symbols[:20]):
            logging.warning(f"  - {symbol}")
        if failed_count > 20:
            logging.warning(f"  ... and {failed_count - 20} more symbols failed")
    else:
        logging.info("✅ All symbols processed successfully!")
    
    log_performance("final memory usage")
    
    return total, successful_count, all_failed_symbols

# -------------------------------
# Main execution
# -------------------------------
def main():
    """Main function with proper error handling for ECS task completion"""
    exit_code = 0
    conn = None
    cur = None
    
    try:
        log_performance("startup")
        logging.info(f"🚀 Starting {SCRIPT_NAME}")

        # Get risk-free rate with caching
        try:
            annual_rfr = get_risk_free_rate_fred(FRED_API_KEY)
            logging.info(f"📊 Annual Risk-Free Rate: {annual_rfr:.2%}")
        except Exception as e:
            logging.warning(f"Failed to get risk-free rate: {e}")
            annual_rfr = 0.0

        # Connect to DB
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Identify symbols that need weekly buy/sell signal updates
        symbols_to_update = identify_symbols_needing_updates(cur, lookback_weeks=4)
        
        if not symbols_to_update:
            logging.info("✅ No symbols need weekly buy/sell signal updates - all up to date!")
            
            # Record last run even if no work was needed
            cur.execute("""
              INSERT INTO last_updated (script_name, last_run)
              VALUES (%s, NOW())
              ON CONFLICT (script_name) DO UPDATE
                SET last_run = EXCLUDED.last_run;
            """, (SCRIPT_NAME,))
            conn.commit()
            
            logging.info("🏁 Latest weekly buy/sell signal loader completed - no updates needed")
            return exit_code

        logging.info(f"📊 Found {len(symbols_to_update)} symbols needing weekly buy/sell signal updates")

        # Process weekly buy/sell signals incrementally
        total, inserted, failed = load_latest_buysell_optimized(symbols_to_update)

        # Ensure cursor is still valid after processing
        try:
            cur.execute("SELECT 1")
        except (psycopg2.InterfaceError, psycopg2.OperationalError):
            logging.info("Reconnecting to database after weekly buy/sell signal processing...")
            cur.close()
            conn.close()
            conn = psycopg2.connect(
                host=cfg["host"], port=cfg["port"],
                user=cfg["user"], password=cfg["password"],
                dbname=cfg["dbname"]
            )
            conn.autocommit = False
            cur = conn.cursor(cursor_factory=RealDictCursor)

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
        logging.info(f"📈 Total symbols: {total}, Successfully processed: {inserted}, Failed: {len(failed)}")
        
        if failed:
            logging.warning(f"⚠️ Failed symbols ({len(failed)}): {failed[:10]}...")
            if len(failed) > len(symbols_to_update) * 0.5:  # More than 50% failed
                logging.error(f"❌ Too many failures ({len(failed)}/{total}), marking as failed")
                exit_code = 1
            else:
                logging.info(f"✅ Acceptable failure rate ({len(failed)}/{total})")

        logging.info("✅ Latest weekly buy/sell signal processing completed successfully")
        
    except KeyboardInterrupt:
        logging.warning("⚠️ Received interrupt signal, shutting down gracefully...")
        exit_code = 130
    except Exception as e:
        logging.error(f"❌ Critical error in {SCRIPT_NAME}: {str(e)}", exc_info=True)
        exit_code = 1
    finally:
        # Clean up database connections
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass
        
        logging.info(f"🏁 {SCRIPT_NAME} finished with exit code {exit_code}")
        
    return exit_code

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
