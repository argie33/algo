#!/usr/bin/env python3 
import sys
import time
import logging
import json
import os
import gc
import psutil  # Changed from resource to psutil for cross-platform compatibility
import warnings
from datetime import datetime, timedelta
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
SCRIPT_NAME = "loadlatesttechnicalsdaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

logging.info("✅ Using Pure NumPy/Pandas Implementation - Latest Technical Indicators Loader!")

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
        results['rsi'] = rsi_fast(df['close'], period=14)
        
        # Momentum indicators
        results['mom'] = momentum_fast(df['close'], period=10)
        results['roc'] = roc_fast(df['close'], period=10)
        
        # Volume indicators
        results['atr'] = atr_fast(df['high'], df['low'], df['close'], period=14)
        results['ad'] = ad_line_fast(df['high'], df['low'], df['close'], df['volume'])
        results['cmf'] = cmf_fast(df['high'], df['low'], df['close'], df['volume'], period=20)
        results['mfi'] = mfi_fast(df['high'], df['low'], df['close'], df['volume'], period=14)
        
        return results
    
    def calculate_moving_averages():
        """Calculate all moving averages in parallel"""
        results = {}
        
        # SMAs
        for period in [10, 20, 50, 150, 200]:
            results[f'sma_{period}'] = sma_fast(df['close'], period)
        
        # EMAs
        for period in [4, 9, 21]:
            results[f'ema_{period}'] = ema_fast(df['close'], period)
        
        return results
    
    def calculate_complex_indicators():
        """Calculate indicators that require more computation"""
        results = {}
        
        # MACD
        macd_line, signal_line, histogram = macd_fast(df['close'], fast=12, slow=26, signal=9)
        results['macd'] = macd_line
        results['macd_signal'] = signal_line
        results['macd_hist'] = histogram
        
        # ADX (computationally expensive)
        results['adx'] = adx_fast(df['high'], df['low'], df['close'], period=14)
        
        # Bollinger Bands
        bb_lower, bb_middle, bb_upper = bollinger_bands_fast(df['close'], period=20, std_dev=2)
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

# -------------------------------
# Incremental technical indicators loader - identifies and processes only symbols with new price data
# -------------------------------
def identify_symbols_needing_updates(cur, lookback_days=7):
    """
    Identify symbols that have new price data and need technical indicators updated.
    Uses the same smart approach as the latest price loader - looks for deltas.
    """
    logging.info("🔍 Identifying symbols with recent price updates that need technical indicators...")
    
    # Find symbols that have price data newer than their technical indicators
    # OR symbols that have no technical indicators at all
    cur.execute("""
        WITH price_dates AS (
            SELECT symbol, MAX(date) as latest_price_date
            FROM price_daily 
            WHERE date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY symbol
        ),
        tech_dates AS (
            SELECT symbol, MAX(date) as latest_tech_date
            FROM technical_data_daily 
            GROUP BY symbol
        )
        SELECT 
            p.symbol,
            p.latest_price_date,
            COALESCE(t.latest_tech_date, '1900-01-01'::date) as latest_tech_date,
            (p.latest_price_date > COALESCE(t.latest_tech_date, '1900-01-01'::date)) as needs_update
        FROM price_dates p
        LEFT JOIN tech_dates t ON p.symbol = t.symbol
        WHERE p.latest_price_date > COALESCE(t.latest_tech_date, '1900-01-01'::date)
        ORDER BY p.symbol;
    """, (lookback_days,))
    
    results = cur.fetchall()
    symbols_to_update = []
    
    for row in results:
        symbol = row['symbol']
        latest_price = row['latest_price_date']
        latest_tech = row['latest_tech_date']
        needs_update = row['needs_update']
        
        if needs_update:
            symbols_to_update.append({
                'symbol': symbol,
                'latest_price_date': latest_price,
                'latest_tech_date': latest_tech
            })
            logging.info(f"📊 {symbol}: Price data through {latest_price}, tech data through {latest_tech} → UPDATE NEEDED")
    
    logging.info(f"🎯 Found {len(symbols_to_update)} symbols needing technical indicators updates")
    return symbols_to_update

def process_symbol_incremental(symbol_info, db_config, lookback_periods=200):
    """
    Process technical indicators for a single symbol incrementally.
    Similar to the price loader approach but for technical indicators.
    """
    symbol = symbol_info['symbol']
    latest_price_date = symbol_info['latest_price_date']
    latest_tech_date = symbol_info['latest_tech_date']
    
    try:
        # Create database connection with performance tuning
        conn = psycopg2.connect(**db_config)
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Set performance parameters (same as full loader)
        cur.execute("SET work_mem = '1GB'")
        cur.execute("SET effective_cache_size = '4GB'")
        cur.execute("SET random_page_cost = 1.0")
        cur.execute("SET seq_page_cost = 1.0")
        cur.execute("SET statement_timeout = '300s'")
        
        logging.info(f"🔄 Processing {symbol}: Need to update from {latest_tech_date} to {latest_price_date}")
        
        # Determine the date range to calculate - need enough lookback for indicators
        # But don't go crazy - limit to reasonable lookback for performance
        start_date = latest_price_date - timedelta(days=lookback_periods)
        
        # Load price data with sufficient lookback for technical indicators
        cur.execute("""
            SELECT date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol = %s
            AND date >= %s
            AND volume > 100  -- Minimal volume filter
            AND close > 0.01  -- Exclude penny stocks with weird data
            ORDER BY date ASC
        """, (symbol, start_date))
        
        price_rows = cur.fetchall()
        
        if not price_rows:
            logging.warning(f"⚠️  {symbol}: No price data found for date range {start_date} to {latest_price_date}")
            cur.close()
            conn.close()
            return False
        
        logging.info(f"📈 {symbol}: Loaded {len(price_rows)} price records for technical analysis")
        
        # Convert to DataFrame for technical analysis
        price_df = pd.DataFrame(price_rows)
        price_df['date'] = pd.to_datetime(price_df['date'])
        price_df.set_index('date', inplace=True)
        price_df.sort_index(inplace=True)
        
        # Optimize dtypes for memory and speed
        price_df = price_df.astype({
            'open': 'float32',
            'high': 'float32',
            'low': 'float32', 
            'close': 'float32',
            'volume': 'int32'
        })
        
        # Calculate technical indicators using the same optimized function
        tech_start = time.time()
        df_tech = calculate_technicals_parallel(price_df.copy())
        tech_time = time.time() - tech_start
        
        if df_tech.empty:
            logging.warning(f"❌ {symbol}: Failed to calculate technicals - empty result")
            cur.close()
            conn.close()
            return False
        
        logging.info(f"⚡ {symbol}: Calculated technical indicators in {tech_time:.2f}s")
        
        # Filter to only the NEW dates we need to insert/update
        # Only process dates that are newer than the latest technical data
        if latest_tech_date and latest_tech_date != datetime(1900, 1, 1).date():
            # Update mode - only process dates newer than existing technical data
            mask = df_tech.index.date > latest_tech_date
            df_new = df_tech[mask].copy()
            operation = "UPDATE"
        else:
            # New symbol - process all calculated data
            df_new = df_tech.copy()
            operation = "INSERT"
        
        if df_new.empty:
            logging.info(f"✅ {symbol}: No new technical data to process - already up to date")
            cur.close()
            conn.close()
            return True
        
        logging.info(f"📊 {symbol}: {operation} - Processing {len(df_new)} new technical indicator records")
        
        # Delete existing data for the date range we're updating (like price loader)
        if operation == "UPDATE":
            cur.execute("""
                DELETE FROM technical_data_daily 
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
            insert_data.append(record)
        
        insert_prep_time = time.time() - insert_start
        
        # Bulk insert
        if insert_data:
            bulk_insert_start = time.time()
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
            
            execute_values(cur, insert_query, insert_data, page_size=1000)
            conn.commit()
            
            bulk_insert_time = time.time() - bulk_insert_start
            records_per_sec = len(insert_data) / bulk_insert_time if bulk_insert_time > 0 else 0
            
            logging.info(f"🚀 {symbol}: Inserted {len(insert_data)} records in {bulk_insert_time:.2f}s ({records_per_sec:.0f} records/sec)")
        
        # Clean up
        cur.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logging.error(f"❌ {symbol}: Error during incremental processing - {str(e)}")
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()
        return False

# -------------------------------
# Main incremental loader with optimized batch processing and parallel execution
# -------------------------------
def load_latest_technicals_optimized(symbols_to_update):
    """Optimized incremental technical indicators loader with batch processing and parallel execution"""
    total = len(symbols_to_update)
    logging.info(f"🚀 Starting incremental technical indicators calculation for {total} symbols")
    
    # Dynamic chunk sizing based on total symbols for optimal performance
    if total <= 20:
        CHUNK_SIZE = 4   # Small chunks for fast processing
        MAX_WORKERS = 2
    elif total <= 100:
        CHUNK_SIZE = 8   # Medium chunks
        MAX_WORKERS = 2
    else:
        CHUNK_SIZE = 12  # Larger chunks for efficiency
        MAX_WORKERS = 2  # Conservative for database stability
    
    logging.info(f"⚙️  Configuration: {CHUNK_SIZE} symbols per chunk, {MAX_WORKERS} parallel workers")
    
    # Split symbols into optimized chunks
    symbol_chunks = [symbols_to_update[i:i + CHUNK_SIZE] for i in range(0, len(symbols_to_update), CHUNK_SIZE)]
    total_chunks = len(symbol_chunks)
    
    db_config = get_db_config()
    all_processed_symbols = []
    all_failed_symbols = []
    
    log_mem("before incremental processing")
    start_time = time.time()
    
    # Process chunks with controlled parallelization
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all chunk processing tasks
        chunk_futures = {}
        
        for chunk_idx, chunk in enumerate(symbol_chunks):
            # Process each symbol in the chunk
            for symbol_info in chunk:
                future = executor.submit(process_symbol_incremental, symbol_info, db_config)
                chunk_futures[future] = (chunk_idx + 1, symbol_info['symbol'])
        
        logging.info(f"📋 Submitted {len(chunk_futures)} symbol processing tasks")
        
        # Process completed symbols as they finish
        completed_symbols = 0
        
        for future in as_completed(chunk_futures):
            chunk_num, symbol = chunk_futures[future]
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
                    log_mem(f"after {completed_symbols} symbols")
                
            except Exception as e:
                logging.error(f"❌ Symbol {symbol} failed completely: {str(e)}")
                all_failed_symbols.append(symbol)
    
    # Final performance summary
    total_time = time.time() - start_time
    successful_count = len(all_processed_symbols)
    failed_count = len(all_failed_symbols)
    
    logging.info(f"🎯 Incremental technical indicators update complete!")
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
    
    log_mem("final memory usage")
    
    return total, successful_count, all_failed_symbols

# -------------------------------
# Entrypoint
# -------------------------------
def main():
    """Main function with proper error handling for ECS task completion"""
    exit_code = 0
    conn = None
    cur = None
    
    try:
        log_mem("startup")
        logging.info(f"🚀 Starting {SCRIPT_NAME}")

        # Connect to DB
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Identify symbols that need technical indicators updates
        symbols_to_update = identify_symbols_needing_updates(cur, lookback_days=7)
        
        if not symbols_to_update:
            logging.info("✅ No symbols need technical indicators updates - all up to date!")
            
            # Record last run even if no work was needed
            cur.execute("""
              INSERT INTO last_updated (script_name, last_run)
              VALUES (%s, NOW())
              ON CONFLICT (script_name) DO UPDATE
                SET last_run = EXCLUDED.last_run;
            """, (SCRIPT_NAME,))
            conn.commit()
            
            logging.info("🏁 Latest technical indicators loader completed - no updates needed")
            return exit_code

        logging.info(f"📊 Found {len(symbols_to_update)} symbols needing technical indicators updates")

        # Process technical indicators incrementally
        total, inserted, failed = load_latest_technicals_optimized(symbols_to_update)

        # Ensure cursor is still valid after processing
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
        logging.info(f"📈 Total symbols: {total}, Successfully processed: {inserted}, Failed: {len(failed)}")
        
        if failed:
            logging.warning(f"⚠️ Failed symbols ({len(failed)}): {failed[:10]}...")
            if len(failed) > len(symbols_to_update) * 0.5:  # More than 50% failed
                logging.error(f"❌ Too many failures ({len(failed)}/{total}), marking as failed")
                exit_code = 1
            else:
                logging.info(f"✅ Acceptable failure rate ({len(failed)}/{total})")

        logging.info("✅ Latest technical indicators processing completed successfully")
        
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