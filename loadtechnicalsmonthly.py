#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import gc
import resource
import math
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import boto3
import numpy as np
import pandas as pd
import pandas_ta as ta

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadtechnicalsmonthly.py"
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
# Technical indicators columns
# -------------------------------
TECHNICALS_COLUMNS = [
    "symbol", "date",
    "rsi", "macd", "macd_signal", "macd_hist",
    "mom", "roc", "adx", "plus_di", "minus_di", "atr", "ad", "cmf", "mfi",
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
    if pd.isna(x) or np.isinf(x):
        return None
    return float(x)

# -------------------------------
# Custom technical indicators
# -------------------------------
def pivot_high_vectorized(df, left_bars=3, right_bars=3):
    """Vectorized pivot high calculation"""
    series = df['high']
    roll_left = series.shift(1).rolling(window=left_bars, min_periods=left_bars).max()
    roll_right = series.shift(-1).rolling(window=right_bars, min_periods=right_bars).max()
    cond = (series > roll_left) & (series > roll_right)
    return series.where(cond, np.nan)

def pivot_low_vectorized(df, left_bars=3, right_bars=3):
    """Vectorized pivot low calculation"""
    series = df['low']
    roll_left = series.shift(1).rolling(window=left_bars, min_periods=left_bars).min()
    roll_right = series.shift(-1).rolling(window=right_bars, min_periods=right_bars).min()
    cond = (series < roll_left) & (series < roll_right)
    return series.where(cond, np.nan)

def td_sequential(close, lookback=4):
    """TD Sequential indicator"""
    count = np.zeros(len(close), dtype=np.float64)
    close_values = close.values
    
    for i in range(lookback, len(close)):
        if close_values[i] < close_values[i-lookback]:
            count[i] = count[i-1]+1 if count[i-1]>0 else 1
        elif close_values[i] > close_values[i-lookback]:
            count[i] = count[i-1]-1 if count[i-1]<0 else -1
    
    return pd.Series(count, index=close.index)

def td_combo(close, lookback=2):
    """TD Combo indicator"""
    count = np.zeros(len(close), dtype=np.float64)
    close_values = close.values
    
    for i in range(lookback, len(close)):
        if close_values[i] < close_values[i-lookback]:
            count[i] = count[i-1]+1 if count[i-1]>0 else 1
        elif close_values[i] > close_values[i-lookback]:
            count[i] = count[i-1]-1 if count[i-1]<0 else -1
    
    return pd.Series(count, index=close.index)

def marketwatch_indicator(close, open_):
    """MarketWatch momentum indicator"""
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

# -------------------------------
# Main technical indicators calculator
# -------------------------------
def calculate_technicals(df):
    """Calculate all technical indicators for a dataframe"""
    # Ensure proper data types
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Fill any gaps and drop NaN rows
    df = df.ffill().bfill().dropna()
    
    if len(df) < 200:  # Need minimum data for indicators
        logging.warning(f"Insufficient data: {len(df)} rows")
        return pd.DataFrame()
    
    # --- RSI ---
    df['rsi'] = ta.rsi(df['close'], length=14)
    
    # --- MACD ---
    ema_fast = df['close'].ewm(span=12, adjust=False).mean()
    ema_slow = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # --- Momentum indicators ---
    df['mom'] = ta.mom(df['close'], length=10)
    df['roc'] = ta.roc(df['close'], length=10)
    
    # --- ADX + DMI ---
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    if adx_df is not None and not adx_df.empty:
        df['adx'] = adx_df.iloc[:, 0]      # ADX
        df['plus_di'] = adx_df.iloc[:, 1]  # DMP
        df['minus_di'] = adx_df.iloc[:, 2] # DMN
    else:
        df[['adx', 'plus_di', 'minus_di']] = np.nan
    
    # --- Volume indicators ---
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    df['ad'] = ta.ad(df['high'], df['low'], df['close'], df['volume'])
    df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'], length=20)
    df['mfi'] = ta.mfi(df['high'], df['low'], df['close'], df['volume'], length=14)
    
    # --- Custom indicators ---
    df['td_sequential'] = td_sequential(df['close'], lookback=4)
    df['td_combo'] = td_combo(df['close'], lookback=2)
    df['marketwatch'] = marketwatch_indicator(df['close'], df['open'])
    
    # --- DM calculation ---
    dm_plus = df['high'].diff()
    dm_minus = df['low'].shift(1) - df['low']
    dm_plus = dm_plus.where((dm_plus>dm_minus)&(dm_plus>0), 0)
    dm_minus = dm_minus.where((dm_minus>dm_plus)&(dm_minus>0), 0)
    df['dm'] = dm_plus - dm_minus
    
    # --- Moving averages ---
    for period in [10, 20, 50, 150, 200]:
        df[f'sma_{period}'] = ta.sma(df['close'], length=period)
    
    for period in [4, 9, 21]:
        df[f'ema_{period}'] = ta.ema(df['close'], length=period)
    
    # --- Bollinger Bands ---
    bb = ta.bbands(df['close'], length=20, std=2)
    if bb is not None and not bb.empty:
        df['bbands_lower'] = bb.iloc[:, 0]   # BBL
        df['bbands_middle'] = bb.iloc[:, 1]  # BBM
        df['bbands_upper'] = bb.iloc[:, 2]   # BBU
    else:
        df[['bbands_lower', 'bbands_middle', 'bbands_upper']] = np.nan
    
    # --- Pivot points ---
    df_reset = df.reset_index()
    df['pivot_high'] = pivot_high_vectorized(df_reset, 3, 3).values
    df['pivot_low'] = pivot_low_vectorized(df_reset, 3, 3).values
    
    # Clean infinite values
    df = df.replace([np.inf, -np.inf], np.nan)
    
    return df

# -------------------------------
# Main loader with batched processing
# -------------------------------
def load_technicals(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading technical indicators for {total} symbols")
    inserted, failed = 0, []
    CHUNK_SIZE, PAUSE = 50, 0.1  # Process 50 symbols at a time
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        
        logging.info(f"Technical indicators – batch {batch_idx+1}/{batches}")
        log_mem(f"technicals batch {batch_idx+1} start")
        
        gc.disable()
        try:
            for symbol in batch:
                try:
                    # Fetch price data for this symbol
                    cur.execute("""
                        SELECT date, open, high, low, close, volume
                        FROM price_monthly
                        WHERE symbol = %s
                        ORDER BY date ASC
                    """, (symbol,))
                    
                    rows = cur.fetchall()
                    if not rows:
                        logging.warning(f"No price data for {symbol}, skipping")
                        continue
                    
                    # Convert to DataFrame
                    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                    
                    # Calculate technical indicators
                    df_tech = calculate_technicals(df.copy())
                    
                    if df_tech.empty:
                        logging.warning(f"Failed to calculate technicals for {symbol}")
                        failed.append(symbol)
                        continue
                    
                    # Prepare data for insertion
                    insert_data = []
                    for idx, row in df_tech.reset_index().iterrows():
                        insert_data.append((
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
                    
                    # Bulk insert using execute_values
                    if insert_data:
                        insert_query = """
                        INSERT INTO technical_data_monthly (
                            symbol, date,
                            rsi, macd, macd_signal, macd_hist,
                            mom, roc, adx, plus_di, minus_di, atr, ad, cmf, mfi,
                            td_sequential, td_combo, marketwatch, dm,
                            sma_10, sma_20, sma_50, sma_150, sma_200,
                            ema_4, ema_9, ema_21,
                            bbands_lower, bbands_middle, bbands_upper,
                            pivot_high, pivot_low,
                            fetched_at
                        ) VALUES %s
                        """
                        execute_values(cur, insert_query, insert_data, page_size=1000)
                        conn.commit()
                        inserted += 1
                        logging.info(f"✅ {symbol}: {len(insert_data)} technical indicators inserted")
                    
                    # Clean up memory
                    del df, df_tech, insert_data
                    
                except Exception as e:
                    logging.error(f"❌ {symbol}: Failed - {str(e)}")
                    failed.append(symbol)
                    conn.rollback()
                    continue
        
        finally:
            gc.enable()
        
        gc.collect()
        log_mem(f"technicals batch {batch_idx+1} end")
        time.sleep(PAUSE)

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
            id              SERIAL PRIMARY KEY,
            symbol          VARCHAR(10) NOT NULL,
            date            DATE        NOT NULL,
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
            fetched_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, date)
        );
    """)
    
    # Create indexes for performance
    cur.execute("""
        CREATE INDEX idx_technical_monthly_symbol ON technical_data_monthly(symbol);
        CREATE INDEX idx_technical_monthly_date ON technical_data_monthly(date);
        CREATE INDEX idx_technical_monthly_symbol_date ON technical_data_monthly(symbol, date);
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
