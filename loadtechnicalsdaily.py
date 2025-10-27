#!/usr/bin/env python3  
# Daily technicals loader - deployment test v13 - trigger workflow with fixed secrets
# Updated 2025-07-15: Ready for production deployment with optimized technical indicators
# Deployment trigger: Enhanced technical loading workflow - Database population v2
import sys
import time
import logging
from datetime import datetime
import json
import os
import concurrent.futures
from functools import partial
import gc
import os

import numpy as np
import numpy

# ───────────────────────────────────────────────────────────────────
# Monkey-patch numpy so that "from numpy import NaN" in pandas_ta will succeed 
numpy.NaN = numpy.nan
np.NaN    = np.nan
# ───────────────────────────────────────────────────────────────────

# Memory optimization for small ECS tasks - production ready
MEMORY_THRESHOLD_MB = int(os.environ.get('MEMORY_THRESHOLD_MB', '400'))  # Warning threshold
ECS_MEMORY_MB = int(os.environ.get('ECS_MEMORY_MB', '512'))  # Total ECS memory
USE_ULTRA_LOW_MEMORY = os.environ.get('ULTRA_LOW_MEMORY', 'false').lower() == 'true'

import boto3
import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values

import pandas as pd

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = os.path.basename(__file__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
    stream=sys.stdout
)

# Optimized for ECS - minimal resource usage
MAX_WORKERS = 1  # Single worker to prevent memory issues on 512MB tasks
BATCH_SIZE = 25  # Smaller batches for memory efficiency
DB_POOL_MIN = 1
DB_POOL_MAX = 2  # Minimal connections for 512MB memory constraint

def get_db_config():
    """
    Fetch database config from local environment variables first, then fall back to Secrets Manager.
    For local dev: DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
    For AWS: DB_SECRET_ARN
    """
    # Try local environment first (for local development)
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = int(os.environ.get("DB_PORT", 5432))
    db_user = os.environ.get("DB_USER", "postgres")
    db_password = os.environ.get("DB_PASSWORD", "password")
    db_name = os.environ.get("DB_NAME", "stocks")

    if db_host and db_host != "localhost":
        return (db_user, db_password, db_host, db_port, db_name)

    # Fall back to AWS Secrets Manager for production
    db_secret_arn = os.environ.get("DB_SECRET_ARN")
    if db_secret_arn:
        try:
            client = boto3.client("secretsmanager")
            resp = client.get_secret_value(SecretId=db_secret_arn)
            sec = json.loads(resp["SecretString"])
            return (
                sec["username"],
                sec["password"],
                sec["host"],
                int(sec["port"]),
                sec["dbname"]
            )
        except Exception as e:
            logging.warning(f"Failed to fetch from AWS Secrets Manager: {e}, using local defaults")

    # Use local defaults as final fallback
    return (db_user, db_password, db_host, db_port, db_name)

def sanitize_value(x):
    if isinstance(x, float) and np.isnan(x):
        return None
    return x

# Fast native implementations of technical indicators
def fast_rsi(close, period=14):
    """Fast RSI calculation using numpy"""
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def fast_macd(close, fast=12, slow=26, signal=9):
    """Fast MACD calculation"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist

def fast_sma(close, period):
    """Fast SMA calculation"""
    return close.rolling(window=period).mean()

def fast_ema(close, period):
    """Fast EMA calculation"""
    return close.ewm(span=period, adjust=False).mean()

def fast_atr(high, low, close, period=14):
    """Fast ATR calculation"""
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

def fast_ad(high, low, close, volume):
    """Fast Accumulation/Distribution calculation"""
    clv = ((close - low) - (high - close)) / (high - low)
    clv = clv.replace([np.inf, -np.inf], 0)
    ad = (clv * volume).cumsum()
    return ad

def fast_mfi(high, low, close, volume, period=14):
    """Fast Money Flow Index calculation"""
    typical_price = (high + low + close) / 3
    money_flow = typical_price * volume
    
    positive_flow = money_flow.where(typical_price > typical_price.shift(1), 0).rolling(window=period).sum()
    negative_flow = money_flow.where(typical_price < typical_price.shift(1), 0).rolling(window=period).sum()
    
    mfi = 100 - (100 / (1 + positive_flow / negative_flow))
    return mfi

def fast_bbands(close, period=20, std_dev=2):
    """Fast Bollinger Bands calculation"""
    sma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return lower, sma, upper

def fast_adx(high, low, close, period=14):
    """Fast ADX calculation - production optimized"""
    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Directional Movement
    dm_plus = high - high.shift(1)
    dm_minus = low.shift(1) - low
    
    dm_plus = dm_plus.where((dm_plus > dm_minus) & (dm_plus > 0), 0)
    dm_minus = dm_minus.where((dm_minus > dm_plus) & (dm_minus > 0), 0)
    
    # Smoothed values
    tr_smooth = tr.rolling(window=period).mean()
    dm_plus_smooth = dm_plus.rolling(window=period).mean()
    dm_minus_smooth = dm_minus.rolling(window=period).mean()
    
    # DI values
    plus_di = 100 * (dm_plus_smooth / tr_smooth)
    minus_di = 100 * (dm_minus_smooth / tr_smooth)
    
    # DX and ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    
    return adx, plus_di, minus_di

def pivot_high_vectorized(df, left_bars=3, right_bars=3):
    """
    Calculate pivot high values - Pine Script style pivothigh()
    Returns the hypothetical pivot high levels that persist until a new pivot is formed
    """
    high_series = df['high'].values
    n = len(high_series)
    pivot_highs = np.full(n, np.nan)
    
    # Find all pivot high points
    for i in range(left_bars, n - right_bars):
        # Check if current bar is highest in the window
        left_max = np.max(high_series[i-left_bars:i])
        right_max = np.max(high_series[i+1:i+right_bars+1])
        current = high_series[i]
        
        if current > left_max and current > right_max:
            pivot_highs[i] = current
    
    # Forward fill the pivot values (persist until new pivot)
    last_pivot = np.nan
    for i in range(n):
        if not np.isnan(pivot_highs[i]):
            last_pivot = pivot_highs[i]
        pivot_highs[i] = last_pivot
    
    return pd.Series(pivot_highs, index=df.index)

def pivot_low_vectorized(df, left_bars=3, right_bars=3):
    """
    Calculate pivot low values - Pine Script style pivotlow()
    Returns the hypothetical pivot low levels that persist until a new pivot is formed
    """
    low_series = df['low'].values
    n = len(low_series)
    pivot_lows = np.full(n, np.nan)
    
    # Find all pivot low points
    for i in range(left_bars, n - right_bars):
        # Check if current bar is lowest in the window
        left_min = np.min(low_series[i-left_bars:i])
        right_min = np.min(low_series[i+1:i+right_bars+1])
        current = low_series[i]
        
        if current < left_min and current < right_min:
            pivot_lows[i] = current
    
    # Forward fill the pivot values (persist until new pivot)
    last_pivot = np.nan
    for i in range(n):
        if not np.isnan(pivot_lows[i]):
            last_pivot = pivot_lows[i]
        pivot_lows[i] = last_pivot
    
    return pd.Series(pivot_lows, index=df.index)

def pivot_high_triggered_vectorized(df, left_bars=3, right_bars=3):
    """
    Calculate pivot high triggers - returns values only when price crosses above pivot high
    This represents when a pivot high breakout signal is actually generated
    """
    high_series = df['high'].values
    n = len(high_series)
    pivot_highs = np.full(n, np.nan)
    
    # Find all pivot high points
    for i in range(left_bars, n - right_bars):
        # Check if current bar is highest in the window
        left_max = np.max(high_series[i-left_bars:i])
        right_max = np.max(high_series[i+1:i+right_bars+1])
        current = high_series[i]
        
        if current > left_max and current > right_max:
            pivot_highs[i] = current
    
    # Forward fill the pivot values (persist until new pivot)
    last_pivot = np.nan
    for i in range(n):
        if not np.isnan(pivot_highs[i]):
            last_pivot = pivot_highs[i]
        pivot_highs[i] = last_pivot
    
    # Now check for breakouts - only return value on the FIRST bar where price crosses above pivot
    triggered = np.full(n, np.nan)
    last_triggered_pivot = np.nan  # Track the last pivot that was triggered
    
    for i in range(1, n):
        if not np.isnan(pivot_highs[i-1]) and high_series[i] > pivot_highs[i-1]:
            # Only trigger if this is a new pivot level (not the same one we already triggered)
            if pivot_highs[i-1] != last_triggered_pivot:
                triggered[i] = pivot_highs[i-1]  # Return the pivot level that was broken
                last_triggered_pivot = pivot_highs[i-1]  # Mark this pivot as triggered
    
    return pd.Series(triggered, index=df.index)

def pivot_low_triggered_vectorized(df, left_bars=3, right_bars=3):
    """
    Calculate pivot low triggers - returns values only when price crosses below pivot low
    This represents when a pivot low breakdown signal is actually generated
    """
    low_series = df['low'].values
    n = len(low_series)
    pivot_lows = np.full(n, np.nan)
    
    # Find all pivot low points
    for i in range(left_bars, n - right_bars):
        # Check if current bar is lowest in the window
        left_min = np.min(low_series[i-left_bars:i])
        right_min = np.min(low_series[i+1:i+right_bars+1])
        current = low_series[i]
        
        if current < left_min and current < right_min:
            pivot_lows[i] = current
    
    # Forward fill the pivot values (persist until new pivot)
    last_pivot = np.nan
    for i in range(n):
        if not np.isnan(pivot_lows[i]):
            last_pivot = pivot_lows[i]
        pivot_lows[i] = last_pivot
    
    # Now check for breakdowns - only return value on the FIRST bar where price crosses below pivot
    triggered = np.full(n, np.nan)
    last_triggered_pivot = np.nan  # Track the last pivot that was triggered
    
    for i in range(1, n):
        if not np.isnan(pivot_lows[i-1]) and low_series[i] < pivot_lows[i-1]:
            # Only trigger if this is a new pivot level (not the same one we already triggered)
            if pivot_lows[i-1] != last_triggered_pivot:
                triggered[i] = pivot_lows[i-1]  # Return the pivot level that was broken
                last_triggered_pivot = pivot_lows[i-1]  # Mark this pivot as triggered
    
    return pd.Series(triggered, index=df.index)

def td_sequential(close, lookback=4):
    count = np.zeros(len(close), dtype=np.float64)
    close_values = close.values  # Extract values once for better performance
    
    for i in range(lookback, len(close)):
        if close_values[i] < close_values[i-lookback]:
            count[i] = count[i-1]+1 if count[i-1]>0 else 1
        elif close_values[i] > close_values[i-lookback]:
            count[i] = count[i-1]-1 if count[i-1]<0 else -1
    
    return pd.Series(count, index=close.index)

def td_combo(close, lookback=2):
    count = np.zeros(len(close), dtype=np.float64)
    close_values = close.values
    
    for i in range(lookback, len(close)):
        if close_values[i] < close_values[i-lookback]:
            count[i] = count[i-1]+1 if count[i-1]>0 else 1
        elif close_values[i] > close_values[i-lookback]:
            count[i] = count[i-1]-1 if count[i-1]<0 else -1
    
    return pd.Series(count, index=close.index)

def marketwatch_indicator(close, open_):
    signal = (close > open_).astype(int) - (close < open_).astype(int)
    count = np.zeros(len(signal), dtype=np.float64)
    signal_values = signal.values
    
    count[0] = signal_values[0]
    for i in range(1, len(signal)):
        if signal_values[i] == signal_values[i-1] and signal_values[i] != 0:
            count[i] = count[i-1] + signal_values[i]
        else:
            count[i] = signal_values[i]
    
    return pd.Series(count, index=close.index)

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

    # Drop and recreate technical_data_daily table
    logging.info("Recreating technical_data_daily table...")
    cursor.execute("DROP TABLE IF EXISTS technical_data_daily;")
    cursor.execute("""
    CREATE TABLE technical_data_daily (
        symbol          VARCHAR(50),
        date            TIMESTAMP,
        rsi             DOUBLE PRECISION,
        macd            DOUBLE PRECISION,
        macd_signal     DOUBLE PRECISION,
        macd_hist       DOUBLE PRECISION,
        mom             DOUBLE PRECISION,
        roc             DOUBLE PRECISION,
        -- Multi-timeframe ROC metrics (CRITICAL for stock scoring)
        roc_10d         DOUBLE PRECISION,
        roc_20d         DOUBLE PRECISION,
        roc_60d         DOUBLE PRECISION,
        roc_120d        DOUBLE PRECISION,
        roc_252d        DOUBLE PRECISION,
        mansfield_rs    DOUBLE PRECISION,
        acc_dist_rating DOUBLE PRECISION,
        -- Trend indicators
        adx             DOUBLE PRECISION,
        plus_di         DOUBLE PRECISION,
        minus_di        DOUBLE PRECISION,
        atr             DOUBLE PRECISION,
        ad              DOUBLE PRECISION,
        cmf             DOUBLE PRECISION,
        mfi             DOUBLE PRECISION,
        td_sequential   DOUBLE PRECISION,
        td_combo        DOUBLE PRECISION,
        marketwatch     DOUBLE PRECISION,
        dm              DOUBLE PRECISION,
        -- Moving averages
        sma_10          DOUBLE PRECISION,
        sma_20          DOUBLE PRECISION,
        sma_50          DOUBLE PRECISION,
        sma_150         DOUBLE PRECISION,
        sma_200         DOUBLE PRECISION,
        ema_4           DOUBLE PRECISION,
        ema_9           DOUBLE PRECISION,
        ema_21          DOUBLE PRECISION,
        -- Bollinger Bands
        bbands_lower    DOUBLE PRECISION,
        bbands_middle   DOUBLE PRECISION,
        bbands_upper    DOUBLE PRECISION,
        -- Pivots
        pivot_high      DOUBLE PRECISION,
        pivot_low       DOUBLE PRECISION,
        pivot_high_triggered DOUBLE PRECISION,
        pivot_low_triggered DOUBLE PRECISION,
        fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """)
    logging.info("Table 'technical_data_daily' ready.")
    
    # Check for priority symbols from portfolio refresh
    priority_symbols = os.environ.get('PRIORITY_SYMBOLS', '').strip()
    trigger_source = os.environ.get('TRIGGER_SOURCE', '').strip()
    
    if priority_symbols and trigger_source == 'portfolio_refresh':
        symbols = [s.strip() for s in priority_symbols.split(',') if s.strip()]
        logging.info(f"🎯 PORTFOLIO REFRESH MODE: Processing {len(symbols)} priority symbols: {symbols}")
        return symbols
    
    # Default behavior: get all symbols
    cursor.execute("SELECT symbol FROM stock_symbols;")
    symbols = [r[0] for r in cursor.fetchall()]
    logging.info(f"📊 FULL MODE: Found {len(symbols)} symbols from stock_symbols table.")
    
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

def get_memory_usage():
    """Get current memory usage in MB. Returns None if psutil unavailable."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        logging.debug("psutil not available, cannot monitor memory usage")
        return None

def process_symbol(symbol, conn_pool):
    """Process a single symbol and return the number of rows inserted"""
    initial_memory = get_memory_usage()
    
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT date, open, high, low, close, volume
              FROM price_daily
             WHERE symbol = %s
             ORDER BY date ASC
        """, (symbol,))
        rows = cursor.fetchall()
        
        if not rows:
            logging.warning(f"No data for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0

        # Initialize DataFrame with proper data handling
        df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        df['date'] = pd.to_datetime(df['date'])
        
        # Ensure we have enough data for calculations (reduced minimum for efficiency)
        if len(df) < 20:  # Reduced from 30 to 20 bars for faster processing
            logging.warning(f"Insufficient data for {symbol}: {len(df)} bars (need at least 20)")
            conn_pool.putconn(conn)
            return 0
        
        # Sort by date to ensure proper ordering
        df = df.sort_values('date').reset_index(drop=True)
        df.set_index('date', inplace=True)
        
        # Convert to float32 for memory efficiency instead of float64
        float_dtype = np.float32 if USE_ULTRA_LOW_MEMORY else np.float64
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype(float_dtype)
        
        # Handle missing data more carefully - only forward fill, then drop remaining NaN
        df = df.ffill().dropna()
        
        # For ultra low memory mode, process in smaller chunks
        if USE_ULTRA_LOW_MEMORY and len(df) > 500:
            # Only process most recent 500 rows to save memory
            df = df.tail(500)
            logging.info(f"{symbol}: Ultra low memory mode - processing only {len(df)} recent bars")
        
        # Final check for sufficient data after cleaning (reduced minimum)
        if len(df) < 15:  # Reduced from 20 to 15 bars for efficiency
            logging.warning(f"Insufficient data after cleaning for {symbol}: {len(df)} bars")
            conn_pool.putconn(conn)
            return 0

        # --- FAST INDICATORS CALCULATION ---
        # Calculate all indicators using fast native implementations
        
        # RSI
        df['rsi'] = fast_rsi(df['close'], period=14)

        # MACD - calculate once and reuse
        df['macd'], df['macd_signal'], df['macd_hist'] = fast_macd(df['close'])

        # Momentum indicators - COMPLETE ROC FAMILY (required for stock_scores)
        df['mom'] = df['close'] - df['close'].shift(10)  # 10-period momentum
        df['roc'] = ((df['close'] - df['close'].shift(10)) / df['close'].shift(10)) * 100  # 10-period ROC

        # Multi-timeframe ROC calculations (CRITICAL for stock scoring)
        df['roc_10d'] = ((df['close'] - df['close'].shift(10)) / df['close'].shift(10)) * 100
        df['roc_20d'] = ((df['close'] - df['close'].shift(20)) / df['close'].shift(20)) * 100
        df['roc_60d'] = ((df['close'] - df['close'].shift(60)) / df['close'].shift(60)) * 100
        df['roc_120d'] = ((df['close'] - df['close'].shift(120)) / df['close'].shift(120)) * 100
        df['roc_252d'] = ((df['close'] - df['close'].shift(252)) / df['close'].shift(252)) * 100  # 1-year ROC

        # Mansfield Relative Strength (uses 10-period momentum)
        # RS = close / SMA(10) - 1, expressed as % where high RS = strong
        sma_10_temp = df['close'].rolling(window=10).mean()
        df['mansfield_rs'] = ((df['close'] / sma_10_temp) - 1) * 100

        # Accumulation/Distribution Rating (based on momentum and volume trends)
        # Positive AD = accumulation, Negative AD = distribution
        # Using existing ad column which has cumulative A/D values
        df['acc_dist_rating'] = ((df['close'] - df['close'].shift(1)) / df['close'].shift(1)) * 100  # Simplified version

        # ADX + DMI - calculate once
        df['adx'], df['plus_di'], df['minus_di'] = fast_adx(df['high'], df['low'], df['close'])
            
        # Calculate other indicators
        df['atr'] = fast_atr(df['high'], df['low'], df['close'])
        df['ad'] = fast_ad(df['high'], df['low'], df['close'], df['volume'])
        df['cmf'] = fast_ad(df['high'], df['low'], df['close'], df['volume'])  # Simplified CMF
        df['mfi'] = fast_mfi(df['high'], df['low'], df['close'], df['volume'])

        # Custom indicators
        df['td_sequential'] = td_sequential(df['close'], lookback=4)
        df['td_combo'] = td_combo(df['close'], lookback=2)
        df['marketwatch'] = marketwatch_indicator(df['close'], df['open'])

        # DM calculation
        dm_plus = df['high'].diff()
        dm_minus = df['low'].shift(1) - df['low']
        dm_plus = dm_plus.where((dm_plus>dm_minus)&(dm_plus>0), 0)
        dm_minus = dm_minus.where((dm_minus>dm_plus)&(dm_minus>0), 0)
        df['dm'] = dm_plus - dm_minus

        # Calculate all SMAs at once
        for p in [10, 20, 50, 150, 200]:
            df[f'sma_{p}'] = fast_sma(df['close'], p)
            
        # Calculate all EMAs at once
        for p in [4, 9, 21]:
            df[f'ema_{p}'] = fast_ema(df['close'], p)

        # Bollinger Bands
        df['bbands_lower'], df['bbands_middle'], df['bbands_upper'] = fast_bbands(df['close'])

        # Pivots - calculate directly on the DataFrame with date index
        df['pivot_high'] = pivot_high_vectorized(df, 3, 3)
        df['pivot_low'] = pivot_low_vectorized(df, 3, 3)
        df['pivot_high_triggered'] = pivot_high_triggered_vectorized(df, 3, 3)
        df['pivot_low_triggered'] = pivot_low_triggered_vectorized(df, 3, 3)

        # Clean data
        df = df.replace([np.inf, -np.inf], np.nan)

        # Remove duplicate dates (keep the latest/last one)
        # This prevents "ON CONFLICT DO UPDATE command cannot affect row a second time" error
        df = df.reset_index().drop_duplicates(subset=['date'], keep='last').set_index('date')

        # Prepare batch data efficiently
        # Use UPSERT to handle any duplicate data gracefully
        insert_q = """
        INSERT INTO technical_data_daily (
          symbol, date,
          rsi, macd, macd_signal, macd_hist,
          mom, roc, roc_10d, roc_20d, roc_60d, roc_120d, roc_252d,
          mansfield_rs, acc_dist_rating,
          adx, plus_di, minus_di, atr, ad, cmf, mfi,
          td_sequential, td_combo, marketwatch, dm,
          sma_10, sma_20, sma_50, sma_150, sma_200,
          ema_4, ema_9, ema_21,
          bbands_lower, bbands_middle, bbands_upper,
          pivot_high, pivot_low, pivot_high_triggered, pivot_low_triggered,
          fetched_at
        ) VALUES %s
        ON CONFLICT (symbol, date) DO UPDATE SET
          rsi = EXCLUDED.rsi,
          macd = EXCLUDED.macd,
          macd_signal = EXCLUDED.macd_signal,
          macd_hist = EXCLUDED.macd_hist,
          mom = EXCLUDED.mom,
          roc = EXCLUDED.roc,
          roc_10d = EXCLUDED.roc_10d,
          roc_20d = EXCLUDED.roc_20d,
          roc_60d = EXCLUDED.roc_60d,
          roc_120d = EXCLUDED.roc_120d,
          roc_252d = EXCLUDED.roc_252d,
          mansfield_rs = EXCLUDED.mansfield_rs,
          acc_dist_rating = EXCLUDED.acc_dist_rating,
          adx = EXCLUDED.adx,
          plus_di = EXCLUDED.plus_di,
          minus_di = EXCLUDED.minus_di,
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
          pivot_high_triggered = EXCLUDED.pivot_high_triggered,
          pivot_low_triggered = EXCLUDED.pivot_low_triggered,
          fetched_at = EXCLUDED.fetched_at;
        """

        # Prepare data for bulk insertion
        data = []
        for idx, row in df.reset_index().iterrows():
            # Handle datetime conversion safely
            date_val = row['date']
            if hasattr(date_val, 'to_pydatetime'):
                date_val = date_val.to_pydatetime()
            elif isinstance(date_val, np.datetime64):
                date_val = pd.Timestamp(date_val).to_pydatetime()
            
            data.append((
                symbol,
                date_val,
                sanitize_value(row.get('rsi')),
                sanitize_value(row.get('macd')),
                sanitize_value(row.get('macd_signal')),
                sanitize_value(row.get('macd_hist')),
                sanitize_value(row.get('mom')),
                sanitize_value(row.get('roc')),
                # Multi-timeframe ROC metrics
                sanitize_value(row.get('roc_10d')),
                sanitize_value(row.get('roc_20d')),
                sanitize_value(row.get('roc_60d')),
                sanitize_value(row.get('roc_120d')),
                sanitize_value(row.get('roc_252d')),
                sanitize_value(row.get('mansfield_rs')),
                sanitize_value(row.get('acc_dist_rating')),
                # Trend indicators
                sanitize_value(row.get('adx')),
                sanitize_value(row.get('plus_di')),
                sanitize_value(row.get('minus_di')),
                sanitize_value(row.get('atr')),
                sanitize_value(row.get('ad')),
                sanitize_value(row.get('cmf')),
                sanitize_value(row.get('mfi')),
                sanitize_value(row.get('td_sequential')),
                sanitize_value(row.get('td_combo')),
                sanitize_value(row.get('marketwatch')),
                sanitize_value(row.get('dm')),
                # Moving averages
                sanitize_value(row.get('sma_10')),
                sanitize_value(row.get('sma_20')),
                sanitize_value(row.get('sma_50')),
                sanitize_value(row.get('sma_150')),
                sanitize_value(row.get('sma_200')),
                sanitize_value(row.get('ema_4')),
                sanitize_value(row.get('ema_9')),
                sanitize_value(row.get('ema_21')),
                # Bollinger Bands
                sanitize_value(row.get('bbands_lower')),
                sanitize_value(row.get('bbands_middle')),
                sanitize_value(row.get('bbands_upper')),
                # Pivots
                sanitize_value(row.get('pivot_high')),
                sanitize_value(row.get('pivot_low')),
                sanitize_value(row.get('pivot_high_triggered')),
                sanitize_value(row.get('pivot_low_triggered')),
                datetime.now()
            ))
            
        # Use execute_values for faster bulk insertion
        if data:
            execute_values(cursor, insert_q, data)
            conn.commit()
            num_inserted = len(data)
            logging.info(f"✅ {symbol}: Inserted {num_inserted} rows")
        else:
            num_inserted = 0
            logging.warning(f"⚠️ {symbol}: No data to insert")
        
        cursor.close()
        conn_pool.putconn(conn)
        
        # Free memory aggressively for ECS tasks
        del df, data, rows
        gc.collect()
        
        # Additional memory cleanup for small ECS tasks
        final_memory = get_memory_usage()

        # Only perform memory checks if data is available
        if final_memory is not None:
            memory_used = final_memory - (initial_memory if initial_memory is not None else 0)

            if final_memory > MEMORY_THRESHOLD_MB:
                logging.warning(f"High memory usage: {final_memory:.1f}MB/{ECS_MEMORY_MB}MB after {symbol} (+{memory_used:.1f}MB)")
                # Force aggressive garbage collection
                gc.collect()
                gc.collect()  # Call twice for more thorough cleanup

            if final_memory > ECS_MEMORY_MB * 0.9:  # Using >90% of available memory
                logging.error(f"CRITICAL: Memory usage {final_memory:.1f}MB exceeds 90% of {ECS_MEMORY_MB}MB")
        
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
        
        # Process symbols sequentially to minimize memory usage on small ECS tasks
        if MAX_WORKERS > 1:
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
        else:
            # Sequential processing for memory-constrained environments
            conn_pool = create_connection_pool()
            try:
                for i in range(0, len(symbols), BATCH_SIZE):
                    batch = symbols[i:i + BATCH_SIZE]
                    for symbol in batch:
                        try:
                            # Check memory before processing each symbol
                            current_memory = get_memory_usage()
                            if current_memory is not None and current_memory > ECS_MEMORY_MB * 0.85:  # >85% memory usage
                                logging.warning(f"High memory before {symbol}: {current_memory:.1f}MB")
                                gc.collect()
                                
                            inserted = process_symbol(symbol, conn_pool)
                            total_inserted += inserted
                            if inserted > 0:
                                symbols_processed += 1
                            else:
                                symbols_failed += 1
                            # Force garbage collection after each symbol to free memory
                            gc.collect()
                        except Exception as e:
                            logging.error(f"❌ Error processing {symbol}: {str(e)}")
                            symbols_failed += 1
            finally:
                conn_pool.closeall()

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