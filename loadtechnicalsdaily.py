#!/usr/bin/env python3
import sys
import time
import logging
from datetime import datetime
import json
import os

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np
import pandas as pd
import pandas_ta as ta
 
# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadtechnicaldaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
 
# -------------------------------
# Environment-driven configuration
# -------------------------------
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]

def get_db_config():
    """
    Fetch host, port, dbname, username & password from Secrets Manager.
    SecretString must be JSON with keys: username, password, host, port, dbname.
    """
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"]
    )

# -------------------------------
# Start up & connect
# -------------------------------
logging.info(f"Starting {SCRIPT_NAME}")
DB_USER, DB_PWD, DB_HOST, DB_PORT, DB_NAME = get_db_config()

try:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PWD,
        dbname=DB_NAME
    )
    conn.autocommit = True
    cursor = conn.cursor()
    logging.info("Connected to PostgreSQL database.")
except Exception as e:
    logging.error(f"Unable to connect to Postgres: {e}")
    sys.exit(1)

# -------------------------------
# Ensure last_updated table exists
# -------------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(255) PRIMARY KEY,
    last_run    TIMESTAMP
);
""")

# -------------------------------
# Recreate technical_data_daily table
# -------------------------------
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
    fib_0           DOUBLE PRECISION,
    fib_236         DOUBLE PRECISION,
    fib_382         DOUBLE PRECISION,
    fib_50          DOUBLE PRECISION,
    fib_618         DOUBLE PRECISION,
    fib_100         DOUBLE PRECISION,
    PRIMARY KEY (symbol, date)
);
""")
logging.info("Table 'technical_data_daily' ready.")

# -------------------------------
# Utility to sanitize NaNs -> None
# -------------------------------
def sanitize_value(x):
    if isinstance(x, float) and np.isnan(x):
        return None
    return x

# -------------------------------
# Load Symbols
# -------------------------------
cursor.execute("SELECT symbol FROM stock_symbols;")
symbols = [row[0] for row in cursor.fetchall()]
logging.info(f"Found {len(symbols)} symbols.")

# -------------------------------
# Insert template
# -------------------------------
insert_query = """
INSERT INTO technical_data_daily (
    symbol, date,
    rsi, macd, macd_signal, macd_hist,
    mom, roc, adx, atr, ad, cmf, mfi,
    td_sequential, td_combo, marketwatch,
    dm,
    sma_10, sma_20, sma_50, sma_150, sma_200,
    ema_4, ema_9, ema_21,
    bbands_lower, bbands_middle, bbands_upper,
    pivot_high, pivot_low,
    fib_0, fib_236, fib_382, fib_50, fib_618, fib_100
) VALUES (
    %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s,
    %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s,
    %s, %s,
    %s, %s, %s, %s, %s, %s
)
"""

# -------------------------------
# Indicator helpers
# -------------------------------
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
    count = [0]*len(close)
    for i in range(lookback, len(close)):
        if close.iloc[i] < close.iloc[i-lookback]:
            count[i] = count[i-1]+1 if count[i-1]>0 else 1
        elif close.iloc[i] > close.iloc[i-lookback]:
            count[i] = count[i-1]-1 if count[i-1]<0 else -1
        else:
            count[i] = 0
    return pd.Series(count, index=close.index)

def td_combo(close, lookback=2):
    count = [0]*len(close)
    for i in range(lookback, len(close)):
        if close.iloc[i] < close.iloc[i-lookback]:
            count[i] = count[i-1]+1 if count[i-1]>0 else 1
        elif close.iloc[i] > close.iloc[i-lookback]:
            count[i] = count[i-1]-1 if count[i-1]<0 else -1
        else:
            count[i] = 0
    return pd.Series(count, index=close.index)

def marketwatch_indicator(close, open_):
    signal = (close > open_).astype(int) - (close < open_).astype(int)
    count  = [0]*len(signal)
    count[0] = signal.iloc[0]
    for i in range(1, len(signal)):
        if signal.iloc[i]==signal.iloc[i-1] and signal.iloc[i]!=0:
            count[i] = count[i-1] + signal.iloc[i]
        else:
            count[i] = signal.iloc[i]
    return pd.Series(count, index=close.index)

# -------------------------------
# Main processing loop
# -------------------------------
total_start = time.time()
for symbol in symbols:
    logging.info(f"Processing symbol: {symbol}")
    cursor.execute("""
        SELECT date, open, high, low, close, volume
          FROM price_data_daily
         WHERE symbol = %s
         ORDER BY date ASC
    """, (symbol,))
    rows = cursor.fetchall()
    if not rows:
        logging.warning(f"No daily data for {symbol}, skipping.")
        continue

    df = pd.DataFrame(rows, columns=['date','open','high','low','close','volume'])
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df.astype({'open':'float','high':'float','low':'float','close':'float','volume':'float'})
    df.ffill().bfill().dropna(subset=['open','high','low','close','volume'], inplace=True)

    # compute indicators...
    df['rsi'] = ta.rsi(df['close'], length=14)
    ema_fast = df['close'].ewm(span=12, adjust=False).mean()
    ema_slow = df['close'].ewm(span=26, adjust=False).mean()
    df['macd']        = ema_fast - ema_slow
    df['macd_signal'] = df['macd'].ewm(span=9,  adjust=False).mean()
    df['macd_hist']   = df['macd'] - df['macd_signal']
    df['mom'] = ta.mom(df['close'], length=10)
    df['roc'] = ta.roc(df['close'], length=10)
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    df['adx'] = adx_df['ADX_14'] if adx_df is not None else np.nan
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    df['ad']  = ta.ad(df['high'], df['low'], df['close'], df['volume'])
    df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'], length=20)
    df['mfi'] = np.array(ta.mfi(df['high'], df['low'], df['close'], df['volume'], length=14), dtype=np.float64)
    df['td_sequential'] = td_sequential(df['close'],  lookback=4)
    df['td_combo']      = td_combo(df['close'],       lookback=2)
    df['marketwatch']   = marketwatch_indicator(df['close'], df['open'])
    df['dm_plus']  = df['high'].diff()
    df['dm_minus'] = df['low'].shift(1) - df['low']
    df['dm_plus']  = df['dm_plus'].where((df['dm_plus']>df['dm_minus'])&(df['dm_plus']>0), 0)
    df['dm_minus'] = df['dm_minus'].where((df['dm_minus']>df['dm_plus'])&(df['dm_minus']>0), 0)
    df['dm'] = df['dm_plus'] - df['dm_minus']
    for p in [10,20,50,150,200]:
        df[f'sma_{p}'] = ta.sma(df['close'], length=p)
    for p in [4,9,21]:
        df[f'ema_{p}'] = ta.ema(df['close'], length=p)
    bb = ta.bbands(df['close'], length=20, std=2)
    if bb is not None:
        df['bbands_lower']  = bb['BBL_20_2.0']
        df['bbands_middle'] = bb['BBM_20_2.0']
        df['bbands_upper']  = bb['BBU_20_2.0']
    else:
        df[['bbands_lower','bbands_middle','bbands_upper']] = np.nan
    df_reset = df.reset_index()
    df['pivot_high'] = pivot_high_vectorized(df_reset, 3, 3).values
    df['pivot_low']  = pivot_low_vectorized(df_reset,  3, 3).values
    hi, lo = df['high'].max(), df['low'].min()
    rng = hi - lo
    df['fib_0']   = hi
    df['fib_236'] = hi - 0.236 * rng
    df['fib_382'] = hi - 0.382 * rng
    df['fib_50']  = hi - 0.5   * rng
    df['fib_618'] = hi - 0.618 * rng
    df['fib_100'] = lo

    df = df.replace([np.inf, -np.inf], np.nan).where(pd.notnull(df), None)

    data_tuples = []
    for _, row in df.reset_index().iterrows():
        data_tuples.append((
            symbol,
            row['date'].to_pydatetime(),
            sanitize_value(row['rsi']),
            sanitize_value(row['macd']),
            sanitize_value(row['macd_signal']),
            sanitize_value(row['macd_hist']),
            sanitize_value(row['mom']),
            sanitize_value(row['roc']),
            sanitize_value(row['adx']),
            sanitize_value(row['atr']),
            sanitize_value(row['ad']),
            sanitize_value(row['cmf']),
            sanitize_value(row['mfi']),
            sanitize_value(row['td_sequential']),
            sanitize_value(row['td_combo']),
            sanitize_value(row['marketwatch']),
            sanitize_value(row['dm']),
            sanitize_value(row['sma_10']),
            sanitize_value(row['sma_20']),
            sanitize_value(row['sma_50']),
            sanitize_value(row['sma_150']),
            sanitize_value(row['sma_200']),
            sanitize_value(row['ema_4']),
            sanitize_value(row['ema_9']),
            sanitize_value(row['ema_21']),
            sanitize_value(row['bbands_lower']),
            sanitize_value(row['bbands_middle']),
            sanitize_value(row['bbands_upper']),
            sanitize_value(row['pivot_high']),
            sanitize_value(row['pivot_low']),
            sanitize_value(row['fib_0']),
            sanitize_value(row['fib_236']),
            sanitize_value(row['fib_382']),
            sanitize_value(row['fib_50']),
            sanitize_value(row['fib_618']),
            sanitize_value(row['fib_100']),
        ))
    if data_tuples:
        cursor.executemany(insert_query, data_tuples)
        logging.info(f"Inserted {len(data_tuples)} rows for {symbol}.")

total_elapsed = time.time() - total_start
logging.info(f"All symbols processed in {total_elapsed:.2f} seconds.")

# -------------------------------
# Stamp last_updated
# -------------------------------
now = datetime.now()
cursor.execute("""
INSERT INTO last_updated (script_name, last_run)
VALUES (%s, %s)
ON CONFLICT (script_name) DO UPDATE
  SET last_run = EXCLUDED.last_run;
""", (SCRIPT_NAME, now))

cursor.close()
conn.close()
logging.info("Done.")
