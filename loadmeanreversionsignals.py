#!/usr/bin/env python3
"""
Mean Reversion Signals Loader (Connors-style RSI Oversold)
Generates buy signals for oversold stocks in uptrends: RSI(2) < 10 + above 200 SMA.
Uses DeMark indicators for confluence scoring.
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

SCRIPT_NAME = "loadmeanreversionsignals.py"

# Logging
import tempfile
from logging.handlers import RotatingFileHandler
log_path = os.path.join(tempfile.gettempdir(), 'loadmeanreversionsignals.log')
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
        q = "SELECT symbol FROM stock_symbols WHERE price >= 5 ORDER BY symbol"
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

def compute_rsi(close, period=2):
    """Compute RSI with specified period"""
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(0)

def compute_sma(close, period):
    """Compute simple moving average"""
    return close.rolling(window=period).mean()

def compute_atr(df, period=14):
    """Compute ATR"""
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr

def generate_mean_reversion_signals(df):
    """Generate mean reversion signals (Connors-style RSI < 10)"""
    if len(df) < 200:
        return df

    # Compute indicators
    df['rsi_2'] = compute_rsi(df['close'], 2)
    df['rsi_14'] = compute_rsi(df['close'], 14)
    df['sma_5'] = compute_sma(df['close'], 5)
    df['sma_200'] = compute_sma(df['close'], 200)
    df['atr'] = compute_atr(df, 14)

    # Compute TD indicators
    df = compute_all_td_indicators(df)

    # Initialize signal columns
    df['signal'] = 'HOLD'
    df['signal_type'] = None
    df['pct_above_200sma'] = (((df['close'] - df['sma_200']) / df['sma_200']) * 100).fillna(0)
    df['confluence_score'] = 0
    df['target_estimate'] = np.nan

    # Generate signals: Connors RSI Oversold
    for i in range(200, len(df)):
        close = df['close'].iloc[i]
        rsi_2 = df['rsi_2'].iloc[i]
        sma_200 = df['sma_200'].iloc[i]
        sma_5 = df['sma_5'].iloc[i]

        # Condition 1: Close > 200 SMA (uptrend filter)
        if close is None or sma_200 is None or close <= sma_200:
            continue

        # Condition 2: RSI(2) < 10 (extreme oversold)
        if rsi_2 is None or rsi_2 >= 10:
            continue

        # Condition 3: Not extreme volume (avoid panic selling)
        avg_vol = df['volume'].iloc[max(0, i-50):i].mean()
        if df['volume'].iloc[i] > avg_vol * 3:
            continue

        # Signal fires
        df.loc[df.index[i], 'signal'] = 'BUY'
        df.loc[df.index[i], 'signal_type'] = 'CONNORS_RSI_OVERSOLD'
        df.loc[df.index[i], 'pct_above_200sma'] = ((close - sma_200) / sma_200) * 100

        # Confluence scoring (optional quality boost)
        confluence = 0
        if df['td_buy_setup_count'].iloc[i] >= 7:
            confluence += 1
        if df['td_buy_setup_complete'].iloc[i]:
            confluence += 2
        if df['td_buy_setup_perfected'].iloc[i]:
            confluence += 1
        if df['td_pressure'].iloc[i] < 30:
            confluence += 1
        if rsi_2 < 5:
            confluence += 1

        df.loc[df.index[i], 'confluence_score'] = confluence
        df.loc[df.index[i], 'target_estimate'] = sma_5 * 1.02

    return df

def compute_trade_levels(df):
    """Compute entry, stop, target levels"""
    df['entry_price'] = df['close']
    df['stop_level'] = df['close'] * 0.95  # 5% hard stop
    df['risk_pct'] = 5.0  # Fixed 5% risk
    df['risk_reward_ratio'] = 0.0

    for i in range(len(df)):
        if df['signal'].iloc[i] == 'HOLD':
            continue

        entry = df['entry_price'].iloc[i]
        stop = df['stop_level'].iloc[i]
        target = df['target_estimate'].iloc[i]

        if not pd.isna(target):
            df.loc[df.index[i], 'risk_reward_ratio'] = (target - entry) / (entry - stop)

    return df

def insert_mean_reversion_signals(cur, symbol, df, table_name="mean_reversion_signals_daily"):
    """Insert mean reversion signals into database"""
    # Filter only rows with signals
    signal_rows = df[df['signal'] != 'HOLD'].copy()

    if len(signal_rows) == 0:
        return 0

    insert_q = f"""
        INSERT INTO {table_name} (
            symbol, date, timeframe,
            open, high, low, close, volume,
            signal, signal_type,
            rsi_2, pct_above_200sma, sma_5,
            entry_price, stop_level, target_estimate,
            risk_pct, risk_reward_ratio,
            confluence_score,
            rsi_14, atr,
            td_buy_setup_count, td_buy_setup_complete, td_buy_setup_perfected,
            td_pressure
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, date) DO UPDATE SET
            signal = EXCLUDED.signal,
            rsi_2 = EXCLUDED.rsi_2,
            confluence_score = EXCLUDED.confluence_score
    """

    values = []
    for idx, row in signal_rows.iterrows():
        values.append((
            row['symbol'], row['date'], 'daily',
            row['open'], row['high'], row['low'], row['close'], row['volume'],
            row['signal'], row['signal_type'],
            row['rsi_2'], row['pct_above_200sma'], row['sma_5'],
            row['entry_price'], row['stop_level'], row['target_estimate'],
            row['risk_pct'], row['risk_reward_ratio'],
            row['confluence_score'],
            row['rsi_14'], row['atr'],
            row['td_buy_setup_count'], row['td_buy_setup_complete'], row['td_buy_setup_perfected'],
            row['td_pressure']
        ))

    execute_values(cur, insert_q, values)
    return len(values)

def create_table(cur):
    """Create mean_reversion_signals_daily table"""
    create_q = """
        CREATE TABLE IF NOT EXISTS mean_reversion_signals_daily (
            id BIGSERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            timeframe VARCHAR(20) DEFAULT 'daily',

            open REAL, high REAL, low REAL, close REAL, volume BIGINT,

            signal VARCHAR(10),
            signal_type VARCHAR(30),

            rsi_2 REAL,
            pct_above_200sma REAL,
            sma_5 REAL,

            entry_price REAL,
            stop_level REAL,
            target_estimate REAL,
            risk_pct REAL,
            risk_reward_ratio REAL,

            confluence_score INTEGER,

            rsi_14 REAL,
            atr REAL,

            td_buy_setup_count INTEGER,
            td_buy_setup_complete BOOLEAN,
            td_buy_setup_perfected BOOLEAN,
            td_pressure REAL,

            created_at TIMESTAMP DEFAULT NOW(),

            UNIQUE(symbol, date)
        );

        CREATE INDEX IF NOT EXISTS idx_meanrev_symbol_date ON mean_reversion_signals_daily(symbol, date DESC);
        CREATE INDEX IF NOT EXISTS idx_meanrev_signal ON mean_reversion_signals_daily(signal, signal_type);
        CREATE INDEX IF NOT EXISTS idx_meanrev_date ON mean_reversion_signals_daily(date DESC);
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
        logging.info("Table mean_reversion_signals_daily ready")

        # Get symbols
        symbols = get_symbols_from_db(limit=None)
        logging.info(f"Processing {len(symbols)} symbols")

        total_signals = 0
        for i, symbol in enumerate(symbols):
            if i % 100 == 0:
                logging.info(f"Progress: {i}/{len(symbols)}")

            # Get price data
            df = get_price_data(symbol)
            if df is None or len(df) < 200:
                continue

            # Generate signals
            df = generate_mean_reversion_signals(df)
            df = compute_trade_levels(df)

            # Insert
            inserted = insert_mean_reversion_signals(cur, symbol, df)
            total_signals += inserted

        conn.commit()
        logging.info(f"Inserted {total_signals} mean reversion signals")

    except Exception as e:
        logging.error(f"Error: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
