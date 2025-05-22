#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import gc
import resource

from datetime import datetime

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

import numpy as np
import pandas as pd
import pandas_ta as ta

# ───────────────────────────────────────────────────────────────────
# Patch for pandas_ta compatibility: ensure numpy exports NaN
np.NaN = np.nan
# ───────────────────────────────────────────────────────────────────

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = os.path.basename(__file__)
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
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host":     sec["host"],
        "port":     int(sec.get("port", 5432)),
        "user":     sec["username"],
        "password": sec["password"],
        "dbname":   sec["dbname"]
    }


# -------------------------------
# Utility functions & indicators
# -------------------------------
def sanitize_value(x):
    if isinstance(x, float) and np.isnan(x):
        return None
    return x

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


def main():
    log_mem("startup")
    logging.info(f"Starting {SCRIPT_NAME}")

    # ─── Connect to Postgres ─────────────────────────────────────
    cfg = get_db_config()
    try:
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
        logging.info("Connected to PostgreSQL database.")
    except Exception as e:
        logging.error(f"Unable to connect to Postgres: {e}")
        sys.exit(1)

    log_mem("after DB connect")

    # ─── Recreate tables ─────────────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS last_updated (
        script_name VARCHAR(255) PRIMARY KEY,
        last_run    TIMESTAMP
    );
    """)
    cur.execute("DROP TABLE IF EXISTS technical_data_daily;")
    cur.execute("""
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
        PRIMARY KEY (symbol, date)
    );
    """)
    conn.commit()
    logging.info("Recreated tables.")
    log_mem("after table setup")

    # ─── Fetch symbols ────────────────────────────────────────────
    cur.execute("SELECT symbol FROM stock_symbols;")
    symbols = [r["symbol"] for r in cur.fetchall()]
    logging.info(f"Found {len(symbols)} symbols to process.")
    log_mem("after symbol fetch")

    # ─── Prepare insert statement ─────────────────────────────────
    cols = [
        "symbol","date",
        "rsi","macd","macd_signal","macd_hist",
        "mom","roc","adx","plus_di","minus_di","atr","ad","cmf","mfi",
        "td_sequential","td_combo","marketwatch","dm",
        "sma_10","sma_20","sma_50","sma_150","sma_200",
        "ema_4","ema_9","ema_21",
        "bbands_lower","bbands_middle","bbands_upper",
        "pivot_high","pivot_low"
    ]
    insert_sql = f"INSERT INTO technical_data_daily ({', '.join(cols)}) VALUES %s"

    start = time.time()
    total_rows = 0

    for sym in symbols:
        logging.info(f"── Processing {sym} ──")
        log_mem(f"{sym} start")

        # Fetch price data
        cur.execute("""
            SELECT date, open, high, low, close, volume
              FROM price_data_daily
             WHERE symbol = %s
             ORDER BY date ASC
        """, (sym,))
        data = cur.fetchall()
        if not data:
            logging.warning(f"No price data for {sym}, skipping.")
            continue

        # Build DataFrame
        df = pd.DataFrame(data, columns=['date','open','high','low','close','volume'])
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df = df.astype(float).ffill().bfill().dropna()
        log_mem(f"{sym} df ready")

        # ─ Indicators ─
        df['rsi'] = ta.rsi(df['close'], length=14)

        ema_fast = df['close'].ewm(span=12, adjust=False).mean()
        ema_slow = df['close'].ewm(span=26, adjust=False).mean()
        df['macd']        = ema_fast - ema_slow
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist']   = df['macd'] - df['macd_signal']

        df['mom'] = ta.mom(df['close'], length=10)
        df['roc'] = ta.roc(df['close'], length=10)

        adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
        if adx_df is not None:
            df['adx']      = adx_df['ADX_14']
            df['plus_di']  = adx_df['DMP_14']
            df['minus_di'] = adx_df['DMN_14']
        else:
            df[['adx','plus_di','minus_di']] = np.nan

        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['ad']  = ta.ad(df['high'], df['low'], df['close'], df['volume'])
        df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'], length=20)

        mfi_vals = ta.mfi(df['high'], df['low'], df['close'], df['volume'], length=14)
        if 'mfi' in df.columns: df.drop(columns=['mfi'], inplace=True)
        df['mfi'] = pd.Series(mfi_vals, index=df.index, dtype='float64')

        df['td_sequential'] = td_sequential(df['close'], lookback=4)
        df['td_combo']      = td_combo(df['close'], lookback=2)
        df['marketwatch']   = marketwatch_indicator(df['close'], df['open'])

        dm_plus  = df['high'].diff()
        dm_minus = df['low'].shift(1) - df['low']
        dm_plus  = dm_plus.where((dm_plus>dm_minus)&(dm_plus>0), 0)
        dm_minus = dm_minus.where((dm_minus>dm_plus)&(dm_minus>0), 0)
        df['dm'] = dm_plus - dm_minus

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

        reset = df.reset_index()
        df['pivot_high'] = pivot_high_vectorized(reset,3,3).values
        df['pivot_low']  = pivot_low_vectorized(reset,3,3).values
        log_mem(f"{sym} indicators computed")

        # ─ Data cleaning & batch insert ─
        df = df.replace([np.inf, -np.inf], np.nan).where(pd.notnull(df), None)
        rows_to_insert = []
        for _, row in df.reset_index().iterrows():
            rows_to_insert.append((
                sym,
                row['date'].to_pydatetime(),
                sanitize_value(row['rsi']),
                sanitize_value(row['macd']),
                sanitize_value(row['macd_signal']),
                sanitize_value(row['macd_hist']),
                sanitize_value(row['mom']),
                sanitize_value(row['roc']),
                sanitize_value(row['adx']),
                sanitize_value(row['plus_di']),
                sanitize_value(row['minus_di']),
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
            ))
        if not rows_to_insert:
            logging.warning(f"{sym}: no valid rows after cleaning, skipping insert.")
            continue

        log_mem(f"{sym} insert start")
        gc.disable()
        try:
            execute_values(cur, insert_sql, rows_to_insert, page_size=500)
            conn.commit()
            total_rows += len(rows_to_insert)
            logging.info(f"{sym}: inserted {len(rows_to_insert)} rows.")
        finally:
            gc.enable()

        # cleanup per-symbol
        del df, rows_to_insert
        gc.collect()
        log_mem(f"{sym} insert end")

    elapsed = time.time() - start
    logging.info(f"All symbols processed in {elapsed:.2f} seconds, total rows inserted: {total_rows}")
    log_mem("after all processing")

    # ─── Stamp last run ───────────────────────────────────────────
    now = datetime.now()
    cur.execute("""
    INSERT INTO last_updated (script_name, last_run)
    VALUES (%s, %s)
    ON CONFLICT (script_name) DO UPDATE
      SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME, now))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")

    cur.close()
    conn.close()
    logging.info("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Unhandled error in script")
        sys.exit(1)
