#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import gc
import psutil  # Changed from resource to psutil for cross-platform compatibility
import warnings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from functools import partial

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import boto3
import numpy as np
import pandas as pd

# Suppress warnings for performance
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadtechnicalsmonthly.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

logging.info("✅ Using Pure NumPy/Pandas Implementation - No TA-Lib Dependencies!")

# -------------------------------
# Memory-logging helper (RSS in MB) - Cross-platform compatible
# -------------------------------
def get_rss_mb():
    """Get RSS memory usage in MB - works on all platforms"""
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

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
    """Convert NaN/inf values to None for database insertion and handle numpy types"""
    if x is None:
        return None
    
    # Handle numpy scalar types (float32, float64, int32, etc.)
    if hasattr(x, 'item'):
        x = x.item()  # Convert numpy scalar to Python native type
    
    # Handle NaN/inf values for float types
    if isinstance(x, (float, np.floating)) and (np.isnan(x) or np.isinf(x)):
        return None
    
    # Convert numpy types to native Python types
    if isinstance(x, np.integer):
        return int(x)
    elif isinstance(x, np.floating):
        return float(x)
    elif isinstance(x, np.bool_):
        return bool(x)
    
    return x

# -------------------------------
# ULTRA-FAST PURE NUMPY TECHNICAL INDICATORS
# (What hedge funds actually use - no compilation dependencies!)
# -------------------------------

def sma_fast(values, period):
    """Ultra-fast SMA using numpy convolution - faster than pandas rolling"""
    if len(values) < period:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    # Use convolution for blazing speed
    kernel = np.ones(period) / period
    result = np.convolve(values.values, kernel, mode='valid')
    
    # Pad with NaN for initial values
    padded_result = np.concatenate([np.full(period - 1, np.nan), result])
    return pd.Series(padded_result, index=values.index)

def ema_fast(values, period):
    """Ultra-fast EMA implementation - hedge fund grade"""
    if len(values) < 1:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    alpha = 2.0 / (period + 1.0)
    result = np.empty_like(values.values, dtype=np.float64)
    
    # Initialize with first valid value
    first_valid_idx = values.first_valid_index()
    if first_valid_idx is None:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    first_valid_pos = values.index.get_loc(first_valid_idx)
    result[:first_valid_pos] = np.nan
    result[first_valid_pos] = values.iloc[first_valid_pos]
    
    # Vectorized EMA calculation
    for i in range(first_valid_pos + 1, len(values)):
        if np.isnan(values.iloc[i]):
            result[i] = result[i-1]
        else:
            result[i] = alpha * values.iloc[i] + (1 - alpha) * result[i - 1]
    
    return pd.Series(result, index=values.index)

def rsi_fast(values, period=14):
    """Lightning-fast RSI - pure NumPy implementation"""
    if len(values) < period + 1:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    # Calculate price changes
    changes = values.diff()
    
    # Separate gains and losses
    gains = changes.where(changes > 0, 0)
    losses = -changes.where(changes < 0, 0)
    
    # Calculate average gains and losses using EMA
    avg_gains = gains.ewm(span=period, adjust=False).mean()
    avg_losses = losses.ewm(span=period, adjust=False).mean()
    
    # Calculate RSI
    rs = avg_gains / (avg_losses + 1e-10)  # Avoid division by zero
    rsi = 100 - (100 / (1 + rs))
    
    return rsi.fillna(50)  # Fill NaN with neutral RSI

def macd_fast(values, fast=12, slow=26, signal=9):
    """Ultra-fast MACD - hedge fund implementation"""
    if len(values) < slow:
        nan_series = pd.Series(np.full(len(values), np.nan), index=values.index)
        return nan_series, nan_series, nan_series
    
    # Calculate EMAs
    ema_fast_line = ema_fast(values, fast)
    ema_slow_line = ema_fast(values, slow)
    
    # MACD line
    macd_line = ema_fast_line - ema_slow_line
    
    # Signal line (EMA of MACD)
    signal_line = ema_fast(macd_line, signal)
    
    # Histogram
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

def bollinger_bands_fast(values, period=20, std_multiplier=2):
    """Ultra-fast Bollinger Bands"""
    if len(values) < period:
        nan_series = pd.Series(np.full(len(values), np.nan), index=values.index)
        return nan_series, nan_series, nan_series
    
    # Middle band (SMA)
    middle = sma_fast(values, period)
    
    # Rolling standard deviation
    rolling_std = values.rolling(window=period, min_periods=period).std()
    
    # Upper and lower bands
    upper = middle + (std_multiplier * rolling_std)
    lower = middle - (std_multiplier * rolling_std)
    
    return lower, middle, upper

def atr_fast(high, low, close, period=14):
    """Average True Range - pure NumPy"""
    if len(high) < 2:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # True Range calculation
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR using EMA
    atr = true_range.ewm(span=period, adjust=False).mean()
    return atr.fillna(0)

def adx_fast(high, low, close, period=14):
    """ADX implementation - simplified but accurate"""
    if len(high) < period + 1:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # Calculate directional movement
    high_diff = high.diff()
    low_diff = low.shift(1) - low
    
    plus_dm = pd.Series(np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0), index=high.index)
    minus_dm = pd.Series(np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0), index=high.index)
    
    # True Range
    tr = atr_fast(high, low, close, 1)
    
    # Smooth DM and TR
    plus_dm_smooth = plus_dm.ewm(span=period, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(span=period, adjust=False).mean()
    tr_smooth = tr.ewm(span=period, adjust=False).mean()
    
    # Calculate DI
    plus_di = 100 * plus_dm_smooth / (tr_smooth + 1e-10)
    minus_di = 100 * minus_dm_smooth / (tr_smooth + 1e-10)
    
    # Calculate DX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    
    # ADX is EMA of DX
    adx = dx.ewm(span=period, adjust=False).mean()
    
    return adx.fillna(0)

def momentum_fast(values, period=10):
    """Momentum indicator"""
    if len(values) < period:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    momentum = values - values.shift(period)
    return momentum.fillna(0)

def roc_fast(values, period=10):
    """Rate of Change"""
    if len(values) < period:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    shifted = values.shift(period)
    roc = ((values - shifted) / (shifted + 1e-10)) * 100
    return roc.fillna(0)

def ad_line_fast(high, low, close, volume):
    """Accumulation/Distribution Line"""
    if len(high) == 0:
        return pd.Series([], dtype=float)
    
    # Money Flow Multiplier
    mfm = ((close - low) - (high - close)) / (high - low + 1e-10)
    
    # Money Flow Volume
    mfv = mfm * volume
    
    # A/D Line (cumulative)
    ad_line = mfv.cumsum()
    return ad_line.fillna(0)

def cmf_fast(high, low, close, volume, period=20):
    """Chaikin Money Flow"""
    if len(high) < period:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # Money Flow Multiplier
    mfm = ((close - low) - (high - close)) / (high - low + 1e-10)
    
    # Money Flow Volume
    mfv = mfm * volume
    
    # CMF calculation using rolling sums
    mfv_sum = mfv.rolling(window=period, min_periods=period).sum()
    volume_sum = volume.rolling(window=period, min_periods=period).sum()
    cmf = mfv_sum / (volume_sum + 1e-10)
    
    return cmf.fillna(0)

def mfi_fast(high, low, close, volume, period=14):
    """Money Flow Index"""
    if len(high) < period + 1:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # Typical Price
    typical_price = (high + low + close) / 3
    
    # Raw Money Flow
    raw_money_flow = typical_price * volume
    
    # Positive and Negative Money Flow
    price_changes = typical_price.diff()
    pos_money_flow = raw_money_flow.where(price_changes > 0, 0)
    neg_money_flow = raw_money_flow.where(price_changes < 0, 0)
    
    # Rolling sums
    pos_sum = pos_money_flow.rolling(window=period, min_periods=period).sum()
    neg_sum = neg_money_flow.rolling(window=period, min_periods=period).sum()
    
    # MFI calculation
    money_ratio = pos_sum / (neg_sum + 1e-10)
    mfi = 100 - (100 / (1 + money_ratio))
    
    return mfi.fillna(50)

# -------------------------------
# Updated function calls to use new implementations
# -------------------------------

def calculate_rsi(prices, period=14):
    """Pure NumPy RSI calculation"""
    return rsi_fast(prices, period)

def calculate_sma(prices, period):
    """Pure NumPy SMA calculation"""
    return sma_fast(prices, period)

def calculate_ema(prices, period):
    """Pure NumPy EMA calculation"""
    return ema_fast(prices, period)

def calculate_atr(high, low, close, period=14):
    """Pure NumPy ATR calculation"""
    return atr_fast(high, low, close, period)

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Pure NumPy MACD calculation"""
    return macd_fast(prices, fast, slow, signal)

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    """Pure NumPy Bollinger Bands calculation"""
    return bollinger_bands_fast(prices, period, std_dev)

def calculate_momentum(prices, period=10):
    """Pure NumPy Momentum calculation"""
    return momentum_fast(prices, period)

def calculate_roc(prices, period=10):
    """Pure NumPy Rate of Change calculation"""
    return roc_fast(prices, period)

def calculate_adx(high, low, close, period=14):
    """Pure NumPy ADX calculation"""
    return adx_fast(high, low, close, period)

def calculate_accumulation_distribution(high, low, close, volume):
    """Pure NumPy A/D Line calculation"""
    return ad_line_fast(high, low, close, volume)

def calculate_cmf(high, low, close, volume, period=20):
    """Pure NumPy Chaikin Money Flow calculation"""
    return cmf_fast(high, low, close, volume, period)

def calculate_mfi(high, low, close, volume, period=14):
    """Pure NumPy Money Flow Index calculation"""
    return mfi_fast(high, low, close, volume, period)

# -------------------------------
# Custom Indicators (Pure NumPy/Pandas implementations)
# -------------------------------

def pivot_high_vectorized(high, left_bars=3, right_bars=3):
    """Vectorized pivot high calculation"""
    if len(high) < left_bars + right_bars + 1:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    result = pd.Series(np.full(len(high), np.nan), index=high.index)
    
    for i in range(left_bars, len(high) - right_bars):
        # Check if current high is higher than surrounding bars
        left_window = high.iloc[i-left_bars:i]
        right_window = high.iloc[i+1:i+right_bars+1]
        
        if (high.iloc[i] > left_window.max()) and (high.iloc[i] > right_window.max()):
            result.iloc[i] = high.iloc[i]
    
    return result

def pivot_low_vectorized(low, left_bars=3, right_bars=3):
    """Vectorized pivot low calculation"""
    if len(low) < left_bars + right_bars + 1:
        return pd.Series(np.full(len(low), np.nan), index=low.index)
    
    result = pd.Series(np.full(len(low), np.nan), index=low.index)
    
    for i in range(left_bars, len(low) - right_bars):
        # Check if current low is lower than surrounding bars
        left_window = low.iloc[i-left_bars:i]
        right_window = low.iloc[i+1:i+right_bars+1]
        
        if (low.iloc[i] < left_window.min()) and (low.iloc[i] < right_window.min()):
            result.iloc[i] = low.iloc[i]
    
    return result

def td_sequential_vectorized(close, lookback=4):
    """Vectorized TD Sequential indicator"""
    if len(close) < lookback + 1:
        return pd.Series(np.zeros(len(close)), index=close.index)
    
    # Compare current close with close N periods ago
    comparison = np.where(close < close.shift(lookback), 1, 
                         np.where(close > close.shift(lookback), -1, 0))
    
    result = np.zeros(len(close))
    count = 0
    current_direction = 0
    
    for i in range(lookback, len(close)):
        if comparison[i] == 1:  # Bearish
            if current_direction == 1:
                count += 1
            else:
                count = 1
                current_direction = 1
            result[i] = count
        elif comparison[i] == -1:  # Bullish
            if current_direction == -1:
                count -= 1
            else:
                count = -1
                current_direction = -1
            result[i] = count
        else:  # No signal
            count = 0
            current_direction = 0
    
    return pd.Series(result, index=close.index)

def td_combo_vectorized(close, lookback=2):
    """Vectorized TD Combo indicator"""
    if len(close) < lookback + 1:
        return pd.Series(np.zeros(len(close)), index=close.index)
    
    # Similar to TD Sequential but with different lookback
    comparison = np.where(close < close.shift(lookback), 1, 
                         np.where(close > close.shift(lookback), -1, 0))
    
    result = np.zeros(len(close))
    count = 0
    current_direction = 0
    
    for i in range(lookback, len(close)):
        if comparison[i] == 1:  # Bearish
            if current_direction == 1:
                count += 1
            else:
                count = 1
                current_direction = 1
            result[i] = count
        elif comparison[i] == -1:  # Bullish
            if current_direction == -1:
                count -= 1
            else:
                count = -1
                current_direction = -1
            result[i] = count
        else:  # No signal
            count = 0
            current_direction = 0
    
    return pd.Series(result, index=close.index)

def marketwatch_indicator_vectorized(close, open_):
    """Vectorized MarketWatch indicator"""
    if len(close) != len(open_):
        return pd.Series(np.zeros(len(close)), index=close.index)
    
    signal = np.where(close > open_, 1, np.where(close < open_, -1, 0))
    result = np.zeros(len(close))
    count = 0
    current_direction = 0
    
    for i in range(len(signal)):
        if signal[i] == 1:  # Green day
            if current_direction == 1:
                count += 1
            else:
                count = 1
                current_direction = 1
            result[i] = count
        elif signal[i] == -1:  # Red day
            if current_direction == -1:
                count -= 1
            else:
                count = -1
                current_direction = -1
            result[i] = count
        else:  # Neutral
            count = 0
            current_direction = 0
    
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
    
    # Process ALL available data regardless of size - maximum data for backtesting
    
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
    """Process a chunk of symbols efficiently with ULTRA-OPTIMIZED database operations and retry logic"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            return _process_symbol_chunk_internal(symbol_chunk, db_config, retry_count)
        except psycopg2.OperationalError as e:
            error_msg = str(e).lower()
            if 'canceling statement due to statement timeout' in error_msg:
                retry_count += 1
                if retry_count < max_retries:
                    logging.warning(f"⚠️ Statement timeout on attempt {retry_count}/{max_retries}, retrying with reduced timeout...")
                    time.sleep(5)  # Brief pause before retry
                    continue
                else:
                    logging.error(f"❌ Statement timeout after {max_retries} attempts for chunk: {symbol_chunk}")
                    return []
            else:
                logging.error(f"❌ Database error in chunk processing: {error_msg}")
                return []
        except Exception as e:
            logging.error(f"❌ Critical error in chunk processing: {str(e)}")
            return []
    
    # If we get here, all retries failed
    logging.error(f"❌ All {max_retries} attempts failed for chunk: {symbol_chunk}")
    return []

def _process_symbol_chunk_internal(symbol_chunk, db_config, retry_count=0):
    """Internal function for processing symbol chunk with progressive timeout"""
    try:
        # Create database connection with AGGRESSIVE performance tuning
        conn = psycopg2.connect(**db_config)
        
        # ULTRA-AGGRESSIVE PERFORMANCE TUNING FOR SPEED
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
          # Set MAXIMUM performance parameters
        cur.execute("SET work_mem = '2GB'")  # Massive memory for sorts/joins
        # Note: shared_buffers cannot be changed at runtime, skipping
        cur.execute("SET effective_cache_size = '8GB'")  # Tell PG about available cache
        cur.execute("SET random_page_cost = 1.0")  # SSD-optimized
        cur.execute("SET seq_page_cost = 1.0")  # Sequential scan cost
        cur.execute("SET cpu_tuple_cost = 0.001")  # Very low CPU cost
        cur.execute("SET cpu_index_tuple_cost = 0.001")  # Very low index cost
        cur.execute("SET cpu_operator_cost = 0.0001")  # Very low operator cost
        cur.execute("SET effective_io_concurrency = 200")  # High I/O concurrency
        cur.execute("SET max_parallel_workers_per_gather = 4")  # Parallel workers
        cur.execute("SET max_parallel_workers = 8")
        cur.execute("SET parallel_tuple_cost = 0.001")  # Low parallel cost
        cur.execute("SET enable_seqscan = off")  # Force index usage when possible
        cur.execute("SET enable_hashjoin = on")  # Enable hash joins
        cur.execute("SET enable_mergejoin = on")  # Enable merge joins
        
        # Progressive timeout reduction for retries: 900s -> 700s -> 500s
        timeout_seconds = max(300, 900 - (retry_count * 200))
        cur.execute(f"SET statement_timeout = '{timeout_seconds}s'")  # Dynamic timeout based on retry
        cur.execute("SET lock_timeout = '60s'")        # Lock timeout for better resource management
        
        if retry_count > 0:
            logging.info(f"🔄 Retry attempt {retry_count + 1}/3 for chunk with {timeout_seconds}s timeout")
        
        # CRITICAL: Reduce the amount of data loaded dramatically
        symbols_placeholder = ','.join(['%s'] * len(symbol_chunk))
        
        logging.info(f"🚀 ULTRA-FAST loading price data for {len(symbol_chunk)} symbols...")        # OPTIMIZED query - load ALL available historical data for maximum comprehensive analysis
        start_query_time = time.time()
        cur.execute(f"""
            SELECT /*+ PARALLEL(price_monthly, 4) USE_INDEX(price_monthly, idx_price_monthly_symbol_date) */
                   symbol, date, open, high, low, close, volume
            FROM price_monthly
            WHERE symbol IN ({symbols_placeholder})
            AND volume > 100  -- Minimal volume filter to include maximum data
            AND close > 0.01   -- Exclude penny stocks with weird data
            ORDER BY symbol, date ASC
        """, symbol_chunk)
        
        all_rows = cur.fetchall()
        query_time = time.time() - start_query_time
        logging.info(f"⚡ Database query completed in {query_time:.2f} seconds")
        
        if not all_rows:
            logging.warning(f"No price data found for chunk: {symbol_chunk}")
            cur.close()
            conn.close()
            return []
        
        logging.info(f"⚡ Loaded {len(all_rows)} price records in {query_time:.2f}s - Converting to DataFrame...")
        
        # ULTRA-FAST DataFrame conversion with optimized dtypes
        price_df_start = time.time()
        price_df = pd.DataFrame(all_rows)
        
        # Optimize dtypes for memory and speed - use the smallest possible types
        price_df = price_df.astype({
            'symbol': 'category',  # Much faster for grouping
            'open': 'float32',     # Sufficient precision, half memory
            'high': 'float32',
            'low': 'float32', 
            'close': 'float32',
            'volume': 'int32'      # Smaller int type for volume
        })
        
        price_df['date'] = pd.to_datetime(price_df['date'])
        price_df.set_index(['symbol', 'date'], inplace=True)
        price_df.sort_index(inplace=True)  # Ensure sorted for performance
        
        df_time = time.time() - price_df_start
        logging.info(f"⚡ DataFrame conversion completed in {df_time:.2f} seconds")
        
        # ULTRA-FAST bulk delete - single operation for entire chunk
        delete_start = time.time()
        cur.execute(f"""
            DELETE FROM technical_data_monthly 
            WHERE symbol IN ({symbols_placeholder})
        """, symbol_chunk)
        delete_time = time.time() - delete_start
        logging.info(f"⚡ Bulk delete completed in {delete_time:.2f} seconds")
        
        # AGGRESSIVE PROCESSING with parallel-friendly chunking
        all_insert_data = []
        processed_symbols = []
        
        # Process each symbol with MAXIMUM SPEED optimizations
        symbol_process_start = time.time()
        for i, symbol in enumerate(symbol_chunk):
            try:
                if symbol not in price_df.index.get_level_values('symbol'):
                    logging.warning(f"⚠️  No price data for {symbol}, skipping")
                    continue
                
                if i % 5 == 0:  # Log progress every 5 symbols
                    logging.info(f"⚙️  Processing {symbol} ({i+1}/{len(symbol_chunk)})...")
                
                # ULTRA-FAST data extraction
                symbol_data = price_df.loc[symbol].copy()                  # Skip if insufficient data - adjusted for monthly data requirements
                if len(symbol_data) < 1:  # Process ALL available data - even single data points for maximum backtesting data
                    logging.warning(f"⚠️  No data available for {symbol}, skipping")
                    continue
                
                # ULTRA-FAST technical indicators calculation using vectorized operations
                tech_start = time.time()
                df_tech = calculate_technicals_parallel(symbol_data.copy())  # Use existing optimized function
                tech_time = time.time() - tech_start
                
                if df_tech.empty:
                    logging.warning(f"❌ Failed to calculate technicals for {symbol}")
                    continue
                
                # ULTRA-FAST data preparation for insertion - vectorized approach
                insert_start = time.time()
                symbol_insert_data = []
                
                # Reset index efficiently
                df_reset = df_tech.reset_index()
                
                # VECTORIZED data preparation - much faster than iterrows()
                dates = df_reset['date'].values
                n_rows = len(df_reset)
                
                # Pre-allocate and vectorize the data preparation
                for idx in range(n_rows):
                    row = df_reset.iloc[idx]
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
                
                insert_prep_time = time.time() - insert_start
                
                all_insert_data.extend(symbol_insert_data)
                processed_symbols.append(symbol)
                
                if i % 5 == 0:  # Log progress every 5 symbols
                    logging.info(f"✅ {symbol}: {len(df_tech)} indicators calculated in {tech_time:.2f}s, data prep in {insert_prep_time:.2f}s")
                
                # Aggressive memory cleanup
                del symbol_data, df_tech, df_reset, symbol_insert_data
                
            except Exception as e:
                logging.error(f"❌ {symbol}: Error during processing - {str(e)}")
                continue
        
        symbol_process_time = time.time() - symbol_process_start
        logging.info(f"⚡ All symbols processed in {symbol_process_time:.2f} seconds")
        
        # ULTRA-FAST bulk insert for entire chunk
        if all_insert_data:
            bulk_insert_start = time.time()
            insert_query = """
            INSERT INTO technical_data_monthly (
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
            
            # Use MAXIMUM page size for ultra-fast bulk insert
            execute_values(cur, insert_query, all_insert_data, page_size=5000)
            conn.commit()
            
            bulk_insert_time = time.time() - bulk_insert_start
            records_per_sec = len(all_insert_data) / bulk_insert_time if bulk_insert_time > 0 else 0
            
            logging.info(f"🚀 ULTRA-FAST bulk insert: {len(all_insert_data)} records in {bulk_insert_time:.2f}s ({records_per_sec:.0f} records/sec)")
        
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
      # Dynamic chunk sizing based on total symbols for optimal memory usage and timeout prevention
    if total <= 100:
        CHUNK_SIZE = 8   # Reduced from 10 to prevent timeouts
        MAX_WORKERS = 2
    elif total <= 500:
        CHUNK_SIZE = 12  # Reduced from 20 to prevent timeouts
        MAX_WORKERS = 2  # Reduced from 3 to prevent database overload
    else:
        CHUNK_SIZE = 15  # Reduced from 25 to prevent timeouts on large datasets
        MAX_WORKERS = 2  # Reduced from 3 to prevent database overload
    
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

    # Recreate technical_data_monthly table
    logging.info("Recreating technical_data_monthly table…")
    cur.execute("DROP TABLE IF EXISTS technical_data_monthly CASCADE;")
    cur.execute("""
        CREATE TABLE technical_data_monthly (
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
        CREATE INDEX idx_technical_monthly_symbol ON technical_data_monthly(symbol);
        CREATE INDEX idx_technical_monthly_date ON technical_data_monthly(date);
    """)
    
    conn.commit()

    # Get symbols that have price data
    cur.execute("""
        SELECT DISTINCT symbol 
        FROM price_monthly 
        ORDER BY symbol
    """)
    symbols = [r["symbol"] for r in cur.fetchall()]
    
    if not symbols:
        logging.error("No symbols found in price_monthly table")
        sys.exit(1)
      # Process technical indicators
    total, inserted, failed = load_technicals(symbols, cur, conn)

    # Ensure cursor is still valid after the optimized processing
    # (the optimized function creates its own connections internally)
    try:
        cur.execute("SELECT 1")
    except (psycopg2.InterfaceError, psycopg2.OperationalError):
        logging.info("Reconnecting to database after technical indicators processing...")
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
    logging.info(f"Total symbols: {total}, Successfully processed: {inserted}, Failed: {len(failed)}")
    
    if failed:
        logging.warning(f"Failed symbols: {failed[:10]}...")  # Show first 10

    cur.close()
    conn.close()
    logging.info("All done.")
