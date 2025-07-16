#!/usr/bin/env python3 
# Weekly technicals loader - deployment test v1 - updated to trigger workflow
import sys
import time
import logging
from datetime import datetime
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

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = os.path.basename(__file__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
    stream=sys.stdout
)

# Optimized for ECS - reduced workers to prevent memory issues
MAX_WORKERS = min(os.cpu_count() or 1, 2)  # Reduced from 4 to 2
BATCH_SIZE = 50  # Reduced from 100 to 50 for better memory management
DB_POOL_MIN = 1
DB_POOL_MAX = 5  # Reduced from 10 to 5

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
    """Fast ADX calculation"""
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

    # Drop and recreate technical_data_weekly table
    logging.info("Recreating technical_data_weekly table...")
    cursor.execute("DROP TABLE IF EXISTS technical_data_weekly;")
    cursor.execute("""
    CREATE TABLE technical_data_weekly (
        symbol          VARCHAR(50),
        date            TIMESTAMP,
        rsi             DOUBLE PRECISION,
        macd            DOUBLE PRECISION,
        macd_signal     DOUBLE PRECISION,
        macd_hist       DOUBLE PRECISION,
        mom             DOUBLE PRECISION,
        roc             DOUBLE PRECISION,
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
        pivot_high_triggered DOUBLE PRECISION,
        pivot_low_triggered DOUBLE PRECISION,
        fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """)
    logging.info("Table 'technical_data_weekly' ready.")
    
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
        
        cursor.execute("""
            SELECT date, open, high, low, close, volume
              FROM price_weekly
             WHERE symbol = %s
             ORDER BY date ASC
        """, (symbol,))
        rows = cursor.fetchall()
        
        if not rows:
            logging.warning(f"No data for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0

        # Initialize DataFrame with proper data handling
        df = pd.DataFrame(rows, columns=['date','open','high','low','close','volume'])
        df['date'] = pd.to_datetime(df['date'])
        
        # Ensure we have enough data for calculations
        if len(df) < 30:  # Need at least 30 bars for meaningful technical analysis
            logging.warning(f"Insufficient data for {symbol}: {len(df)} bars (need at least 30)")
            conn_pool.putconn(conn)
            return 0
        
        # Sort by date to ensure proper ordering
        df = df.sort_values('date').reset_index(drop=True)
        df.set_index('date', inplace=True)
        
        # Convert to float once for all calculations
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Handle missing data more carefully - only forward fill, then drop remaining NaN
        df = df.ffill().dropna()
        
        # Final check for sufficient data after cleaning
        if len(df) < 20:
            logging.warning(f"Insufficient data after cleaning for {symbol}: {len(df)} bars")
            conn_pool.putconn(conn)
            return 0

        # --- FAST INDICATORS CALCULATION ---
        # Calculate all indicators using fast native implementations
        
        # RSI
        df['rsi'] = fast_rsi(df['close'], period=14)

        # MACD - calculate once and reuse
        df['macd'], df['macd_signal'], df['macd_hist'] = fast_macd(df['close'])

        # Momentum indicators
        df['mom'] = df['close'] - df['close'].shift(10)  # 10-period momentum
        df['roc'] = ((df['close'] - df['close'].shift(10)) / df['close'].shift(10)) * 100  # 10-period ROC

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

        # Prepare batch data efficiently
        insert_q = """
        INSERT INTO technical_data_weekly (
          symbol, date,
          rsi, macd, macd_signal, macd_hist,
          mom, roc, adx, plus_di, minus_di, atr, ad, cmf, mfi,
          td_sequential, td_combo, marketwatch, dm,
          sma_10, sma_20, sma_50, sma_150, sma_200,
          ema_4, ema_9, ema_21,
          bbands_lower, bbands_middle, bbands_upper,
          pivot_high, pivot_low,
          pivot_high_triggered, pivot_low_triggered,
          fetched_at
        ) VALUES %s;
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
        
        # Free memory aggressively
        del df, data
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
