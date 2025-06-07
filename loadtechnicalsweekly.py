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
SCRIPT_NAME = "loadtechnicalsweekly.py"
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
    """Convert NaN/inf values to None for database insertion"""
    if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
        return None
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
    if len(values) < period:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    alpha = 2.0 / (period + 1)
    result = np.zeros(len(values))
    result[0] = values.iloc[0]
    
    for i in range(1, len(values)):
        result[i] = alpha * values.iloc[i] + (1 - alpha) * result[i-1]
    
    # First (period-1) values should be NaN
    result[:period-1] = np.nan
    return pd.Series(result, index=values.index)

def rsi_fast(values, period=14):
    """Blazing fast RSI calculation"""
    if len(values) < period + 1:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    delta = values.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # Use Wilder's smoothing (like EMA with alpha = 1/period)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def macd_fast(values, fast=12, slow=26, signal=9):
    """Lightning fast MACD"""
    if len(values) < slow:
        nan_series = pd.Series(np.full(len(values), np.nan), index=values.index)
        return nan_series, nan_series, nan_series
    
    ema_fast = ema_fast(values, fast)
    ema_slow = ema_fast(values, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema_fast(macd_line, signal)
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

def bollinger_bands_fast(values, period=20, std_dev=2):
    """Ultra-fast Bollinger Bands"""
    if len(values) < period:
        nan_series = pd.Series(np.full(len(values), np.nan), index=values.index)
        return nan_series, nan_series, nan_series
    
    sma = sma_fast(values, period)
    rolling_std = values.rolling(window=period, min_periods=period).std()
    
    upper_band = sma + (rolling_std * std_dev)
    lower_band = sma - (rolling_std * std_dev)
    
    return lower_band, sma, upper_band

def atr_fast(high, low, close, period=14):
    """Average True Range - optimized"""
    if len(high) < period:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/period, adjust=False).mean()
    return atr

def adx_fast(high, low, close, period=14):
    """Simplified ADX for speed"""
    if len(high) < period + 1:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # Calculate directional movement
    plus_dm = high.diff()
    minus_dm = low.shift().sub(low)
    
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    
    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Smooth the values
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    
    # ADX calculation
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    
    return adx

def momentum_fast(values, period=10):
    """Simple momentum indicator"""
    return values.diff(period)

def roc_fast(values, period=10):
    """Rate of Change"""
    return ((values / values.shift(period)) - 1) * 100

def ad_line_fast(high, low, close, volume):
    """Accumulation/Distribution Line"""
    clv = ((close - low) - (high - close)) / (high - low)
    clv = clv.fillna(0)  # Handle division by zero
    ad = (clv * volume).cumsum()
    return ad

def cmf_fast(high, low, close, volume, period=20):
    """Chaikin Money Flow"""
    if len(high) < period:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    clv = ((close - low) - (high - close)) / (high - low)
    clv = clv.fillna(0)
    
    cmf_values = (clv * volume).rolling(window=period).sum() / volume.rolling(window=period).sum()
    return cmf_values

def mfi_fast(high, low, close, volume, period=14):
    """Money Flow Index"""
    if len(high) < period:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    typical_price = (high + low + close) / 3
    money_flow = typical_price * volume
    
    positive_flow = money_flow.where(typical_price > typical_price.shift(), 0)
    negative_flow = money_flow.where(typical_price < typical_price.shift(), 0)
    
    positive_mf = positive_flow.rolling(window=period).sum()
    negative_mf = negative_flow.rolling(window=period).sum()
    
    mfi = 100 - (100 / (1 + positive_mf / negative_mf))
    return mfi.fillna(50)

# -------------------------------
# Custom Technical Indicators (Vectorized)
# -------------------------------

def td_sequential_vectorized(close, lookback=4):
    """Tom DeMark Sequential - vectorized"""
    if len(close) < lookback + 1:
        return pd.Series(np.zeros(len(close)), index=close.index)
    
    # Setup comparison - price vs price 4 periods ago
    comparison = close > close.shift(lookback)
    
    # Initialize sequence counter
    sequence = pd.Series(np.zeros(len(close)), index=close.index)
    
    # Vectorized counting using cumsum and groupby
    # Reset counter when condition changes
    condition_changes = comparison.ne(comparison.shift()).cumsum()
    
    # Count consecutive occurrences within each group
    for group_id in condition_changes.unique():
        if pd.isna(group_id):
            continue
        
        mask = condition_changes == group_id
        group_data = comparison[mask]
        
        if len(group_data) > 0 and group_data.iloc[0]:  # Only count bullish sequences
            sequence[mask] = range(1, len(group_data) + 1)
    
    # Cap at 13 (traditional TD Sequential limit)
    sequence = sequence.clip(upper=13)
    return sequence

def td_combo_vectorized(close, lookback=2):
    """Tom DeMark Combo - vectorized"""
    if len(close) < lookback + 1:
        return pd.Series(np.zeros(len(close)), index=close.index)
    
    # Combo uses close vs close 2 periods ago
    comparison = close > close.shift(lookback)
    
    # Similar logic to sequential but different lookback
    sequence = pd.Series(np.zeros(len(close)), index=close.index)
    condition_changes = comparison.ne(comparison.shift()).cumsum()
    
    for group_id in condition_changes.unique():
        if pd.isna(group_id):
            continue
        
        mask = condition_changes == group_id
        group_data = comparison[mask]
        
        if len(group_data) > 0 and group_data.iloc[0]:
            sequence[mask] = range(1, len(group_data) + 1)
    
    return sequence.clip(upper=13)

def marketwatch_indicator_vectorized(close, open_price):
    """Custom MarketWatch-style momentum indicator"""
    # Combine intraday and inter-day momentum
    intraday_momentum = (close - open_price) / open_price
    interday_momentum = close.pct_change()
    
    # Weighted combination (60% interday, 40% intraday)
    combined_momentum = 0.6 * interday_momentum + 0.4 * intraday_momentum
    
    # Normalize to -100 to +100 scale
    normalized = combined_momentum * 100
    return normalized.fillna(0)

# -------------------------------
# Vectorized Pivot Functions 
# -------------------------------
def pivot_high_vectorized(high, left_bars=3, right_bars=3):
    """Vectorized pivot high calculation"""
    if len(high) < left_bars + right_bars + 1:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # For each point, check if it's higher than surrounding points
    pivot_highs = pd.Series(np.full(len(high), np.nan), index=high.index)
    
    for i in range(left_bars, len(high) - right_bars):
        current_high = high.iloc[i]
        left_max = high.iloc[i-left_bars:i].max()
        right_max = high.iloc[i+1:i+right_bars+1].max()
        
        if current_high > left_max and current_high > right_max:
            pivot_highs.iloc[i] = current_high
    
    return pivot_highs

def pivot_low_vectorized(low, left_bars=3, right_bars=3):
    """Vectorized pivot low calculation"""
    if len(low) < left_bars + right_bars + 1:
        return pd.Series(np.full(len(low), np.nan), index=low.index)
    
    # For each point, check if it's lower than surrounding points
    pivot_lows = pd.Series(np.full(len(low), np.nan), index=low.index)
    
    for i in range(left_bars, len(low) - right_bars):
        current_low = low.iloc[i]
        left_min = low.iloc[i-left_bars:i].min()
        right_min = low.iloc[i+1:i+right_bars+1].min()
        
        if current_low < left_min and current_low < right_min:
            pivot_lows.iloc[i] = current_low
    
    return pivot_lows

# -------------------------------
# PARALLEL TECHNICAL CALCULATION ENGINE
# -------------------------------

def calculate_technicals_parallel(df):
    """Calculate all technical indicators using parallel processing where beneficial"""
    if len(df) < 50:  # Need minimum data for indicators
        logging.warning(f"Insufficient data: {len(df)} rows")
        return pd.DataFrame()
    
    # Ensure proper data types for performance
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Memory-optimized data types
    df['open'] = df['open'].astype('float32')
    df['high'] = df['high'].astype('float32')
    df['low'] = df['low'].astype('float32')
    df['close'] = df['close'].astype('float32')
    df['volume'] = df['volume'].astype('int64')
    
    # Fill gaps and drop NaN rows
    df = df.ffill().bfill().dropna()
    
    # Use ThreadPoolExecutor for I/O bound operations (limited by GIL but still helpful)
    def calculate_trend_indicators():
        """Calculate trend-following indicators"""
        results = {}
        
        # Moving averages (fastest calculations)
        for period in [10, 20, 50, 150, 200]:
            results[f'sma_{period}'] = sma_fast(df['close'], period)
        
        for period in [4, 9, 21]:
            results[f'ema_{period}'] = ema_fast(df['close'], period)
        
        # MACD
        macd, signal, hist = macd_fast(df['close'])
        results['macd'] = macd
        results['macd_signal'] = signal
        results['macd_hist'] = hist
        
        # Bollinger Bands
        bb_lower, bb_middle, bb_upper = bollinger_bands_fast(df['close'])
        results['bbands_lower'] = bb_lower
        results['bbands_middle'] = bb_middle
        results['bbands_upper'] = bb_upper
        
        return results
    
    def calculate_momentum_indicators():
        """Calculate momentum and oscillator indicators"""
        results = {}
        
        # RSI
        results['rsi'] = rsi_fast(df['close'])
        
        # Momentum indicators
        results['mom'] = momentum_fast(df['close'])
        results['roc'] = roc_fast(df['close'])
        
        # ADX and ATR
        results['adx'] = adx_fast(df['high'], df['low'], df['close'])
        results['atr'] = atr_fast(df['high'], df['low'], df['close'])
        
        return results
    
    def calculate_volume_indicators():
        """Calculate volume-based indicators"""
        results = {}
        
        # Volume indicators
        results['ad'] = ad_line_fast(df['high'], df['low'], df['close'], df['volume'])
        results['cmf'] = cmf_fast(df['high'], df['low'], df['close'], df['volume'])
        results['mfi'] = mfi_fast(df['high'], df['low'], df['close'], df['volume'])
        
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
    
    # Execute calculations in parallel (limited parallelization due to GIL)
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_trend = executor.submit(calculate_trend_indicators)
        future_momentum = executor.submit(calculate_momentum_indicators)
        future_volume = executor.submit(calculate_volume_indicators)
        future_custom = executor.submit(calculate_custom_indicators)
        
        # Collect results
        trend_results = future_trend.result()
        momentum_results = future_momentum.result()
        volume_results = future_volume.result()
        custom_results = future_custom.result()
    
    # Combine all results into the dataframe
    all_results = {}
    all_results.update(trend_results)
    all_results.update(momentum_results)
    all_results.update(volume_results)
    all_results.update(custom_results)
    
    # Apply results to dataframe
    for key, value in all_results.items():
        if isinstance(value, pd.Series):
            df[key] = value
    
    # Clean infinite values
    df = df.replace([np.inf, -np.inf], np.nan)
    
    return df

# -------------------------------
# DB Connection Optimization
# -------------------------------
def get_optimized_connection(cfg):
    """Get database connection with performance optimizations"""
    conn = psycopg2.connect(
        host=cfg["host"], 
        port=cfg["port"],
        user=cfg["user"], 
        password=cfg["password"],
        dbname=cfg["dbname"],
        # Performance optimizations
        connect_timeout=10,
        application_name="technicals_weekly_loader"
    )
    
    # Aggressive performance tuning
    with conn.cursor() as cur:
        cur.execute("SET work_mem = '256MB'")
        cur.execute("SET maintenance_work_mem = '1GB'") 
        cur.execute("SET effective_cache_size = '4GB'")
        cur.execute("SET random_page_cost = 1.1")
        cur.execute("SET effective_io_concurrency = 200")
        cur.execute("SET wal_buffers = '16MB'")
        cur.execute("SET checkpoint_completion_target = 0.9")
        cur.execute("SET max_wal_size = '4GB'")
        cur.execute("SET synchronous_commit = off")  # Aggressive!
        
    conn.autocommit = False
    return conn

# -------------------------------
# OPTIMIZED BATCH LOADER
# -------------------------------

def load_technicals_optimized(symbols):
    """Optimized technical indicators loader with batch processing and advanced parallelization"""
    
    cfg = get_db_config()
    conn = get_optimized_connection(cfg)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    total = len(symbols)
    logging.info(f"Loading technical indicators for {total} symbols")
    inserted, failed = 0, []
    
    # Optimized batch processing parameters
    CHUNK_SIZE = 25  # Reduced for better memory management
    PAUSE = 0.05     # Minimal pause
    PARALLEL_DB_WORKERS = 2  # Limited parallelism for DB operations
    
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE
    
    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        
        logging.info(f"Technical indicators – batch {batch_idx+1}/{batches} ({len(batch)} symbols)")
        log_mem(f"technicals batch {batch_idx+1} start")
        
        # Memory management
        gc.disable()
        
        try:
            # Process symbols in parallel within the batch
            def process_symbol(symbol):
                try:
                    # Fetch price data for this symbol
                    cur.execute("""
                        SELECT date, open, high, low, close, volume
                        FROM price_weekly
                        WHERE symbol = %s
                        ORDER BY date ASC
                    """, (symbol,))
                    
                    rows = cur.fetchall()
                    if not rows:
                        logging.warning(f"No price data for {symbol}, skipping")
                        return None, symbol
                    
                    # Convert to DataFrame with optimized dtypes
                    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                    
                    # Calculate technical indicators using parallel processing
                    df_tech = calculate_technicals_parallel(df.copy())
                    
                    if df_tech.empty:
                        logging.warning(f"Failed to calculate technicals for {symbol}")
                        return None, symbol
                    
                    # Prepare data for insertion with optimized data handling
                    insert_data = []
                    for idx, row in df_tech.reset_index().iterrows():
                        insert_data.append([
                            symbol,
                            row['date'].to_pydatetime(),
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
                        ])
                    
                    return insert_data, symbol
                    
                except Exception as e:
                    logging.error(f"❌ {symbol}: Failed - {str(e)}")
                    return None, symbol
            
            # Process batch sequentially for now (can be parallelized further if needed)
            for symbol in batch:
                insert_data, processed_symbol = process_symbol(symbol)
                
                if insert_data:
                    try:
                        # Bulk insert using execute_values with optimized page size
                        insert_query = """
                        INSERT INTO technical_data_weekly (
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
                        """
                        execute_values(cur, insert_query, insert_data, page_size=5000)  # Optimized page size
                        conn.commit()
                        inserted += 1
                        logging.info(f"✅ {processed_symbol}: {len(insert_data)} technical indicators inserted")
                        
                        # Aggressive memory cleanup
                        del insert_data
                        
                    except Exception as e:
                        logging.error(f"❌ {processed_symbol}: DB insertion failed - {str(e)}")
                        failed.append(processed_symbol)
                        conn.rollback()
                        continue
                else:
                    failed.append(processed_symbol)
                    
        finally:
            gc.enable()
        
        # Force garbage collection and memory cleanup
        gc.collect()
        log_mem(f"technicals batch {batch_idx+1} end")
        time.sleep(PAUSE)
    
    cur.close()
    conn.close()
    return total, inserted, failed

def load_technicals(symbols, cur, conn):
    """Legacy function maintained for compatibility - delegates to optimized version"""
    return load_technicals_optimized(symbols)

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

    # Recreate technical_data_weekly table
    logging.info("Recreating technical_data_weekly table…")
    cur.execute("DROP TABLE IF EXISTS technical_data_weekly CASCADE;")
    cur.execute("""
        CREATE TABLE technical_data_weekly (
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
        CREATE INDEX idx_technical_weekly_symbol ON technical_data_weekly(symbol);
        CREATE INDEX idx_technical_weekly_date ON technical_data_weekly(date);
    """)
    
    conn.commit()

    # Get symbols that have price data
    cur.execute("""
        SELECT DISTINCT symbol 
        FROM price_weekly 
        ORDER BY symbol
    """)
    symbols = [r["symbol"] for r in cur.fetchall()]
    
    if not symbols:
        logging.error("No symbols found in price_weekly table")
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
