#!/usr/bin/env python3
"""
Range Trading Signals Loader
Detects price ranges and generates buy/sell signals at support/resistance with TD Setup confirmation.
Uses DeMark indicators for signal timing and quality.
"""

import os
import sys
import json
import pandas as pd
import numpy as np
import boto3
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
import logging
from pathlib import Path
from dotenv import load_dotenv

# Import DeMark helper
try:
    from demark_indicators import compute_all_td_indicators
except ImportError:
    logging.error("Failed to import demark_indicators module")
    sys.exit(1)

# Load environment
env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

SCRIPT_NAME = "loadrangesignals.py"

# Logging
import tempfile
from logging.handlers import RotatingFileHandler
log_path = os.path.join(tempfile.gettempdir(), 'loadrangesignals.log')
log_handler = RotatingFileHandler(log_path, maxBytes=100*1024*1024, backupCount=3)
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), log_handler]
)

# Database config
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN")
DB_HOST = None
DB_PORT = None
DB_USER = None
DB_PASSWORD = None
DB_NAME = None

if DB_SECRET_ARN:
    try:
        sm_client = boto3.client("secretsmanager")
        secret_resp = sm_client.get_secret_value(SecretId=DB_SECRET_ARN)
        creds = json.loads(secret_resp["SecretString"])
        DB_USER = creds["username"]
        DB_PASSWORD = creds["password"]
        DB_HOST = creds["host"]
        DB_PORT = int(creds.get("port", 5432))
        DB_NAME = creds["dbname"]
        logging.info("Using AWS Secrets Manager")
    except Exception as e:
        logging.warning(f"AWS Secrets Manager failed: {e}")
        DB_SECRET_ARN = None

if not DB_SECRET_ARN or DB_HOST is None:
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_USER = os.environ.get("DB_USER", "stocks")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_PORT = int(os.environ.get("DB_PORT", 5432))
    DB_NAME = os.environ.get("DB_NAME", "stocks")
    logging.info("Using environment variables for database config")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        options='-c statement_timeout=600000'
    )

def get_symbols_from_db(limit=None):
    """Get all symbols from database"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        q = "SELECT symbol FROM stock_symbols ORDER BY symbol"
        if limit:
            q += f" LIMIT {limit}"
        cur.execute(q)
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

def get_price_data(symbol, lookback_days=120):
    """Fetch price data from price_daily table"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        q = """
            SELECT symbol, date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol = %s AND date >= NOW() - INTERVAL '%d days'
            ORDER BY date ASC
        """ % (lookback_days,)
        cur.execute(q, (symbol,))
        rows = cur.fetchall()

        if not rows:
            return None

        df = pd.DataFrame(
            rows,
            columns=['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']
        )
        df['date'] = pd.to_datetime(df['date'])
        return df
    finally:
        cur.close()
        conn.close()

def detect_range(df):
    """
    Detect if price is in a range.
    Rules:
    - max(close[-20:]) / min(close[-20:]) - 1 < 0.10 (less than 10% spread)
    - ATR(14) < ATR(50) * 0.85 (volatility contracted)
    - range_height > 2 * ATR (meaningful range)
    Returns: (is_ranging, range_high, range_low, range_position, range_age_days, range_strength)
    """
    if len(df) < 50:
        return None

    # Last 20 bars
    recent = df.tail(20)
    range_high = recent['high'].max()
    range_low = recent['low'].max()

    range_height = range_high - range_low
    close_current = df['close'].iloc[-1]

    # ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr_14 = tr.rolling(14).mean().iloc[-1]
    atr_50 = tr.rolling(50).mean().iloc[-1]

    # Range spread check
    if range_height == 0:
        return None
    spread = (range_high / range_low) - 1
    if spread >= 0.10:
        return None  # Too wide

    # Volatility contraction check
    if atr_50 == 0 or atr_14 > atr_50 * 0.85:
        return None  # Not contracted

    # Range height check
    if range_height < 2 * atr_14:
        return None  # Not meaningful

    # Range position (0-100%)
    if range_height == 0:
        range_position = 50
    else:
        range_position = ((close_current - range_low) / range_height) * 100
        range_position = np.clip(range_position, 0, 100)

    # Range age (bars since last violation)
    range_age = 0
    for i in range(len(df) - 1, max(0, len(df) - 60), -1):
        if df['high'].iloc[i] > range_high or df['low'].iloc[i] < range_low:
            range_age = len(df) - 1 - i
            break
    else:
        range_age = 60

    # Range strength (# of touches of boundaries in last 60 bars)
    recent_60 = df.tail(60)
    touches_high = (recent_60['high'] >= range_high * 0.995).sum()
    touches_low = (recent_60['low'] <= range_low * 1.005).sum()
    range_strength = touches_high + touches_low

    return {
        'range_high': range_high,
        'range_low': range_low,
        'range_height': range_height,
        'range_position': range_position,
        'range_age_days': range_age,
        'range_strength': range_strength,
        'is_range': True
    }

def generate_range_signals(df):
    """Generate range trading signals with DeMark confirmation"""
    if len(df) < 50:
        return df

    # Compute TD indicators
    df = compute_all_td_indicators(df)

    # Compute RSI, ADX, ATR for context
    df['rsi'] = compute_rsi(df['close'], 14)
    df['adx'] = compute_adx(df, 14)
    df['atr'] = compute_atr(df, 14)

    # Initialize signal columns
    df['signal'] = 'HOLD'
    df['signal_type'] = None
    df['range_high'] = np.nan
    df['range_low'] = np.nan
    df['range_position'] = np.nan
    df['range_age_days'] = 0
    df['range_strength'] = 0
    df['range_height_pct'] = np.nan

    # Process each bar (rolling window detection)
    for i in range(49, len(df)):
        window = df.iloc[i-49:i+1]

        range_info = detect_range(window)
        if not range_info:
            continue

        df.loc[df.index[i], 'range_high'] = range_info['range_high']
        df.loc[df.index[i], 'range_low'] = range_info['range_low']
        df.loc[df.index[i], 'range_position'] = range_info['range_position']
        df.loc[df.index[i], 'range_age_days'] = range_info['range_age_days']
        df.loc[df.index[i], 'range_strength'] = range_info['range_strength']
        df.loc[df.index[i], 'range_height_pct'] = (range_info['range_height'] / range_info['range_low']) * 100

        # Generate signals
        close = df['close'].iloc[i]
        range_position = range_info['range_position']
        td_buy_complete = df['td_buy_setup_complete'].iloc[i]
        td_sell_complete = df['td_sell_setup_complete'].iloc[i]
        range_age = range_info['range_age_days']

        # RANGE_BOUNCE_LOW (long)
        if range_position < 25 and td_buy_complete and range_age >= 10:
            df.loc[df.index[i], 'signal'] = 'BUY'
            df.loc[df.index[i], 'signal_type'] = 'RANGE_BOUNCE_LOW'

        # RANGE_BOUNCE_HIGH (short)
        elif range_position > 75 and td_sell_complete and range_age >= 10:
            df.loc[df.index[i], 'signal'] = 'SELL'
            df.loc[df.index[i], 'signal_type'] = 'RANGE_BOUNCE_HIGH'

    return df

def compute_trade_levels(df):
    """Compute entry, stop, target levels"""
    df['entry_price'] = df['close']
    df['risk_pct'] = 0.0
    df['risk_reward_ratio'] = 0.0
    df['target_1'] = np.nan
    df['target_2'] = np.nan
    df['stop_level'] = np.nan

    for i in range(len(df)):
        if df['signal'].iloc[i] == 'HOLD':
            continue

        atr = df['atr'].iloc[i]
        range_high = df['range_high'].iloc[i]
        range_low = df['range_low'].iloc[i]
        range_height = range_high - range_low
        close = df['close'].iloc[i]

        if df['signal'].iloc[i] == 'BUY':
            # Long
            df.loc[df.index[i], 'stop_level'] = range_low - atr
            df.loc[df.index[i], 'target_1'] = range_low + 0.5 * range_height
            df.loc[df.index[i], 'target_2'] = range_high - atr
            stop = df['stop_level'].iloc[i]
            if stop < close:
                df.loc[df.index[i], 'risk_pct'] = ((close - stop) / close) * 100
                df.loc[df.index[i], 'risk_reward_ratio'] = (df['target_2'].iloc[i] - close) / (close - stop)

        elif df['signal'].iloc[i] == 'SELL':
            # Short
            df.loc[df.index[i], 'stop_level'] = range_high + atr
            df.loc[df.index[i], 'target_1'] = range_high - 0.5 * range_height
            df.loc[df.index[i], 'target_2'] = range_low + atr
            stop = df['stop_level'].iloc[i]
            if stop > close:
                df.loc[df.index[i], 'risk_pct'] = ((stop - close) / close) * 100
                df.loc[df.index[i], 'risk_reward_ratio'] = (close - df['target_2'].iloc[i]) / (stop - close)

    return df

def compute_rsi(close, period=14):
    """Compute RSI"""
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_atr(df, period=14):
    """Compute ATR"""
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr

def compute_adx(df, period=14):
    """Simplified ADX (using DX only)"""
    high_diff = df['high'].diff()
    low_diff = -df['low'].diff()

    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)

    tr = (df['high'] - df['low']).rolling(period).mean()
    adx = 100 * (plus_dm - minus_dm).rolling(period).mean() / tr.replace(0, np.nan)
    adx = adx.abs()

    return adx.fillna(0)

def insert_range_signals(cur, symbol, df, table_name="range_signals_daily"):
    """Insert range signals into database"""
    # Filter only rows with signals
    signal_rows = df[df['signal'] != 'HOLD'].copy()

    if len(signal_rows) == 0:
        return 0

    insert_q = f"""
        INSERT INTO {table_name} (
            symbol, date, timeframe,
            open, high, low, close, volume,
            signal, signal_type,
            range_high, range_low, range_position, range_age_days, range_strength, range_height_pct,
            entry_price, stop_level, target_1, target_2,
            risk_pct, risk_reward_ratio,
            rsi, adx, atr,
            td_buy_setup_count, td_sell_setup_count, td_buy_setup_complete, td_sell_setup_complete,
            td_buy_setup_perfected, td_sell_setup_perfected,
            td_buy_countdown_count, td_sell_countdown_count,
            td_pressure
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s)
        ON CONFLICT (symbol, date) DO UPDATE SET
            signal = EXCLUDED.signal,
            signal_type = EXCLUDED.signal_type,
            range_position = EXCLUDED.range_position
    """

    values = []
    for idx, row in signal_rows.iterrows():
        values.append((
            row['symbol'], row['date'], 'daily',
            row['open'], row['high'], row['low'], row['close'], row['volume'],
            row['signal'], row['signal_type'],
            row['range_high'], row['range_low'], row['range_position'], row['range_age_days'],
            row['range_strength'], row['range_height_pct'],
            row['entry_price'], row['stop_level'], row['target_1'], row['target_2'],
            row['risk_pct'], row['risk_reward_ratio'],
            row['rsi'], row['adx'], row['atr'],
            row['td_buy_setup_count'], row['td_sell_setup_count'], row['td_buy_setup_complete'],
            row['td_sell_setup_complete'], row['td_buy_setup_perfected'], row['td_sell_setup_perfected'],
            row['td_buy_countdown_count'], row['td_sell_countdown_count'], row['td_pressure']
        ))

    execute_values(cur, insert_q, values)
    return len(values)

def create_table(cur):
    """Create range_signals_daily table if it doesn't exist"""
    create_q = """
        CREATE TABLE IF NOT EXISTS range_signals_daily (
            id BIGSERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            timeframe VARCHAR(20) DEFAULT 'daily',

            open REAL, high REAL, low REAL, close REAL, volume BIGINT,

            signal VARCHAR(10),
            signal_type VARCHAR(30),

            range_high REAL,
            range_low REAL,
            range_position REAL,
            range_age_days INTEGER,
            range_strength INTEGER,
            range_height_pct REAL,

            entry_price REAL,
            stop_level REAL,
            target_1 REAL,
            target_2 REAL,
            risk_pct REAL,
            risk_reward_ratio REAL,

            rsi REAL,
            adx REAL,
            atr REAL,

            td_buy_setup_count INTEGER,
            td_sell_setup_count INTEGER,
            td_buy_setup_complete BOOLEAN,
            td_sell_setup_complete BOOLEAN,
            td_buy_setup_perfected BOOLEAN,
            td_sell_setup_perfected BOOLEAN,
            td_buy_countdown_count INTEGER,
            td_sell_countdown_count INTEGER,
            td_pressure REAL,

            created_at TIMESTAMP DEFAULT NOW(),

            UNIQUE(symbol, date)
        );

        CREATE INDEX IF NOT EXISTS idx_range_signals_symbol_date ON range_signals_daily(symbol, date DESC);
        CREATE INDEX IF NOT EXISTS idx_range_signals_signal ON range_signals_daily(signal, signal_type);
        CREATE INDEX IF NOT EXISTS idx_range_signals_date ON range_signals_daily(date DESC);
    """
    cur.execute(create_q)

def main():
    """Main loader logic"""
    logging.info(f"Starting {SCRIPT_NAME}")

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Create table
        create_table(cur)
        conn.commit()
        logging.info("Table range_signals_daily ready")

        # Get symbols
        symbols = get_symbols_from_db(limit=None)
        logging.info(f"Processing {len(symbols)} symbols")

        total_signals = 0
        for i, symbol in enumerate(symbols):
            if i % 100 == 0:
                logging.info(f"Progress: {i}/{len(symbols)}")

            # Get price data
            df = get_price_data(symbol)
            if df is None or len(df) < 50:
                continue

            # Generate signals
            df = generate_range_signals(df)
            df = compute_trade_levels(df)

            # Insert
            inserted = insert_range_signals(cur, symbol, df)
            total_signals += inserted

        conn.commit()
        logging.info(f"Inserted {total_signals} range signals")

    except Exception as e:
        logging.error(f"Error: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
