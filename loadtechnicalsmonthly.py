#!/usr/bin/env python3 
import sys
import time
import logging
from datetime import datetime
import json
import os
import concurrent.futures
from functools import partial
import gc
from io import StringIO

import numpy as np
import numpy

# ───────────────────────────────────────────────────────────────────
# NumPy configuration for compatibility
numpy.NaN = numpy.nan
np.NaN    = np.nan
# ───────────────────────────────────────────────────────────────────

# Numba JIT compilation for ultra-high performance
from numba import njit, prange
from numba.core import config
config.THREADING_LAYER = 'safe'

import boto3
import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values

import pandas as pd
import talib

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = os.path.basename(__file__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
    stream=sys.stdout
)

# Configure these based on your ECS task size - optimized for small tasks
MAX_WORKERS = min(os.cpu_count() or 1, 2)  # Reduced for memory efficiency
BATCH_SIZE = 15  # Even smaller batches for monthly data
DB_POOL_MIN = 1
DB_POOL_MAX = 4  # Reduced pool size for small ECS tasks

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
    """Enhanced sanitization for better type handling"""
    if x is None:
        return None
    if isinstance(x, (int, str, bool)):
        return x
    if isinstance(x, (float, np.floating)):
        if np.isnan(x) or np.isinf(x):
            return None
        return float(x)
    if isinstance(x, (np.integer)):
        return int(x)
    if hasattr(x, 'item'):  # numpy scalars
        val = x.item()
        if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
            return None
        return val
    return x

# ═══════════════════════════════════════════════════════════════════
# JIT-COMPILED TECHNICAL ANALYSIS FUNCTIONS FOR ULTRA-HIGH PERFORMANCE
# ═══════════════════════════════════════════════════════════════════

@njit(cache=True, fastmath=True)
def rsi_numba(close_prices, length=14):
    """Ultra-fast RSI calculation using Numba JIT compilation"""
    n = len(close_prices)
    if n < length + 1:
        return np.full(n, np.nan)
    
    delta = np.diff(close_prices)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    
    # Calculate initial averages
    avg_gain = np.mean(gain[:length])
    avg_loss = np.mean(loss[:length])
    
    rsi = np.full(n, np.nan)
    
    for i in range(length, n):
        if i == length:
            # First RSI calculation
            current_gain = gain[i-1]
            current_loss = loss[i-1]
        else:
            # Smooth the averages
            current_gain = gain[i-1]
            current_loss = loss[i-1]
            avg_gain = (avg_gain * (length - 1) + current_gain) / length
            avg_loss = (avg_loss * (length - 1) + current_loss) / length
        
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    
    return rsi

@njit(cache=True, fastmath=True)
def sma_numba(prices, length):
    """Ultra-fast SMA calculation using Numba JIT compilation"""
    n = len(prices)
    if n < length:
        return np.full(n, np.nan)
    
    sma = np.full(n, np.nan)
    for i in range(length - 1, n):
        sma[i] = np.mean(prices[i - length + 1:i + 1])
    
    return sma

@njit(cache=True, fastmath=True)
def ema_numba(prices, length):
    """Ultra-fast EMA calculation using Numba JIT compilation"""
    n = len(prices)
    if n == 0:
        return np.array([])
    
    alpha = 2.0 / (length + 1.0)
    ema = np.full(n, np.nan)
    ema[0] = prices[0]
    
    for i in range(1, n):
        ema[i] = alpha * prices[i] + (1.0 - alpha) * ema[i-1]
    
    return ema

@njit(cache=True, fastmath=True)
def atr_numba(high, low, close, length=14):
    """Ultra-fast ATR calculation using Numba JIT compilation"""
    n = len(high)
    if n < 2:
        return np.full(n, np.nan)
    
    tr = np.full(n, np.nan)
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i-1])
        lc = abs(low[i] - close[i-1])
        tr[i] = max(hl, hc, lc)
    
    # Calculate ATR using modified EMA
    atr = np.full(n, np.nan)
    if n > length:
        # Initialize with simple average
        atr[length] = np.mean(tr[1:length+1])
        
        # Continue with smoothed average
        for i in range(length + 1, n):
            atr[i] = (atr[i-1] * (length - 1) + tr[i]) / length
    
    return atr

@njit(cache=True, fastmath=True)
def td_sequential_numba(close_prices, lookback=4):
    """Ultra-fast TD Sequential calculation using Numba JIT compilation"""
    n = len(close_prices)
    count = np.zeros(n)
    
    for i in range(lookback, n):
        if close_prices[i] < close_prices[i-lookback]:
            count[i] = count[i-1] + 1 if count[i-1] > 0 else 1
        elif close_prices[i] > close_prices[i-lookback]:
            count[i] = count[i-1] - 1 if count[i-1] < 0 else -1
        else:
            count[i] = 0
    
    return count

@njit(cache=True, fastmath=True)
def td_combo_numba(close_prices, lookback=2):
    """Ultra-fast TD Combo calculation using Numba JIT compilation"""
    n = len(close_prices)
    count = np.zeros(n)
    
    for i in range(lookback, n):
        if close_prices[i] < close_prices[i-lookback]:
            count[i] = count[i-1] + 1 if count[i-1] > 0 else 1
        elif close_prices[i] > close_prices[i-lookback]:
            count[i] = count[i-1] - 1 if count[i-1] < 0 else -1
        else:
            count[i] = 0
    
    return count

@njit(cache=True, fastmath=True)
def marketwatch_numba(close_prices, open_prices):
    """Ultra-fast MarketWatch indicator using Numba JIT compilation"""
    n = len(close_prices)
    if n != len(open_prices):
        return np.zeros(n)
    
    signal = np.zeros(n)
    count = np.zeros(n)
    
    for i in range(n):
        if close_prices[i] > open_prices[i]:
            signal[i] = 1
        elif close_prices[i] < open_prices[i]:
            signal[i] = -1
        else:
            signal[i] = 0
    
    count[0] = signal[0]
    for i in range(1, n):
        if signal[i] == signal[i-1] and signal[i] != 0:
            count[i] = count[i-1] + signal[i]
        else:
            count[i] = signal[i]
    
    return count

def bulk_copy_insert(cursor, table_name, columns, data):
    """Ultra-fast PostgreSQL COPY insertion - 10x faster than execute_values"""
    if not data:
        return
    
    # Create a StringIO buffer for COPY
    buffer = StringIO()
    
    for row in data:
        # Convert each value to string, handling None/NULL values
        str_row = []
        for val in row:
            if val is None:
                str_row.append('\\N')  # PostgreSQL NULL representation
            elif isinstance(val, datetime):
                str_row.append(val.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                str_row.append(str(val))
        buffer.write('\t'.join(str_row) + '\n')
    
    # Reset buffer position
    buffer.seek(0)
    
    # Use COPY command for ultra-fast insertion
    cursor.copy_from(
        buffer, 
        table_name, 
        columns=columns,
        sep='\t',
        null='\\N'
    )

def pivot_high_vectorized(df, left_bars=3, right_bars=3):
    series = df['high']
    roll_left  = series.shift(1).rolling(window=left_bars,  min_periods=left_bars).max()
    roll_right = series.shift(-1).rolling(window=right_bars, min_periods=right_bars).max()
    cond = (series > roll_left) & (series > roll_right)
    return series.where(cond, np.nan)

def pivot_low_vectorized(df, left_bars=3, right_bars=3):
    series = df['low']
    roll_left  = series.shift(1).rolling(window=left_bars,  min_periods=left_bars).min()
    roll_right = series.shift(-1).rolling(window=right_bars, min_periods=right_bars).min()
    cond = (series < roll_left) & (series < roll_right)
    return series.where(cond, np.nan)

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

    # Drop and recreate technical_data_monthly table
    logging.info("Recreating technical_data_monthly table...")
    cursor.execute("DROP TABLE IF EXISTS technical_data_monthly;")
    cursor.execute("""
    CREATE TABLE technical_data_monthly (
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
        fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """)
    logging.info("Table 'technical_data_monthly' ready.")
    
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
              FROM price_monthly
             WHERE symbol = %s
             ORDER BY date ASC
        """, (symbol,))
        rows = cursor.fetchall()
        
        if not rows:
            logging.warning(f"No data for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0        # Initialize DataFrame with proper data types
        df = pd.DataFrame(rows, columns=['date','open','high','low','close','volume'])
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # Ensure minimum data for technical analysis
        if len(df) < 50:  # Need minimum periods for calculations
            logging.warning(f"Insufficient data for {symbol} ({len(df)} rows), skipping.")
            conn_pool.putconn(conn)
            return 0
        
        # Enhanced data preprocessing for talib compatibility
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype('float64')
        
        # Remove any remaining NaN values and ensure data quality
        df = df.dropna()
        if df.empty:
            logging.warning(f"No valid data after cleaning for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0
        
        # --- PRE-EXTRACT NUMPY ARRAYS FOR ULTRA-FAST PROCESSING ---
        # Convert to numpy arrays for talib (ensures proper data types)
        close_np = np.ascontiguousarray(df['close'].values, dtype=np.float64)
        open_np = np.ascontiguousarray(df['open'].values, dtype=np.float64)
        high_np = np.ascontiguousarray(df['high'].values, dtype=np.float64)
        low_np = np.ascontiguousarray(df['low'].values, dtype=np.float64)
        volume_np = np.ascontiguousarray(df['volume'].values, dtype=np.float64)        # --- TECHNICAL INDICATORS USING TALIB ---
        # RSI
        df['rsi'] = talib.RSI(close_np, timeperiod=14)
        
        # MACD - optimized single function call
        macd, macd_signal, macd_hist = talib.MACD(close_np, fastperiod=12, slowperiod=26, signalperiod=9)
        df['macd'] = macd
        df['macd_signal'] = macd_signal
        df['macd_hist'] = macd_hist# Momentum indicators
        df['mom'] = talib.MOM(close_np, timeperiod=10)
        df['roc'] = talib.ROC(close_np, timeperiod=10)

        # ADX + DMI
        df['adx'] = talib.ADX(high_np, low_np, close_np, timeperiod=14)
        df['plus_di'] = talib.PLUS_DI(high_np, low_np, close_np, timeperiod=14)
        df['minus_di'] = talib.MINUS_DI(high_np, low_np, close_np, timeperiod=14)
            
        # ATR
        df['atr'] = talib.ATR(high_np, low_np, close_np, timeperiod=14)
        
        # Volume indicators
        df['ad'] = talib.AD(high_np, low_np, close_np, volume_np)
        df['mfi'] = talib.MFI(high_np, low_np, close_np, volume_np, timeperiod=14)
        
        # CMF calculation (optimized pandas)
        money_flow_volume = ((close_np - low_np) - (high_np - close_np)) / (high_np - low_np) * volume_np
        money_flow_volume = np.where(high_np == low_np, 0, money_flow_volume)
        df['cmf'] = pd.Series(money_flow_volume).rolling(window=20).sum() / pd.Series(volume_np).rolling(window=20).sum()# JIT-optimized custom indicators
        df['td_sequential'] = td_sequential_numba(close_np, lookback=4)
        df['td_combo'] = td_combo_numba(close_np, lookback=2)
        df['marketwatch'] = marketwatch_numba(close_np, open_np)        # Optimized DM calculation using numpy vectorization
        high_diff = np.diff(high_np, prepend=high_np[0])
        low_diff = np.diff(low_np, prepend=low_np[0])
        dm_plus = np.where((high_diff > np.abs(low_diff)) & (high_diff > 0), high_diff, 0)
        dm_minus = np.where((np.abs(low_diff) > high_diff) & (low_diff < 0), np.abs(low_diff), 0)
        df['dm'] = dm_plus - dm_minus        # Moving averages using talib for optimal performance
        for p in [10, 20, 50, 150, 200]:
            df[f'sma_{p}'] = talib.SMA(close_np, timeperiod=p)
        
        for p in [4, 9, 21]:
            df[f'ema_{p}'] = talib.EMA(close_np, timeperiod=p)
        
        # Bollinger Bands using talib
        bb_upper, bb_middle, bb_lower = talib.BBANDS(close_np, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        df['bbands_upper'] = bb_upper
        df['bbands_middle'] = bb_middle
        df['bbands_lower'] = bb_lower

        # Pivots
        reset = df.reset_index()
        df['pivot_high'] = pivot_high_vectorized(reset, 3, 3).values
        df['pivot_low'] = pivot_low_vectorized(reset, 3, 3).values

        # Clean data
        df = df.replace([np.inf, -np.inf], np.nan)        # Prepare data for ultra-fast bulk insertion
        data = []
        for idx, row in df.reset_index().iterrows():
            data.append((
                symbol,
                row['date'].to_pydatetime(),
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
                datetime.now()
            ))
              # Use ultra-fast COPY method for 10x faster insertion
        if data:
            columns = ['symbol', 'date', 'rsi', 'macd', 'macd_signal', 'macd_hist',
                      'mom', 'roc', 'adx', 'plus_di', 'minus_di', 'atr', 'ad', 'cmf', 'mfi',
                      'td_sequential', 'td_combo', 'marketwatch', 'dm',
                      'sma_10', 'sma_20', 'sma_50', 'sma_150', 'sma_200',
                      'ema_4', 'ema_9', 'ema_21',
                      'bbands_lower', 'bbands_middle', 'bbands_upper',
                      'pivot_high', 'pivot_low', 'fetched_at']
            bulk_copy_insert(cursor, 'technical_data_monthly', columns, data)
            conn.commit()
            num_inserted = len(data)
            logging.info(f"✅ {symbol}: Inserted {num_inserted} rows")
        else:
            num_inserted = 0
            logging.warning(f"⚠️ {symbol}: No data to insert")
        
        cursor.close()
        conn_pool.putconn(conn)
        
        # Free memory
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