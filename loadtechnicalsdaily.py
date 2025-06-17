#!/usr/bin/env python3 
import sys
import time
import logging
import json
import os
import gc
import psutil
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
SCRIPT_NAME = "loadtechnicalsdaily.py"
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
# Pure NumPy/Pandas Technical Indicators (No TA-Lib dependencies)
# Same as weekly/monthly - COMPLETE IMPLEMENTATION
# -------------------------------

def sma_fast(values, period):
    """Ultra-fast SMA using numpy convolution"""
    if len(values) < period:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    kernel = np.ones(period) / period
    result = np.convolve(values.values, kernel, mode='valid')
    padded_result = np.concatenate([np.full(period - 1, np.nan), result])
    return pd.Series(padded_result, index=values.index)

def ema_fast(values, period):
    """Ultra-fast EMA implementation"""
    if len(values) < 1:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    alpha = 2.0 / (period + 1.0)
    result = np.empty_like(values.values, dtype=np.float64)
    
    first_valid_idx = values.first_valid_index()
    if first_valid_idx is None:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    first_valid_pos = values.index.get_loc(first_valid_idx)
    result[:first_valid_pos] = np.nan
    result[first_valid_pos] = values.iloc[first_valid_pos]
    
    for i in range(first_valid_pos + 1, len(values)):
        if np.isnan(values.iloc[i]):
            result[i] = result[i-1]
        else:
            result[i] = alpha * values.iloc[i] + (1 - alpha) * result[i - 1]
    
    return pd.Series(result, index=values.index)

def rsi_fast(values, period=14):
    """Lightning-fast RSI"""
    if len(values) < period + 1:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    changes = values.diff()
    gains = changes.where(changes > 0, 0)
    losses = -changes.where(changes < 0, 0)
    
    avg_gains = gains.ewm(span=period, adjust=False).mean()
    avg_losses = losses.ewm(span=period, adjust=False).mean()
    
    rs = avg_gains / (avg_losses + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    
    return rsi.fillna(50)

def macd_fast(values, fast=12, slow=26, signal=9):
    """Ultra-fast MACD"""
    if len(values) < slow:
        nan_series = pd.Series(np.full(len(values), np.nan), index=values.index)
        return nan_series, nan_series, nan_series
    
    ema_fast_line = ema_fast(values, fast)
    ema_slow_line = ema_fast(values, slow)
    
    macd_line = ema_fast_line - ema_slow_line
    signal_line = ema_fast(macd_line, signal)
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

def bollinger_bands_fast(values, period=20, std_multiplier=2):
    """Ultra-fast Bollinger Bands"""
    if len(values) < period:
        nan_series = pd.Series(np.full(len(values), np.nan), index=values.index)
        return nan_series, nan_series, nan_series
    
    middle = sma_fast(values, period)
    rolling_std = values.rolling(window=period, min_periods=period).std()
    
    upper = middle + (std_multiplier * rolling_std)
    lower = middle - (std_multiplier * rolling_std)
    
    return lower, middle, upper

def atr_fast(high, low, close, period=14):
    """Average True Range"""
    if len(high) < 2:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
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
    """Money Flow Index - Fixed to handle edge cases"""
    if len(high) < period + 1:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    try:
        # Ensure all inputs are numeric and not empty
        high = pd.to_numeric(high, errors='coerce')
        low = pd.to_numeric(low, errors='coerce')
        close = pd.to_numeric(close, errors='coerce')
        volume = pd.to_numeric(volume, errors='coerce')
        
        # Remove any rows where any value is NaN
        mask = ~(high.isna() | low.isna() | close.isna() | volume.isna() | (volume <= 0))
        if mask.sum() < period + 1:
            return pd.Series(np.full(len(high), np.nan), index=high.index)
        
        # Typical Price
        typical_price = (high + low + close) / 3
        
        # Raw Money Flow
        raw_money_flow = typical_price * volume
        
        # Positive and Negative Money Flow
        price_changes = typical_price.diff()
        pos_money_flow = raw_money_flow.where(price_changes > 0, 0)
        neg_money_flow = raw_money_flow.where(price_changes < 0, 0)
        
        # Rolling sums with minimum periods
        pos_sum = pos_money_flow.rolling(window=period, min_periods=1).sum()
        neg_sum = neg_money_flow.rolling(window=period, min_periods=1).sum()
        
        # MFI calculation with better error handling
        neg_sum_safe = neg_sum.replace(0, 1e-10)  # Avoid division by zero
        money_ratio = pos_sum / neg_sum_safe
        mfi = 100 - (100 / (1 + money_ratio))
        
        # Ensure MFI is between 0 and 100
        mfi = mfi.clip(0, 100)
        
        return mfi.fillna(50)
        
    except Exception as e:
        logging.warning(f"MFI calculation failed: {e}")
        return pd.Series(np.full(len(high), 50.0), index=high.index)

def pivot_high_vectorized(high, left_bars=3, right_bars=3):
    """
    Pivot high calculation based on Pine Script / TradingView logic
    Similar to the approach in buysellload_1.py
    """
    if len(high) < left_bars + right_bars + 1:
        logging.warning(f"⚠️ Pivot High: Insufficient data length {len(high)}, need at least {left_bars + right_bars + 1}")
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # Convert to numpy for easier manipulation, preserve index
    high_values = high.values
    result_values = np.full(len(high), np.nan)
    pivot_count = 0
    
    logging.info(f"🔧 Pivot High: Scanning {len(high)} bars with left={left_bars}, right={right_bars}")
    logging.info(f"📊 High data range: min={np.nanmin(high_values):.4f}, max={np.nanmax(high_values):.4f}")
    
    # Look for pivot highs - a bar that is higher than both left and right surrounding bars
    for i in range(left_bars, len(high_values) - right_bars):
        current_val = high_values[i]
        
        # Check if current bar is higher than all bars to the left
        left_check = True
        for j in range(i - left_bars, i):
            if high_values[j] >= current_val:
                left_check = False
                break
        
        # Check if current bar is higher than all bars to the right
        right_check = True
        for j in range(i + 1, i + right_bars + 1):
            if high_values[j] >= current_val:
                right_check = False
                break
        
        # If both checks pass, it's a pivot high
        if left_check and right_check:
            result_values[i] = current_val
            pivot_count += 1
            
            if pivot_count <= 5:  # Log first few pivots
                logging.info(f"✅ Pivot High #{pivot_count} at bar {i}: {current_val:.4f}")
                if pivot_count <= 2:  # Detailed info for first two
                    left_vals = high_values[i-left_bars:i]
                    right_vals = high_values[i+1:i+right_bars+1] 
                    logging.info(f"📊   Left bars: {left_vals}")
                    logging.info(f"📊   Right bars: {right_vals}")
    
    logging.info(f"✅ Pivot High: Found {pivot_count} pivot highs out of {len(high) - left_bars - right_bars} possible bars")
    
    # Diagnostic info if no pivots found
    if pivot_count == 0:
        logging.error("❌ No pivot highs found! Sample data analysis:")
        sample_size = min(10, len(high))
        logging.error(f"📊 First {sample_size} values: {high_values[:sample_size]}")
        if len(high) > 20:
            mid_start = len(high) // 2 - 5
            logging.error(f"📊 Middle values: {high_values[mid_start:mid_start+10]}")
    
    return pd.Series(result_values, index=high.index)

def pivot_low_vectorized(low, left_bars=3, right_bars=3):
    """
    Pivot low calculation based on Pine Script / TradingView logic
    Similar to the approach in buysellload_1.py
    """
    if len(low) < left_bars + right_bars + 1:
        logging.warning(f"⚠️ Pivot Low: Insufficient data length {len(low)}, need at least {left_bars + right_bars + 1}")
        return pd.Series(np.full(len(low), np.nan), index=low.index)
    
    # Convert to numpy for easier manipulation, preserve index
    low_values = low.values
    result_values = np.full(len(low), np.nan)
    pivot_count = 0
    
    logging.info(f"🔧 Pivot Low: Scanning {len(low)} bars with left={left_bars}, right={right_bars}")
    logging.info(f"📊 Low data range: min={np.nanmin(low_values):.4f}, max={np.nanmax(low_values):.4f}")
    
    # Look for pivot lows - a bar that is lower than both left and right surrounding bars
    for i in range(left_bars, len(low_values) - right_bars):
        current_val = low_values[i]
        
        # Check if current bar is lower than all bars to the left
        left_check = True
        for j in range(i - left_bars, i):
            if low_values[j] <= current_val:
                left_check = False
                break
        
        # Check if current bar is lower than all bars to the right
        right_check = True
        for j in range(i + 1, i + right_bars + 1):
            if low_values[j] <= current_val:
                right_check = False
                break
        
        # If both checks pass, it's a pivot low
        if left_check and right_check:
            result_values[i] = current_val
            pivot_count += 1
            
            if pivot_count <= 5:  # Log first few pivots
                logging.info(f"✅ Pivot Low #{pivot_count} at bar {i}: {current_val:.4f}")
                if pivot_count <= 2:  # Detailed info for first two
                    left_vals = low_values[i-left_bars:i]
                    right_vals = low_values[i+1:i+right_bars+1]
                    logging.info(f"📊   Left bars: {left_vals}")
                    logging.info(f"📊   Right bars: {right_vals}")
    
    logging.info(f"✅ Pivot Low: Found {pivot_count} pivot lows out of {len(low) - left_bars - right_bars} possible bars")
    
    # Diagnostic info if no pivots found
    if pivot_count == 0:
        logging.error("❌ No pivot lows found! Sample data analysis:")
        sample_size = min(10, len(low))
        logging.error(f"📊 First {sample_size} values: {low_values[:sample_size]}")
        if len(low) > 20:
            mid_start = len(low) // 2 - 5
            logging.error(f"📊 Middle values: {low_values[mid_start:mid_start+10]}")
    
    return pd.Series(result_values, index=low.index)

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

def calculate_technicals_parallel(df):
    """Calculate all technical indicators using parallel processing where beneficial - COMPLETE IMPLEMENTATION"""
    logging.info(f"🔧 Starting technical calculations for {len(df)} rows of data")
    
    # Ensure proper data types
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
      # Fill gaps and drop NaN rows
    original_len = len(df)
    df = df.ffill().bfill().dropna()
    
    if len(df) != original_len:
        logging.info(f"📊 Cleaned data: {original_len} → {len(df)} rows after removing NaN")
    
    if len(df) < 50:  # Need minimum data for calculations
        logging.warning(f"⚠️ Insufficient data for technicals: {len(df)} rows (need at least 50)")
        return None

    try:
        results = {}
        
        # Basic indicators
        logging.info("🔄 Calculating basic indicators...")
        results['rsi'] = rsi_fast(df['close'], period=14)
        logging.info(f"✓ RSI: {results['rsi'].count()} valid values, {results['rsi'].isna().sum()} NaN")
        
        results['mom'] = momentum_fast(df['close'], period=10)
        logging.info(f"✓ Momentum: {results['mom'].count()} valid values, {results['mom'].isna().sum()} NaN")
        
        results['roc'] = roc_fast(df['close'], period=10)
        logging.info(f"✓ ROC: {results['roc'].count()} valid values, {results['roc'].isna().sum()} NaN")
          # Volume indicators (MISSING FROM ORIGINAL)
        logging.info("🔄 Calculating volume indicators...")
        logging.info(f"📊 Volume data: min={df['volume'].min()}, max={df['volume'].max()}, nan_count={df['volume'].isna().sum()}")
        logging.info(f"📊 Sample volume values: {df['volume'].head(5).tolist()}")
        logging.info(f"📊 High-Low-Close sample: H={df['high'].head(3).tolist()}, L={df['low'].head(3).tolist()}, C={df['close'].head(3).tolist()}")
        
        # A/D Line with detailed logging
        logging.info("🔧 Calculating A/D Line...")
        try:
            results['ad'] = ad_line_fast(df['high'], df['low'], df['close'], df['volume'])
            sample_ad = results['ad'].dropna().head(3)
            logging.info(f"✓ A/D Line: {results['ad'].count()} valid values, {results['ad'].isna().sum()} NaN")
            logging.info(f"📊 A/D Sample values: {sample_ad.tolist()}")
            if results['ad'].count() == 0:
                logging.error("❌ A/D Line: ALL VALUES ARE NaN! Investigating...")
                # Check intermediate calculations
                mfm_sample = ((df['close'].head(3) - df['low'].head(3)) - (df['high'].head(3) - df['close'].head(3))) / (df['high'].head(3) - df['low'].head(3) + 1e-10)
                logging.error(f"📊 MFM sample: {mfm_sample.tolist()}")
                mfv_sample = mfm_sample * df['volume'].head(3)
                logging.error(f"📊 MFV sample: {mfv_sample.tolist()}")
        except Exception as e:
            logging.error(f"❌ A/D Line calculation failed: {e}")
            results['ad'] = pd.Series(np.full(len(df), np.nan), index=df.index)
        
        # CMF with detailed logging
        logging.info("🔧 Calculating CMF...")
        try:
            results['cmf'] = cmf_fast(df['high'], df['low'], df['close'], df['volume'], period=20)
            sample_cmf = results['cmf'].dropna().head(3)
            logging.info(f"✓ CMF: {results['cmf'].count()} valid values, {results['cmf'].isna().sum()} NaN")
            logging.info(f"📊 CMF Sample values: {sample_cmf.tolist()}")
            if results['cmf'].count() == 0:
                logging.error("❌ CMF: ALL VALUES ARE NaN! Need at least 20 periods for CMF calculation")
        except Exception as e:
            logging.error(f"❌ CMF calculation failed: {e}")
            results['cmf'] = pd.Series(np.full(len(df), np.nan), index=df.index)
        
        # MFI with detailed logging
        logging.info("🔧 Calculating MFI...")
        try:
            results['mfi'] = mfi_fast(df['high'], df['low'], df['close'], df['volume'], period=14)
            sample_mfi = results['mfi'].dropna().head(3)
            logging.info(f"✓ MFI: {results['mfi'].count()} valid values, {results['mfi'].isna().sum()} NaN")
            logging.info(f"📊 MFI Sample values: {sample_mfi.tolist()}")
            if results['mfi'].count() == 0:
                logging.error("❌ MFI: ALL VALUES ARE NaN! Investigating...")
                # Check typical price calculation
                tp_sample = (df['high'].head(3) + df['low'].head(3) + df['close'].head(3)) / 3
                logging.error(f"📊 Typical Price sample: {tp_sample.tolist()}")
                rmf_sample = tp_sample * df['volume'].head(3)
                logging.error(f"📊 Raw Money Flow sample: {rmf_sample.tolist()}")
        except Exception as e:
            logging.error(f"❌ MFI calculation failed: {e}")
            results['mfi'] = pd.Series(np.full(len(df), 50.0), index=df.index)
        
        # Moving averages
        logging.info("🔄 Calculating moving averages...")
        for period in [10, 20, 50, 150, 200]:
            results[f'sma_{period}'] = sma_fast(df['close'], period)
        
        for period in [4, 9, 21]:
            results[f'ema_{period}'] = ema_fast(df['close'], period)
        
        # Complex indicators
        logging.info("🔄 Calculating complex indicators...")
        
        # MACD
        macd_line, signal_line, histogram = macd_fast(df['close'], fast=12, slow=26, signal=9)
        results['macd'] = macd_line
        results['macd_signal'] = signal_line
        results['macd_hist'] = histogram
        
        # ADX (computationally expensive)
        results['adx'] = adx_fast(df['high'], df['low'], df['close'], period=14)
        
        # Bollinger Bands
        bb_lower, bb_middle, bb_upper = bollinger_bands_fast(df['close'], period=20, std_multiplier=2)
        results['bbands_lower'] = bb_lower
        results['bbands_middle'] = bb_middle
        results['bbands_upper'] = bb_upper
        
        # ATR
        results['atr'] = atr_fast(df['high'], df['low'], df['close'], period=14)
          # Custom indicators (MISSING FROM ORIGINAL)
        logging.info("🔄 Calculating custom indicators...")
        results['td_sequential'] = td_sequential_vectorized(df['close'], lookback=4)
        logging.info(f"✓ TD Sequential: {results['td_sequential'].count()} valid values, {results['td_sequential'].isna().sum()} NaN")
        
        results['td_combo'] = td_combo_vectorized(df['close'], lookback=2)
        logging.info(f"✓ TD Combo: {results['td_combo'].count()} valid values, {results['td_combo'].isna().sum()} NaN")
        
        results['marketwatch'] = marketwatch_indicator_vectorized(df['close'], df['open'])
        logging.info(f"✓ MarketWatch: {results['marketwatch'].count()} valid values, {results['marketwatch'].isna().sum()} NaN")
          # Pivot points (MISSING FROM ORIGINAL)
        logging.info("🔄 Calculating pivot points...")
        logging.info(f"📊 High data: min={df['high'].min()}, max={df['high'].max()}")
        logging.info(f"📊 Low data: min={df['low'].min()}, max={df['low'].max()}")
        logging.info(f"📊 Data length: {len(df)} rows (need at least 7 for 3+3 bars)")
        
        # Pivot High with detailed logging
        logging.info("🔧 Calculating Pivot High...")
        try:
            results['pivot_high'] = pivot_high_vectorized(df['high'], left_bars=3, right_bars=3)
            pivot_high_count = results['pivot_high'].count()
            logging.info(f"✓ Pivot High: {pivot_high_count} valid values, {results['pivot_high'].isna().sum()} NaN")
            if pivot_high_count > 0:
                sample_pivots = results['pivot_high'].dropna().head(3)
                logging.info(f"📊 Pivot High Sample values: {sample_pivots.tolist()}")
            else:
                logging.warning("⚠️ No pivot highs found - this may be normal if data doesn't have clear pivot points")
                # Show some high values for context
                logging.info(f"📊 Recent high values: {df['high'].tail(10).tolist()}")
        except Exception as e:
            logging.error(f"❌ Pivot High calculation failed: {e}")
            results['pivot_high'] = pd.Series(np.full(len(df), np.nan), index=df.index)
        
        # Pivot Low with detailed logging
        logging.info("🔧 Calculating Pivot Low...")
        try:
            results['pivot_low'] = pivot_low_vectorized(df['low'], left_bars=3, right_bars=3)
            pivot_low_count = results['pivot_low'].count()
            logging.info(f"✓ Pivot Low: {pivot_low_count} valid values, {results['pivot_low'].isna().sum()} NaN")
            if pivot_low_count > 0:
                sample_pivots = results['pivot_low'].dropna().head(3)
                logging.info(f"📊 Pivot Low Sample values: {sample_pivots.tolist()}")
            else:
                logging.warning("⚠️ No pivot lows found - this may be normal if data doesn't have clear pivot points")
                # Show some low values for context
                logging.info(f"📊 Recent low values: {df['low'].tail(10).tolist()}")
        except Exception as e:
            logging.error(f"❌ Pivot Low calculation failed: {e}")
            results['pivot_low'] = pd.Series(np.full(len(df), np.nan), index=df.index)
          # DM calculation (MISSING FROM ORIGINAL)
        logging.info("🔄 Calculating directional movement...")
        try:
            dm_plus = df['high'].diff()
            dm_minus = df['low'].shift(1) - df['low']
            logging.info(f"📊 DM+ sample (raw): {dm_plus.head(5).tolist()}")
            logging.info(f"📊 DM- sample (raw): {dm_minus.head(5).tolist()}")
            
            dm_plus = dm_plus.where((dm_plus>dm_minus)&(dm_plus>0), 0)
            dm_minus = dm_minus.where((dm_minus>dm_plus)&(dm_minus>0), 0)
            
            logging.info(f"📊 DM+ sample (filtered): {dm_plus.head(5).tolist()}")
            logging.info(f"📊 DM- sample (filtered): {dm_minus.head(5).tolist()}")
            
            results['dm'] = dm_plus - dm_minus
            dm_count = results['dm'].count()
            logging.info(f"✓ DM: {dm_count} valid values, {results['dm'].isna().sum()} NaN")
            if dm_count > 0:
                sample_dm = results['dm'].dropna().head(5)
                logging.info(f"📊 DM Sample values: {sample_dm.tolist()}")
            else:
                logging.error("❌ DM: ALL VALUES ARE NaN!")
        except Exception as e:
            logging.error(f"❌ DM calculation failed: {e}")
            import traceback
            logging.error(f"❌ DM traceback: {traceback.format_exc()}")
            results['dm'] = pd.Series(np.full(len(df), 0), index=df.index)
        
        # Combine all results into the original dataframe
        for key, series in results.items():
            df[key] = series
        
        # Clean infinite values
        df = df.replace([np.inf, -np.inf], np.nan)
        
        logging.info(f"✅ Technical calculations completed successfully for {len(results)} indicators")
        return df
        
    except Exception as e:
        logging.error(f"❌ Failed to calculate technicals: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        return None

def validate_prerequisites(cur):
    """Validate that prerequisites for loading technical data are met"""
    try:
        logging.info("🔍 Step 1: Checking if price_daily table exists...")
        
        # Check if price_daily table exists and has data
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'price_daily'
            ) as table_exists
        """)
        result = cur.fetchone()
        price_table_exists = result['table_exists']
        logging.info(f"📊 price_daily table exists: {price_table_exists}")
        
        if not price_table_exists:
            logging.error("❌ price_daily table does not exist. Technical data requires price data.")
            logging.error("💡 Hint: Run the price data loader first (pricedaily-loader) to populate price_daily table")
            return False
        
        logging.info("🔍 Step 2: Checking if price_daily table has data...")
        
        # Check total number of rows first
        cur.execute("SELECT COUNT(*) as total_rows FROM price_daily")
        result = cur.fetchone()
        total_rows = result['total_rows']
        logging.info(f"📊 Total rows in price_daily: {total_rows}")
        
        if total_rows == 0:
            logging.error("❌ price_daily table exists but is empty (0 rows)")
            logging.error("💡 Hint: Run the price data loader first (pricedaily-loader) to populate price_daily table")
            return False
        
        # Check if we have price data for symbols
        logging.info("🔍 Step 3: Counting distinct symbols in price_daily...")
        cur.execute("SELECT COUNT(DISTINCT symbol) as symbol_count FROM price_daily")
        result = cur.fetchone()
        price_symbol_count = result['symbol_count'] if result else 0
        logging.info(f"📊 Distinct symbols in price_daily: {price_symbol_count}")
        
        if price_symbol_count == 0:
            logging.error("❌ No distinct symbols found in price_daily table")
            logging.error("💡 This is unusual - table has rows but no distinct symbols")
            return False
        
        logging.info(f"✅ Prerequisites met: price_daily table exists with {price_symbol_count} symbols")
        return True
        
    except Exception as e:
        logging.error(f"❌ Exception type: {type(e).__name__}")
        logging.error(f"❌ Exception details: {repr(e)}")
        logging.error(f"❌ Full traceback: {str(e)}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        return False

def delete_existing_table(cur):
    """Delete existing technical_data_daily table and confirm deletion"""
    try:
        logging.info("🗑️ Step 1: Checking if technical_data_daily table exists...")
        
        # Check if table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'technical_data_daily'
            ) as table_exists
        """)
        result = cur.fetchone()
        table_exists = result['table_exists']
        
        if table_exists:
            logging.info("📊 technical_data_daily table exists, checking row count...")
            
            # Count existing rows
            cur.execute("SELECT COUNT(*) as row_count FROM technical_data_daily")
            result = cur.fetchone()
            existing_rows = result['row_count']
            logging.info(f"📊 Existing table has {existing_rows} rows")
            
            # Drop the table
            logging.info("🗑️ Dropping existing technical_data_daily table...")
            cur.execute("DROP TABLE IF EXISTS technical_data_daily CASCADE")
            logging.info("✅ Successfully dropped technical_data_daily table")
            
            # Verify deletion
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'technical_data_daily'
                ) as table_exists
            """)
            result = cur.fetchone()
            still_exists = result['table_exists']
            
            if still_exists:
                logging.error("❌ Table still exists after DROP command!")
                return False
            else:
                logging.info("✅ Confirmed: technical_data_daily table has been deleted")
                return True
        else:
            logging.info("📋 technical_data_daily table does not exist (first run)")
            return True
            
    except Exception as e:
        logging.error(f"❌ Failed to delete existing table: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        return False

def create_technical_table(cur):
    """Create technical_data_daily table with comprehensive schema"""
    try:
        logging.info("🔧 Creating technical_data_daily table...")
        
        create_table_sql = """
        CREATE TABLE technical_data_daily (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            
            -- Price data for reference
            open DECIMAL(12,4),
            high DECIMAL(12,4),
            low DECIMAL(12,4),
            close DECIMAL(12,4),
            volume BIGINT,
            
            -- Basic indicators
            rsi DECIMAL(8,4),
            mom DECIMAL(12,4),
            roc DECIMAL(8,4),
            
            -- Moving Averages
            sma_10 DECIMAL(12,4),
            sma_20 DECIMAL(12,4),
            sma_50 DECIMAL(12,4),
            sma_150 DECIMAL(12,4),
            sma_200 DECIMAL(12,4),
            ema_4 DECIMAL(12,4),
            ema_9 DECIMAL(12,4),
            ema_21 DECIMAL(12,4),
            
            -- MACD
            macd DECIMAL(12,6),
            macd_signal DECIMAL(12,6),
            macd_hist DECIMAL(12,6),
            
            -- Bollinger Bands
            bbands_lower DECIMAL(12,4),
            bbands_middle DECIMAL(12,4),
            bbands_upper DECIMAL(12,4),
            
            -- Other indicators
            atr DECIMAL(12,4),
            adx DECIMAL(8,4),
            ad DECIMAL(15,4),
            cmf DECIMAL(8,4),
            mfi DECIMAL(8,4),
            dm DECIMAL(8,4),
            marketwatch DECIMAL(8,4),
            
            -- Custom indicators
            td_sequential DECIMAL(8,2),
            td_combo DECIMAL(8,2),
            
            -- Pivot points
            pivot_high DECIMAL(12,4),
            pivot_low DECIMAL(12,4),
            
            -- Metadata
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(symbol, date)
        )
        """
        
        cur.execute(create_table_sql)
        logging.info("✅ Created technical_data_daily table")
        
        # Create indexes for performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_technical_daily_symbol ON technical_data_daily(symbol)",
            "CREATE INDEX IF NOT EXISTS idx_technical_daily_date ON technical_data_daily(date)",
            "CREATE INDEX IF NOT EXISTS idx_technical_daily_symbol_date ON technical_data_daily(symbol, date)",
            "CREATE INDEX IF NOT EXISTS idx_technical_daily_created_at ON technical_data_daily(created_at)"
        ]
        
        for index_sql in indexes:
            cur.execute(index_sql)
            index_name = index_sql.split(' ')[-1].split('(')[0]
            logging.info(f"✅ Created index: {index_name}")
        
        # Verify table creation
        cur.execute("""
            SELECT COUNT(*) as column_count 
            FROM information_schema.columns 
            WHERE table_name = 'technical_data_daily'
        """)
        result = cur.fetchone()
        column_count = result['column_count']
        logging.info(f"✅ Table created successfully with {column_count} columns")
        
        return True
        
    except Exception as e:
        logging.error(f"❌ Failed to create technical table: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        return False

def load_technicals_for_symbol(symbol, cur):
    """Load technical data for a single symbol with detailed logging"""
    try:
        logging.info(f"🔄 Processing symbol: {symbol}")
        
        # Fetch price data
        cur.execute("""
            SELECT date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol = %s
            ORDER BY date ASC
        """, (symbol,))
        
        rows = cur.fetchall()
        if not rows:
            logging.warning(f"⚠️ No price data found for {symbol}")
            return 0
        
        logging.info(f"📊 Retrieved {len(rows)} price records for {symbol}")
        
        # Convert to DataFrame
        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        logging.info(f"📊 Data range for {symbol}: {df.index.min()} to {df.index.max()}")
          # Calculate technical indicators
        df_tech = calculate_technicals_parallel(df)
        if df_tech is None:
            logging.warning(f"⚠️ Failed to calculate technicals for {symbol}")
            return 0        # Log final data quality for troubleshooting indicators
        key_indicators = ['mfi', 'ad', 'cmf', 'pivot_high', 'pivot_low', 'dm']
        for indicator in key_indicators:
            if indicator in df_tech.columns:
                valid_count = df_tech[indicator].count()
                total_count = len(df_tech)
                na_count = df_tech[indicator].isna().sum()
                logging.info(f"📊 {symbol} {indicator.upper()}: {valid_count}/{total_count} valid values ({valid_count/total_count*100:.1f}%), {na_count} NaN")
                
                # For failing indicators, show sample values
                if valid_count == 0:
                    logging.error(f"❌ {symbol} {indicator.upper()}: COMPLETELY FAILED - all values are NaN")
                elif valid_count < total_count * 0.1:  # Less than 10% valid
                    logging.warning(f"⚠️ {symbol} {indicator.upper()}: LOW SUCCESS RATE - only {valid_count/total_count*100:.1f}% valid")
                    sample_valid = df_tech[indicator].dropna().head(3)
                    if len(sample_valid) > 0:
                        logging.info(f"📊 {symbol} {indicator.upper()} valid sample: {sample_valid.tolist()}")
                else:
                    # Show sample of valid values for successful indicators
                    sample_valid = df_tech[indicator].dropna().head(3)
                    logging.info(f"📊 {symbol} {indicator.upper()} sample: {sample_valid.tolist()}")
            else:
                logging.error(f"❌ {symbol}: {indicator.upper()} column not found in calculated data")
        
        # Prepare data for insertion
        df_tech = df_tech.reset_index()
        df_tech['symbol'] = symbol
          # Select columns for database (includes all new indicators)
        columns = [
            'symbol', 'date', 'open', 'high', 'low', 'close', 'volume',
            'rsi', 'mom', 'roc', 'sma_10', 'sma_20', 'sma_50', 'sma_150', 'sma_200',
            'ema_4', 'ema_9', 'ema_21', 'macd', 'macd_signal', 'macd_hist',
            'bbands_lower', 'bbands_middle', 'bbands_upper', 'atr', 'adx',
            'ad', 'cmf', 'mfi', 'dm', 'marketwatch',
            'td_sequential', 'td_combo', 'pivot_high', 'pivot_low'
        ]
        
        # Filter to existing columns and replace NaN with None
        insert_data = []
        for _, row in df_tech.iterrows():
            row_data = []
            for col in columns:
                if col in df_tech.columns:
                    val = row[col]
                    row_data.append(None if pd.isna(val) else val)
                else:
                    row_data.append(None)
            insert_data.append(tuple(row_data))
        
        if not insert_data:
            logging.warning(f"⚠️ No data to insert for {symbol}")
            return 0        # Insert data with conflict resolution using execute_values
        # Note: execute_values expects a single %s placeholder that it will replace with VALUES
        insert_sql = f"""
            INSERT INTO technical_data_daily ({', '.join(columns)})
            VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                rsi = EXCLUDED.rsi,
                mom = EXCLUDED.mom,
                roc = EXCLUDED.roc,
                sma_10 = EXCLUDED.sma_10,
                sma_20 = EXCLUDED.sma_20,
                sma_50 = EXCLUDED.sma_50,
                sma_150 = EXCLUDED.sma_150,
                sma_200 = EXCLUDED.sma_200,
                ema_4 = EXCLUDED.ema_4,
                ema_9 = EXCLUDED.ema_9,
                ema_21 = EXCLUDED.ema_21,
                macd = EXCLUDED.macd,
                macd_signal = EXCLUDED.macd_signal,
                macd_hist = EXCLUDED.macd_hist,
                bbands_lower = EXCLUDED.bbands_lower,
                bbands_middle = EXCLUDED.bbands_middle,
                bbands_upper = EXCLUDED.bbands_upper,
                atr = EXCLUDED.atr,
                adx = EXCLUDED.adx,
                ad = EXCLUDED.ad,
                cmf = EXCLUDED.cmf,
                mfi = EXCLUDED.mfi,
                dm = EXCLUDED.dm,
                marketwatch = EXCLUDED.marketwatch,
                td_sequential = EXCLUDED.td_sequential,
                td_combo = EXCLUDED.td_combo,
                pivot_high = EXCLUDED.pivot_high,
                pivot_low = EXCLUDED.pivot_low,
                updated_at = CURRENT_TIMESTAMP
        """
        
        execute_values(cur, insert_sql, insert_data, page_size=1000)
        
        logging.info(f"✅ Loaded {len(insert_data)} technical records for {symbol}")
        return len(insert_data)
        
    except Exception as e:
        logging.error(f"❌ Failed to load technicals for {symbol}: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        return 0

def get_db_config():
    """Get database configuration from AWS Secrets Manager"""
    try:
        # Get the secret ARN from environment variable
        secret_arn = os.environ.get('DB_SECRET_ARN')
        if not secret_arn:
            raise ValueError("DB_SECRET_ARN environment variable not set")
        
        # Create a Secrets Manager client
        session = boto3.session.Session()
        client = session.client(service_name='secretsmanager', region_name='us-east-1')
        
        # Get the secret value
        response = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        
        return {
            'host': secret['host'],
            'port': secret['port'],
            'dbname': secret['dbname'],
            'user': secret['username'],
            'password': secret['password']
        }
    except Exception as e:
        logging.error(f"❌ Failed to get database configuration: {e}")
        raise

if __name__ == "__main__":
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

        # Step 1: Validate prerequisites
        logging.info("🔍 Validating prerequisites...")
        if not validate_prerequisites(cur):
            logging.error("❌ Prerequisites not met for loading technical data")
            sys.exit(1)
        
        logging.info("✅ Prerequisites validation passed!")
        
        # Step 2: Delete existing table
        logging.info("🗑️ Deleting existing technical table...")
        if not delete_existing_table(cur):
            logging.error("❌ Failed to delete existing technical table")
            sys.exit(1)
        
        # Step 3: Create new table
        logging.info("🔧 Creating new technical table...")
        if not create_technical_table(cur):
            logging.error("❌ Failed to create technical table")
            sys.exit(1)
        
        conn.commit()
        logging.info("💾 Table creation committed to database")
        
        # Step 4: Get symbols to process (limit for testing)
        logging.info("📋 Getting symbols to process...")
        cur.execute("SELECT DISTINCT symbol FROM price_daily ORDER BY symbol LIMIT 50")  # Start with 50 for testing
        symbols = [row['symbol'] for row in cur.fetchall()]
        logging.info(f"📊 Found {len(symbols)} symbols to process")
        
        if not symbols:
            logging.warning("⚠️ No symbols found to process")
            sys.exit(0)
        
        # Step 5: Process symbols
        total_records = 0
        successful_symbols = 0
        failed_symbols = []
        
        for i, symbol in enumerate(symbols, 1):
            logging.info(f"🔄 Processing {symbol} ({i}/{len(symbols)})...")
            
            try:
                records_inserted = load_technicals_for_symbol(symbol, cur)
                if records_inserted > 0:
                    successful_symbols += 1
                    total_records += records_inserted
                else:
                    failed_symbols.append(symbol)
                    
                # Commit every 10 symbols to avoid long transactions
                if i % 10 == 0:
                    conn.commit()
                    logging.info(f"💾 Committed batch at symbol {i}")
                    log_mem(f"after_symbol_{i}")
                    
            except Exception as e:
                logging.error(f"❌ Failed to process {symbol}: {e}")
                failed_symbols.append(symbol)
        
        # Final commit
        conn.commit()
        
        # Final summary
        logging.info("=" * 60)
        logging.info("📊 PROCESSING SUMMARY")
        logging.info("=" * 60)
        logging.info(f"✅ Successfully processed: {successful_symbols}/{len(symbols)} symbols")
        logging.info(f"📊 Total technical records inserted: {total_records}")
        logging.info(f"❌ Failed symbols: {len(failed_symbols)}")
        
        if failed_symbols:
            logging.info(f"❌ Failed symbol list: {', '.join(failed_symbols[:10])}{'...' if len(failed_symbols) > 10 else ''}")
        
        # Verify final table state
        cur.execute("SELECT COUNT(*) as final_count FROM technical_data_daily")
        result = cur.fetchone()
        final_count = result['final_count']
        logging.info(f"📊 Final table count: {final_count} records")
        
        cur.execute("SELECT COUNT(DISTINCT symbol) as symbol_count FROM technical_data_daily")
        result = cur.fetchone()
        symbol_count = result['symbol_count']
        logging.info(f"📊 Final symbol count: {symbol_count} symbols")
        
        # Close connections
        cur.close()
        conn.close()
        
        log_mem("final")
        logging.info("🏁 loadtechnicalsdaily.py finished")
        logging.info("✅ Process completed successfully")
        logging.info(f"🏁 {SCRIPT_NAME} finished with exit code 0")
        
    except Exception as e:
        logging.error(f"❌ Fatal error in main: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        sys.exit(1)

def test_pivot_functions():
    """Test pivot functions with sample data to debug the logic"""
    import pandas as pd
    import numpy as np
    
    # Create sample data that should have clear pivots
    # Pattern: 10, 12, 15, 18, 22, 20, 17, 15, 18, 21, 19, 16
    # Should have pivot high at index 4 (value 22) and pivot low at index 7 (value 15)
    sample_highs = pd.Series([10, 12, 15, 18, 22, 20, 17, 15, 18, 21, 19, 16])
    sample_lows = pd.Series([8, 10, 13, 16, 20, 18, 15, 13, 16, 19, 17, 14])
    
    print("🔧 Testing Pivot Functions with Sample Data")
    print(f"Sample highs: {sample_highs.tolist()}")
    print(f"Sample lows: {sample_lows.tolist()}")
    
    # Test pivot highs
    pivot_highs = pivot_high_vectorized(sample_highs, left_bars=3, right_bars=3)
    print(f"Pivot highs result: {pivot_highs.tolist()}")
    
    # Test pivot lows  
    pivot_lows = pivot_low_vectorized(sample_lows, left_bars=3, right_bars=3)
    print(f"Pivot lows result: {pivot_lows.tolist()}")
    
    # Count non-NaN values
    high_count = pivot_highs.count()
    low_count = pivot_lows.count()
    print(f"Found {high_count} pivot highs and {low_count} pivot lows")
    
    return pivot_highs, pivot_lows

# Uncomment the line below to test pivot functions locally
# test_pivot_functions()
