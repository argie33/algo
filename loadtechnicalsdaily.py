#!/usr/bin/env python3  
import sys
import time
import logging
import json
import os
import gc
import resource
import warnings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from functools import partial

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import boto3
import numpy as np
import pandas as pd
try:
    import talib
    TALIB_AVAILABLE = True
    logging.info("✅ TA-Lib loaded successfully")
except ImportError as e:
    TALIB_AVAILABLE = False
    logging.error(f"❌ TA-Lib not available: {e}")
    logging.error("Please ensure TA-Lib C library is properly installed")
    sys.exit(1)

# Suppress warnings for performance
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadtechnicalsdaily.py"
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
# Technical indicators columns (optimized for ECS)
# -------------------------------
TECHNICALS_COLUMNS = [
    "symbol", "date",
    "rsi", "macd", "macd_signal", "macd_hist",
    "mom", "roc", "adx", "atr", "ad", "cmf", "mfi",
    "td_sequential", "td_combo", "marketwatch", "dm",
    "sma_10", "sma_20", "sma_50", "sma_150", "sma_200",
    "ema_4", "ema_9", "ema_21",
    "bbands_lower", "bbands_middle", "bbands_upper",
    "pivot_high", "pivot_low",
    "fetched_at"
]

# -------------------------------
# DB config loader
# -------------------------------
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

def sanitize_value(x):
    """Convert NaN/inf values to None for database insertion"""
    if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
        return None
    return x

# -------------------------------
# Highly optimized technical indicators using TA-Lib
# -------------------------------

def calculate_rsi(prices, period=14):
    """TA-Lib RSI calculation - extremely fast C implementation"""
    return pd.Series(talib.RSI(prices.values, timeperiod=period), index=prices.index)

def calculate_sma(prices, period):
    """TA-Lib SMA calculation"""
    return pd.Series(talib.SMA(prices.values, timeperiod=period), index=prices.index)

def calculate_ema(prices, period):
    """TA-Lib EMA calculation"""
    return pd.Series(talib.EMA(prices.values, timeperiod=period), index=prices.index)

def calculate_atr(high, low, close, period=14):
    """TA-Lib ATR calculation"""
    return pd.Series(talib.ATR(high.values, low.values, close.values, timeperiod=period), index=high.index)

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """TA-Lib MACD calculation"""
    macd_line, signal_line, histogram = talib.MACD(prices.values, fastperiod=fast, slowperiod=slow, signalperiod=signal)
    return (pd.Series(macd_line, index=prices.index), 
            pd.Series(signal_line, index=prices.index), 
            pd.Series(histogram, index=prices.index))

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    """TA-Lib Bollinger Bands calculation"""
    upper, middle, lower = talib.BBANDS(prices.values, timeperiod=period, nbdevup=std_dev, nbdevdn=std_dev, matype=0)
    return (pd.Series(lower, index=prices.index), 
            pd.Series(middle, index=prices.index), 
            pd.Series(upper, index=prices.index))

def calculate_momentum(prices, period=10):
    """TA-Lib Momentum calculation"""
    return pd.Series(talib.MOM(prices.values, timeperiod=period), index=prices.index)

def calculate_roc(prices, period=10):
    """TA-Lib Rate of Change calculation"""
    return pd.Series(talib.ROC(prices.values, timeperiod=period), index=prices.index)

def calculate_adx(high, low, close, period=14):
    """TA-Lib ADX calculation"""
    return pd.Series(talib.ADX(high.values, low.values, close.values, timeperiod=period), index=high.index).fillna(0)

def calculate_accumulation_distribution(high, low, close, volume):
    """TA-Lib A/D Line calculation"""
    return pd.Series(talib.AD(high.values, low.values, close.values, volume.values), index=high.index)

def calculate_cmf(high, low, close, volume, period=20):
    """TA-Lib Chaikin Money Flow calculation"""
    ad_line = talib.AD(high.values, low.values, close.values, volume.values)
    ad_sum = pd.Series(ad_line, index=high.index).rolling(window=period, min_periods=period).sum()
    volume_sum = volume.rolling(window=period, min_periods=period).sum()
    return ad_sum / volume_sum

def calculate_mfi(high, low, close, volume, period=14):
    """TA-Lib Money Flow Index calculation"""
    return pd.Series(talib.MFI(high.values, low.values, close.values, volume.values, timeperiod=period), index=high.index).fillna(50)
def pivot_high_vectorized(high, left_bars=3, right_bars=3):
    """Vectorized pivot high calculation"""
    roll_left = high.shift(1).rolling(window=left_bars, min_periods=left_bars).max()
    roll_right = high.shift(-1).rolling(window=right_bars, min_periods=right_bars).max()
    cond = (high > roll_left) & (high > roll_right)
    return high.where(cond, np.nan)

def pivot_low_vectorized(low, left_bars=3, right_bars=3):
    """Vectorized pivot low calculation"""
    roll_left = low.shift(1).rolling(window=left_bars, min_periods=left_bars).min()
    roll_right = low.shift(-1).rolling(window=right_bars, min_periods=right_bars).min()
    cond = (low < roll_left) & (low < roll_right)
    return low.where(cond, np.nan)

def td_sequential_vectorized(close, lookback=4):
    """Vectorized TD Sequential indicator"""
    # Compare current close with close N periods ago
    comparison = np.where(close < close.shift(lookback), 1, 
                         np.where(close > close.shift(lookback), -1, 0))
    
    # Convert to series for easier manipulation
    comp_series = pd.Series(comparison, index=close.index)
    
    # Initialize result
    result = np.zeros(len(close))
    
    # Vectorized approach using groupby
    changes = comp_series != comp_series.shift(1)
    groups = changes.cumsum()
    
    for group_id, group in comp_series.groupby(groups):
        if len(group) > 0 and group.iloc[0] != 0:
            start_idx = group.index[0]
            start_pos = close.index.get_loc(start_idx)
            group_len = len(group)
            
            if group.iloc[0] == 1:  # Bearish sequence
                result[start_pos:start_pos+group_len] = range(1, group_len + 1)
            elif group.iloc[0] == -1:  # Bullish sequence
                result[start_pos:start_pos+group_len] = range(-1, -(group_len + 1), -1)
    
    return pd.Series(result, index=close.index)

def td_combo_vectorized(close, lookback=2):
    """Vectorized TD Combo indicator"""
    comparison = np.where(close < close.shift(lookback), 1, 
                         np.where(close > close.shift(lookback), -1, 0))
    
    comp_series = pd.Series(comparison, index=close.index)
    result = np.zeros(len(close))
    
    changes = comp_series != comp_series.shift(1)
    groups = changes.cumsum()
    
    for group_id, group in comp_series.groupby(groups):
        if len(group) > 0 and group.iloc[0] != 0:
            start_idx = group.index[0]
            start_pos = close.index.get_loc(start_idx)
            group_len = len(group)
            
            if group.iloc[0] == 1:
                result[start_pos:start_pos+group_len] = range(1, group_len + 1)
            elif group.iloc[0] == -1:
                result[start_pos:start_pos+group_len] = range(-1, -(group_len + 1), -1)
    
    return pd.Series(result, index=close.index)

def marketwatch_indicator_vectorized(close, open_):
    """Vectorized MarketWatch indicator"""
    signal = np.where(close > open_, 1, np.where(close < open_, -1, 0))
    signal_series = pd.Series(signal, index=close.index)
    
    result = np.zeros(len(close))
    changes = (signal_series != signal_series.shift(1)) | (signal_series == 0)
    groups = changes.cumsum()
    
    for group_id, group in signal_series.groupby(groups):
        if len(group) > 0 and group.iloc[0] != 0:
            start_idx = group.index[0]
            start_pos = close.index.get_loc(start_idx)
            group_len = len(group)
            
            if group.iloc[0] == 1:
                result[start_pos:start_pos+group_len] = range(1, group_len + 1)
            elif group.iloc[0] == -1:
                result[start_pos:start_pos+group_len] = range(-1, -(group_len + 1), -1)
    
    return pd.Series(result, index=close.index)

# -------------------------------
# Main technical indicators calculator with parallel processing
# -------------------------------
def calculate_technicals_parallel(df):
    """Calculate all technical indicators using parallel processing where beneficial"""
    # Ensure proper data types
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Fill any gaps and drop NaN rows
    df = df.ffill().bfill().dropna()
    
    if len(df) < 200:  # Need minimum data for indicators
        return pd.DataFrame()
    
    # Use joblib for CPU-intensive calculations (with limited jobs for ECS)
    def calculate_basic_indicators():
        """Calculate basic indicators that don't depend on each other"""
        results = {}
        
        # RSI
        results['rsi'] = calculate_rsi(df['close'], period=14)
        
        # Momentum indicators
        results['mom'] = calculate_momentum(df['close'], period=10)
        results['roc'] = calculate_roc(df['close'], period=10)
        
        # Volume indicators
        results['atr'] = calculate_atr(df['high'], df['low'], df['close'], period=14)
        results['ad'] = calculate_accumulation_distribution(df['high'], df['low'], df['close'], df['volume'])
        results['cmf'] = calculate_cmf(df['high'], df['low'], df['close'], df['volume'], period=20)
        results['mfi'] = calculate_mfi(df['high'], df['low'], df['close'], df['volume'], period=14)
        
        return results
    
    def calculate_moving_averages():
        """Calculate all moving averages in parallel"""
        results = {}
        
        # SMAs
        for period in [10, 20, 50, 150, 200]:
            results[f'sma_{period}'] = calculate_sma(df['close'], period)
        
        # EMAs
        for period in [4, 9, 21]:
            results[f'ema_{period}'] = calculate_ema(df['close'], period)
        
        return results
    
    def calculate_complex_indicators():
        """Calculate indicators that require more computation"""
        results = {}
        
        # MACD
        macd_line, signal_line, histogram = calculate_macd(df['close'], fast=12, slow=26, signal=9)
        results['macd'] = macd_line
        results['macd_signal'] = signal_line
        results['macd_hist'] = histogram
        
        # ADX (computationally expensive)
        results['adx'] = calculate_adx(df['high'], df['low'], df['close'], period=14)
        
        # Bollinger Bands
        bb_lower, bb_middle, bb_upper = calculate_bollinger_bands(df['close'], period=20, std_dev=2)
        results['bbands_lower'] = bb_lower
        results['bbands_middle'] = bb_middle
        results['bbands_upper'] = bb_upper
        
        return results
    
    def calculate_custom_indicators():
        """Calculate custom indicators"""
        results = {}
        
        # Custom indicators
        results['td_sequential'] = td_sequential_vectorized(df['close'], lookback=4)
        results['td_combo'] = td_combo_vectorized(df['close'], lookback=2)
        results['marketwatch'] = marketwatch_indicator_vectorized(df['close'], df['open'])
        
        # Pivot points
        results['pivot_high'] = pivot_high_vectorized(df['high'], left_bars=3, right_bars=3)
        results['pivot_low'] = pivot_low_vectorized(df['low'], left_bars=3, right_bars=3)
        
        # DM calculation
        dm_plus = df['high'].diff()
        dm_minus = df['low'].shift(1) - df['low']
        dm_plus = dm_plus.where((dm_plus>dm_minus)&(dm_plus>0), 0)
        dm_minus = dm_minus.where((dm_minus>dm_plus)&(dm_minus>0), 0)
        results['dm'] = dm_plus - dm_minus
        
        return results
    
    # Execute calculations in parallel (limited to 2 jobs for ECS safety)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit tasks
            basic_future = executor.submit(calculate_basic_indicators)
            ma_future = executor.submit(calculate_moving_averages)
            complex_future = executor.submit(calculate_complex_indicators)
            custom_future = executor.submit(calculate_custom_indicators)
            
            # Collect results
            basic_results = basic_future.result()
            ma_results = ma_future.result()
            complex_results = complex_future.result()
            custom_results = custom_future.result()
    except Exception as e:
        logging.warning(f"Parallel processing failed, falling back to sequential: {e}")
        # Fallback to sequential processing
        basic_results = calculate_basic_indicators()
        ma_results = calculate_moving_averages()
        complex_results = calculate_complex_indicators()
        custom_results = calculate_custom_indicators()
    
    # Combine all results
    for results_dict in [basic_results, ma_results, complex_results, custom_results]:
        for key, value in results_dict.items():
            df[key] = value
    
    # Clean infinite values
    df = df.replace([np.inf, -np.inf], np.nan)
    
    return df

def process_symbol_chunk(symbol_chunk, db_config):
    """Process a chunk of symbols efficiently with optimized batch database operations"""
    try:
        # Create database connection for this chunk
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Batch load all price data for this chunk in one optimized query
        symbols_placeholder = ','.join(['%s'] * len(symbol_chunk))
        
        logging.info(f"📊 Loading price data for {len(symbol_chunk)} symbols in batch...")
        
        # Optimized query with proper parameterization and ordering
        cur.execute(f"""
            SELECT symbol, date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol IN ({symbols_placeholder})
            AND date >= CURRENT_DATE - INTERVAL '5 years'  -- Limit to recent data for performance
            ORDER BY symbol, date ASC
        """, symbol_chunk)
        
        all_rows = cur.fetchall()
        if not all_rows:
            logging.warning(f"No price data found for chunk: {symbol_chunk}")
            cur.close()
            conn.close()
            return []
        
        logging.info(f"📈 Loaded {len(all_rows)} price records for batch processing")
        
        # Convert to DataFrame and group by symbol for efficient processing
        price_df = pd.DataFrame(all_rows)
        price_df['date'] = pd.to_datetime(price_df['date'])
        price_df.set_index(['symbol', 'date'], inplace=True)
        
        # Pre-delete existing technical data for these symbols to avoid conflicts
        cur.execute(f"""
            DELETE FROM technical_data_daily 
            WHERE symbol IN ({symbols_placeholder})
        """, symbol_chunk)
        
        all_insert_data = []
        processed_symbols = []
        
        # Process each symbol in the chunk with optimized memory usage
        for symbol in symbol_chunk:
            try:
                if symbol not in price_df.index.get_level_values('symbol'):
                    logging.warning(f"⚠️  No price data for {symbol}, skipping")
                    continue
                
                logging.info(f"⚙️  Processing {symbol}...")
                
                # Extract data for this symbol efficiently
                symbol_data = price_df.loc[symbol].copy()
                symbol_data.reset_index(inplace=True)
                symbol_data.set_index('date', inplace=True)
                
                # Skip if insufficient data for technical analysis
                if len(symbol_data) < 200:
                    logging.warning(f"⚠️  Insufficient data for {symbol} ({len(symbol_data)} rows), skipping")
                    continue
                
                # Calculate technical indicators with error handling
                df_tech = calculate_technicals_parallel(symbol_data.copy())
                
                if df_tech.empty:
                    logging.warning(f"❌ Failed to calculate technicals for {symbol}")
                    continue
                
                # Efficiently prepare data for bulk insertion
                symbol_insert_data = []
                df_reset = df_tech.reset_index()
                
                for _, row in df_reset.iterrows():
                    # Create tuple with all required fields - order must match INSERT statement
                    record = (
                        symbol,
                        row['date'].to_pydatetime() if hasattr(row['date'], 'to_pydatetime') else row['date'],
                        sanitize_value(row.get('rsi')),
                        sanitize_value(row.get('macd')),
                        sanitize_value(row.get('macd_signal')),
                        sanitize_value(row.get('macd_hist')),
                        sanitize_value(row.get('mom')),
                        sanitize_value(row.get('roc')),
                        sanitize_value(row.get('adx')),
                        sanitize_value(row.get('atr')),
                        sanitize_value(row.get('ad')),
                        sanitize_value(row.get('cmf')),
                        sanitize_value(row.get('mfi')),
                        sanitize_value(row.get('td_sequential')),
                        sanitize_value(row.get('td_combo')),
                        sanitize_value(row.get('marketwatch')),
                        sanitize_value(row.get('dm')),
                        sanitize_value(row.get('sma_10')),
                        sanitize_value(row.get('sma_20')),
                        sanitize_value(row.get('sma_50')),
                        sanitize_value(row.get('sma_150')),
                        sanitize_value(row.get('sma_200')),
                        sanitize_value(row.get('ema_4')),
                        sanitize_value(row.get('ema_9')),
                        sanitize_value(row.get('ema_21')),
                        sanitize_value(row.get('bbands_lower')),
                        sanitize_value(row.get('bbands_middle')),
                        sanitize_value(row.get('bbands_upper')),
                        sanitize_value(row.get('pivot_high')),
                        sanitize_value(row.get('pivot_low')),
                        datetime.now()
                    )
                    symbol_insert_data.append(record)
                
                all_insert_data.extend(symbol_insert_data)
                processed_symbols.append(symbol)
                
                logging.info(f"✅ {symbol}: {len(df_tech)} technical indicators calculated ({len(symbol_insert_data)} records)")
                
                # Clean up memory for this symbol immediately
                del symbol_data, df_tech, df_reset, symbol_insert_data
                
            except Exception as e:
                logging.error(f"❌ {symbol}: Error during processing - {str(e)}")
                continue
        
        # Perform single bulk insert for entire chunk - much more efficient
        if all_insert_data:
            insert_query = """
            INSERT INTO technical_data_daily (
                symbol, date,
                rsi, macd, macd_signal, macd_hist,
                mom, roc, adx, atr, ad, cmf, mfi,
                td_sequential, td_combo, marketwatch, dm,
                sma_10, sma_20, sma_50, sma_150, sma_200,
                ema_4, ema_9, ema_21,
                bbands_lower, bbands_middle, bbands_upper,
                pivot_high, pivot_low,
                fetched_at
            ) VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                rsi = EXCLUDED.rsi,
                macd = EXCLUDED.macd,
                macd_signal = EXCLUDED.macd_signal,
                macd_hist = EXCLUDED.macd_hist,
                mom = EXCLUDED.mom,
                roc = EXCLUDED.roc,
                adx = EXCLUDED.adx,
                atr = EXCLUDED.atr,
                ad = EXCLUDED.ad,
                cmf = EXCLUDED.cmf,
                mfi = EXCLUDED.mfi,
                td_sequential = EXCLUDED.td_sequential,
                td_combo = EXCLUDED.td_combo,
                marketwatch = EXCLUDED.marketwatch,
                dm = EXCLUDED.dm,
                sma_10 = EXCLUDED.sma_10,
                sma_20 = EXCLUDED.sma_20,
                sma_50 = EXCLUDED.sma_50,
                sma_150 = EXCLUDED.sma_150,
                sma_200 = EXCLUDED.sma_200,
                ema_4 = EXCLUDED.ema_4,
                ema_9 = EXCLUDED.ema_9,
                ema_21 = EXCLUDED.ema_21,
                bbands_lower = EXCLUDED.bbands_lower,
                bbands_middle = EXCLUDED.bbands_middle,
                bbands_upper = EXCLUDED.bbands_upper,
                pivot_high = EXCLUDED.pivot_high,
                pivot_low = EXCLUDED.pivot_low,
                fetched_at = EXCLUDED.fetched_at
            """
            
            # Use large page size for maximum efficiency
            execute_values(cur, insert_query, all_insert_data, page_size=2000)
            conn.commit()
            
            logging.info(f"💾 Successfully bulk inserted {len(all_insert_data)} technical indicator records for chunk")
        
        # Clean up
        del price_df, all_insert_data
        cur.close()
        conn.close()
        
        return processed_symbols
        
    except Exception as e:
        logging.error(f"❌ Critical error in chunk processing: {str(e)}")
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()
        return []

# -------------------------------
# Main loader with optimized batch processing and parallel execution
# -------------------------------
def load_technicals_optimized(symbols):
    """Optimized technical indicators loader with batch processing and advanced parallelization"""
    total = len(symbols)
    logging.info(f"🚀 Starting ultra-optimized technical indicators calculation for {total} symbols")
    logging.info(f"📊 Performance improvements: TA-Lib C library + Batch processing + Parallel execution")
    
    # Dynamic chunk sizing based on total symbols for optimal memory usage
    if total <= 100:
        CHUNK_SIZE = 10
        MAX_WORKERS = 2
    elif total <= 500:
        CHUNK_SIZE = 20  
        MAX_WORKERS = 3
    else:
        CHUNK_SIZE = 25  # Conservative for large datasets
        MAX_WORKERS = 3
    
    logging.info(f"⚙️  Configuration: {CHUNK_SIZE} symbols per chunk, {MAX_WORKERS} parallel workers")
    
    # Split symbols into optimized chunks
    symbol_chunks = [symbols[i:i + CHUNK_SIZE] for i in range(0, len(symbols), CHUNK_SIZE)]
    total_chunks = len(symbol_chunks)
    
    db_config = get_db_config()
    all_processed_symbols = []
    all_failed_symbols = []
    
    log_mem("before parallel processing")
    start_time = time.time()
    
    # Process chunks with controlled parallelization and progress tracking
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all chunk processing tasks
        chunk_futures = {}
        
        for chunk_idx, chunk in enumerate(symbol_chunks):
            future = executor.submit(process_symbol_chunk, chunk, db_config)
            chunk_futures[future] = (chunk_idx + 1, chunk)
            
        logging.info(f"📋 Submitted {len(chunk_futures)} chunk processing tasks")
        
        # Process completed chunks as they finish with detailed progress tracking
        completed_chunks = 0
        
        for future in as_completed(chunk_futures):
            chunk_num, chunk = chunk_futures[future]
            completed_chunks += 1
            
            try:
                processed_symbols = future.result()
                all_processed_symbols.extend(processed_symbols)
                
                # Determine failed symbols in this chunk
                failed_in_chunk = [s for s in chunk if s not in processed_symbols]
                all_failed_symbols.extend(failed_in_chunk)
                
                # Calculate progress and ETA
                progress_pct = (completed_chunks / total_chunks) * 100
                elapsed_time = time.time() - start_time
                
                if completed_chunks > 1:
                    avg_time_per_chunk = elapsed_time / completed_chunks
                    remaining_chunks = total_chunks - completed_chunks
                    eta_seconds = avg_time_per_chunk * remaining_chunks
                    eta_minutes = eta_seconds / 60
                    
                    logging.info(f"📈 Progress: {completed_chunks}/{total_chunks} chunks ({progress_pct:.1f}%) | "
                                f"Chunk {chunk_num}: {len(processed_symbols)}/{len(chunk)} symbols succeeded | "
                                f"ETA: {eta_minutes:.1f} minutes")
                else:
                    logging.info(f"📊 Chunk {chunk_num}/{total_chunks} completed: "
                                f"{len(processed_symbols)}/{len(chunk)} symbols processed successfully")
                
                log_mem(f"after chunk {chunk_num}")
                
                # Force garbage collection after each chunk to maintain memory efficiency
                gc.collect()
                
            except Exception as e:
                logging.error(f"❌ Chunk {chunk_num}/{total_chunks} failed completely: {str(e)}")
                all_failed_symbols.extend(chunk)
    
    # Final performance summary
    total_time = time.time() - start_time
    successful_count = len(all_processed_symbols)
    failed_count = len(all_failed_symbols)
    
    logging.info(f"🎯 TA-Lib optimization complete!")
    logging.info(f"📊 Results: {successful_count}/{total} symbols processed successfully")
    logging.info(f"⏱️  Total time: {total_time/60:.2f} minutes ({total_time:.1f} seconds)")
    logging.info(f"⚡ Performance: {successful_count/(total_time/60):.1f} symbols/minute")
    
    if failed_count > 0:
        logging.warning(f"⚠️  {failed_count} symbols failed: {all_failed_symbols[:10]}{'...' if failed_count > 10 else ''}")
    
    log_mem("final memory usage")
    
    return total, successful_count, all_failed_symbols

def load_technicals(symbols, cur, conn):
    """Legacy function maintained for compatibility - delegates to optimized version"""
    logging.info("🔄 Using ultra-optimized batch processing with TA-Lib...")
    
    # Close the passed connection since we'll manage our own in the optimized version
    cur.close()
    conn.close()
    
    # Use the optimized approach
    total, inserted, failed = load_technicals_optimized(symbols)
    
    return total, inserted, failed

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    log_mem("startup")

    # Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Recreate technical_data_daily table
    logging.info("Recreating technical_data_daily table…")
    cur.execute("DROP TABLE IF EXISTS technical_data_daily CASCADE;")
    cur.execute("""
        CREATE TABLE technical_data_daily (
            symbol          VARCHAR(50) NOT NULL,
            date            DATE        NOT NULL,
            rsi             DOUBLE PRECISION,
            macd            DOUBLE PRECISION,
            macd_signal     DOUBLE PRECISION,
            macd_hist       DOUBLE PRECISION,
            mom             DOUBLE PRECISION,
            roc             DOUBLE PRECISION,
            adx             DOUBLE PRECISION,
            atr             DOUBLE PRECISION,
            ad              DOUBLE PRECISION,
            cmf             DOUBLE PRECISION,
            mfi             DOUBLE PRECISION,
            td_sequential   DOUBLE PRECISION,
            td_combo        DOUBLE PRECISION,
            marketwatch     DOUBLE PRECISION,
            dm              DOUBLE PRECISION,
            sma_10          DOUBLE PRECISION,
            sma_20          DOUBLE PRECISION,
            sma_50          DOUBLE PRECISION,
            sma_150         DOUBLE PRECISION,
            sma_200         DOUBLE PRECISION,
            ema_4           DOUBLE PRECISION,
            ema_9           DOUBLE PRECISION,
            ema_21          DOUBLE PRECISION,
            bbands_lower    DOUBLE PRECISION,
            bbands_middle   DOUBLE PRECISION,
            bbands_upper    DOUBLE PRECISION,
            pivot_high      DOUBLE PRECISION,
            pivot_low       DOUBLE PRECISION,
            fetched_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, date)
        );
    """)
    
    # Create indexes for performance
    cur.execute("""
        CREATE INDEX idx_technical_daily_symbol ON technical_data_daily(symbol);
        CREATE INDEX idx_technical_daily_date ON technical_data_daily(date);
    """)
    
    conn.commit()

    # Get symbols that have price data
    cur.execute("""
        SELECT DISTINCT symbol 
        FROM price_daily 
        ORDER BY symbol
    """)
    symbols = [r["symbol"] for r in cur.fetchall()]
    
    if not symbols:
        logging.error("No symbols found in price_daily table")
        sys.exit(1)
    
    # Process technical indicators
    total, inserted, failed = load_technicals(symbols, cur, conn)

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
    logging.info(f"Total symbols: {total}, Successfully processed: {inserted}, Failed: {len(failed)}")
    
    if failed:
        logging.warning(f"Failed symbols: {failed[:10]}...")  # Show first 10

    cur.close()
    conn.close()
    logging.info("All done.")
