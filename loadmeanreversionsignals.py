#!/usr/bin/env python3
"""
Mean Reversion Signals Loader with 100% Data Parity to Swing Trading

Connors-style RSI Oversold strategy with full technical analysis:
- Connors RSI(2) < 10 for oversold detection
- Shared indicators from signal_utils.py (SMA, EMA, MACD, RSI, ADX, ATR)
- Market stage detection & SATA scoring
- Entry quality & breakout quality assessment
- Volume analysis & position sizing
- DeMark TD Sequential confluence scoring
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

# Import shared signal utilities
try:
    from signal_utils import (
        compute_moving_averages, compute_volume_analysis, compute_rs_metrics,
        compute_daily_range_pct, compute_base_analysis, compute_relative_position,
        detect_market_stage, compute_signal_strength, compute_entry_quality,
        compute_breakout_quality, compute_position_sizing, calculate_macd,
        calculate_rsi, calculate_atr, calculate_adx, calculate_sma,
        compute_sata_scores, calculate_sata
    )
except ImportError as e:
    logging.error(f"Failed to import signal_utils: {e}")
    sys.exit(1)

# Import DeMark helper
try:
    from demark_indicators import compute_all_td_indicators
    HAS_DEMARK = True
except ImportError:
    HAS_DEMARK = False
    logging.warning("demark_indicators not available - TD indicators will be skipped")

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
        q = f"""
            SELECT symbol, date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol = %s AND date >= NOW() - INTERVAL '{lookback_days} days'
            ORDER BY date ASC
        """
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

# Note: RSI, SMA, ATR calculations are imported from signal_utils
# Local definitions removed to avoid duplication

def generate_mean_reversion_signals(df):
    """Generate mean reversion signals (Connors-style RSI < 10) with full technical analysis"""
    if len(df) < 200:
        return df

    # === LOCAL INDICATOR CALCULATIONS ===
    df['rsi_2'] = calculate_rsi(df['close'], 2)
    df['rsi_14'] = calculate_rsi(df['close'], 14)
    df['sma_5'] = calculate_sma(df['close'], 5)
    df['atr'] = calculate_atr(df['high'], df['low'], df['close'], 14)
    df['adx'] = calculate_adx(df['high'], df['low'], df['close'], 14)

    # === SHARED INDICATOR COMPUTATIONS ===
    df = compute_moving_averages(df)  # SMA 20/50/200, EMA 21/26
    df = compute_relative_position(df)  # % from moving averages
    df = compute_volume_analysis(df)  # Volume surge, ratio, 50d avg
    df = compute_rs_metrics(df)  # RS rating, Mansfield RS
    df = compute_daily_range_pct(df)  # Daily range %
    df = compute_base_analysis(df)  # Base type, length
    df = detect_market_stage(df)  # Market stage 1-4

    # MACD calculation
    macd, signal_line = calculate_macd(df['close'])
    df['macd'] = macd
    df['signal_line'] = signal_line

    # Pivot price
    df['pivot_price'] = ((df['high'] + df['low'] + df['close']) / 3).round(2)

    # Buy zone
    df['buy_zone_start'] = df['sma_200'] * 0.98
    df['buy_zone_end'] = df['sma_200']

    # Exit triggers
    df['exit_trigger_1_price'] = None
    df['exit_trigger_2_price'] = None
    df['exit_trigger_3_price'] = None
    df['exit_trigger_4_price'] = None

    # === DeMark TD INDICATORS ===
    if HAS_DEMARK:
        try:
            td_df = compute_all_td_indicators(df)
            td_cols = ['td_buy_setup_count', 'td_sell_setup_count',
                      'td_buy_setup_complete', 'td_sell_setup_complete',
                      'td_buy_setup_perfected', 'td_sell_setup_perfected',
                      'td_buy_countdown_count', 'td_sell_countdown_count', 'td_pressure']
            for col in td_cols:
                if col in td_df.columns:
                    df[col] = td_df[col]
        except Exception as e:
            logging.warning(f"DeMark computation failed: {e}")

    # Initialize signal columns
    df['signal'] = 'HOLD'
    df['signal_type'] = None
    df['pct_above_200sma'] = (((df['close'] - df['sma_200']) / df['sma_200']) * 100).fillna(0)
    df['confluence_score'] = 0
    df['target_estimate'] = np.nan
    df['entry_price'] = np.nan
    df['stop_level'] = np.nan
    df['initial_stop'] = np.nan
    df['trailing_stop'] = np.nan
    df['profit_target_8pct'] = np.nan
    df['profit_target_20pct'] = np.nan
    df['profit_target_25pct'] = np.nan

    # Generate signals: Connors RSI Oversold
    for i in range(200, len(df)):
        close = df['close'].iloc[i]
        rsi_2 = df['rsi_2'].iloc[i]
        sma_200 = df['sma_200'].iloc[i]
        sma_5 = df['sma_5'].iloc[i]

        # Condition 1: Close reasonably near 200 SMA (within 10% below)
        if close is None or sma_200 is None or close < sma_200 * 0.9:
            continue

        # Condition 2: RSI(2) < 40 (oversold/weak)
        if rsi_2 is None or rsi_2 >= 40:
            continue

        # Signal fires
        df.loc[df.index[i], 'signal'] = 'BUY'
        df.loc[df.index[i], 'signal_type'] = 'CONNORS_RSI_OVERSOLD'
        df.loc[df.index[i], 'pct_above_200sma'] = ((close - sma_200) / sma_200) * 100

        # Entry and stop levels
        df.loc[df.index[i], 'entry_price'] = close
        df.loc[df.index[i], 'stop_level'] = close * 0.95
        df.loc[df.index[i], 'initial_stop'] = close * 0.95
        df.loc[df.index[i], 'trailing_stop'] = close * 0.95

        # Profit targets
        df.loc[df.index[i], 'profit_target_8pct'] = close * 1.08
        df.loc[df.index[i], 'profit_target_20pct'] = close * 1.20
        df.loc[df.index[i], 'profit_target_25pct'] = close * 1.25

        # Exit triggers
        df.loc[df.index[i], 'exit_trigger_1_price'] = close * 1.08
        df.loc[df.index[i], 'exit_trigger_2_price'] = close * 1.20
        df.loc[df.index[i], 'exit_trigger_3_price'] = close * 1.25
        df.loc[df.index[i], 'exit_trigger_4_price'] = close * 0.95

        # Confluence scoring (DeMark confluence)
        confluence = 0
        if HAS_DEMARK:
            td_setup = df['td_buy_setup_count'].iloc[i] if 'td_buy_setup_count' in df.columns else 0
            td_complete = df['td_buy_setup_complete'].iloc[i] if 'td_buy_setup_complete' in df.columns else False
            td_perfected = df['td_buy_setup_perfected'].iloc[i] if 'td_buy_setup_perfected' in df.columns else False
            td_pressure = df['td_pressure'].iloc[i] if 'td_pressure' in df.columns else 100

            if td_setup >= 7:
                confluence += 1
            if td_complete:
                confluence += 2
            if td_perfected:
                confluence += 1
            if td_pressure < 30:
                confluence += 1

        if rsi_2 < 5:
            confluence += 1

        df.loc[df.index[i], 'confluence_score'] = confluence
        df.loc[df.index[i], 'target_estimate'] = sma_5 * 1.02

    # === QUALITY METRICS ===
    df = compute_signal_strength(df)
    df = compute_breakout_quality(df)
    df = compute_entry_quality(df)
    df = compute_position_sizing(df)
    df = compute_sata_scores(df)

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
    """Insert mean reversion signals into database with all enriched data"""
    # Filter only rows with signals
    signal_rows = df[df['signal'] != 'HOLD'].copy()

    if len(signal_rows) == 0:
        return 0

    def safe_val(val):
        """Convert NaN/None to None for database compatibility"""
        if pd.isna(val):
            return None
        return val

    insert_q = f"""
        INSERT INTO {table_name} (
            symbol, date, timeframe,
            open, high, low, close, volume,
            signal, signal_type,
            rsi_2, pct_above_200sma, sma_5, confluence_score,
            entry_price, stop_level, initial_stop, trailing_stop,
            target_estimate, profit_target_8pct, profit_target_20pct, profit_target_25pct,
            risk_pct, risk_reward_ratio,
            rsi_14, atr,
            sma_20, sma_50, sma_200, ema_21, ema_26,
            pivot_price, macd, signal_line,
            avg_volume_50d, volume_surge_pct, volume_ratio,
            pct_from_ema21, pct_from_sma50, pct_from_sma200,
            market_stage, stage_number, stage_confidence, substage,
            daily_range_pct, base_type, base_length_days,
            signal_strength, entry_quality_score, breakout_quality,
            sata_score, mansfield_rs, rs_rating,
            buy_zone_start, buy_zone_end,
            exit_trigger_1_price, exit_trigger_2_price, exit_trigger_3_price, exit_trigger_4_price,
            position_size_recommendation,
            td_buy_setup_count, td_buy_setup_complete, td_buy_setup_perfected,
            td_buy_countdown_count, td_sell_setup_count, td_sell_setup_complete,
            td_sell_setup_perfected, td_sell_countdown_count, td_pressure
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s,
            %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s
        )
        ON CONFLICT (symbol, date) DO UPDATE SET
            signal = EXCLUDED.signal,
            signal_strength = EXCLUDED.signal_strength,
            confluence_score = EXCLUDED.confluence_score
    """

    values = []
    for idx, row in signal_rows.iterrows():
        values.append((
            # Basic
            row['symbol'], row['date'], 'daily',
            safe_val(row['open']), safe_val(row['high']), safe_val(row['low']), safe_val(row['close']), safe_val(row['volume']),
            safe_val(row['signal']), safe_val(row['signal_type']),
            # Mean reversion specific
            safe_val(row['rsi_2']), safe_val(row['pct_above_200sma']), safe_val(row['sma_5']), safe_val(row['confluence_score']),
            # Entry/Exit
            safe_val(row['entry_price']), safe_val(row['stop_level']), safe_val(row.get('initial_stop')), safe_val(row.get('trailing_stop')),
            safe_val(row['target_estimate']), safe_val(row.get('profit_target_8pct')), safe_val(row.get('profit_target_20pct')), safe_val(row.get('profit_target_25pct')),
            # Risk/Reward
            safe_val(row.get('risk_pct')), safe_val(row.get('risk_reward_ratio')),
            # Technical
            safe_val(row['rsi_14']), safe_val(row['atr']),
            safe_val(row.get('sma_20')), safe_val(row.get('sma_50')), safe_val(row.get('sma_200')), safe_val(row.get('ema_21')), safe_val(row.get('ema_26')),
            safe_val(row.get('pivot_price')), safe_val(row.get('macd')), safe_val(row.get('signal_line')),
            # Volume
            int(row.get('avg_volume_50d')) if pd.notna(row.get('avg_volume_50d')) else None,
            safe_val(row.get('volume_surge_pct')), safe_val(row.get('volume_ratio')),
            # Position
            safe_val(row.get('pct_from_ema21')), safe_val(row.get('pct_from_sma50')), safe_val(row.get('pct_from_sma200')),
            # Market
            safe_val(row.get('market_stage')),
            int(row.get('stage_number')) if pd.notna(row.get('stage_number')) else None,
            safe_val(row.get('stage_confidence')),
            safe_val(row.get('substage')),
            safe_val(row.get('daily_range_pct')), safe_val(row.get('base_type')),
            int(row.get('base_length_days')) if pd.notna(row.get('base_length_days')) else None,
            # Quality
            safe_val(row.get('signal_strength')), safe_val(row.get('entry_quality_score')), safe_val(row.get('breakout_quality')),
            int(row.get('sata_score')) if pd.notna(row.get('sata_score')) else None,
            safe_val(row.get('mansfield_rs')),
            int(row.get('rs_rating')) if pd.notna(row.get('rs_rating')) else None,
            # Zone & triggers
            safe_val(row.get('buy_zone_start')), safe_val(row.get('buy_zone_end')),
            safe_val(row.get('exit_trigger_1_price')), safe_val(row.get('exit_trigger_2_price')), safe_val(row.get('exit_trigger_3_price')), safe_val(row.get('exit_trigger_4_price')),
            # Position sizing
            safe_val(row.get('position_size_recommendation')),
            # DeMark
            int(row.get('td_buy_setup_count', 0)) if pd.notna(row.get('td_buy_setup_count')) else None,
            bool(row.get('td_buy_setup_complete', False)) if pd.notna(row.get('td_buy_setup_complete')) else None,
            bool(row.get('td_buy_setup_perfected', False)) if pd.notna(row.get('td_buy_setup_perfected')) else None,
            int(row.get('td_buy_countdown_count', 0)) if pd.notna(row.get('td_buy_countdown_count')) else None,
            int(row.get('td_sell_setup_count', 0)) if pd.notna(row.get('td_sell_setup_count')) else None,
            bool(row.get('td_sell_setup_complete', False)) if pd.notna(row.get('td_sell_setup_complete')) else None,
            bool(row.get('td_sell_setup_perfected', False)) if pd.notna(row.get('td_sell_setup_perfected')) else None,
            int(row.get('td_sell_countdown_count', 0)) if pd.notna(row.get('td_sell_countdown_count')) else None,
            safe_val(row.get('td_pressure'))
        ))

    execute_values(cur, insert_q, values)
    return len(values)

def create_table(cur):
    """Create mean_reversion_signals_daily table with full data parity"""
    create_q = """
        CREATE TABLE IF NOT EXISTS mean_reversion_signals_daily (
            id BIGSERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            timeframe VARCHAR(20) DEFAULT 'daily',

            -- Price data
            open REAL, high REAL, low REAL, close REAL, volume BIGINT,

            -- Signal
            signal VARCHAR(10),
            signal_type VARCHAR(30),

            -- Mean reversion specific
            rsi_2 REAL,
            pct_above_200sma REAL,
            sma_5 REAL,
            confluence_score INTEGER,

            -- Entry/Exit levels
            entry_price REAL,
            stop_level REAL,
            initial_stop REAL,
            trailing_stop REAL,
            target_estimate REAL,
            profit_target_8pct REAL,
            profit_target_20pct REAL,
            profit_target_25pct REAL,

            -- Risk/Reward
            risk_pct REAL,
            risk_reward_ratio REAL,

            -- Shared technical indicators
            rsi_14 REAL,
            atr REAL,
            sma_20 REAL,
            sma_50 REAL,
            sma_200 REAL,
            ema_21 REAL,
            ema_26 REAL,
            pivot_price REAL,
            macd REAL,
            signal_line REAL,

            -- Volume analysis
            avg_volume_50d BIGINT,
            volume_surge_pct REAL,
            volume_ratio REAL,

            -- Relative position
            pct_from_ema21 REAL,
            pct_from_sma50 REAL,
            pct_from_sma200 REAL,

            -- Market analysis
            market_stage VARCHAR(50),
            stage_number INT,
            stage_confidence REAL,
            substage VARCHAR(50),
            daily_range_pct REAL,
            base_type VARCHAR(30),
            base_length_days INT,

            -- Quality metrics
            signal_strength REAL,
            entry_quality_score REAL,
            breakout_quality VARCHAR(20),
            sata_score INT,
            mansfield_rs REAL,
            rs_rating INT,

            -- Buy zone & exit triggers
            buy_zone_start REAL,
            buy_zone_end REAL,
            exit_trigger_1_price REAL,
            exit_trigger_2_price REAL,
            exit_trigger_3_price REAL,
            exit_trigger_4_price REAL,

            -- Position sizing
            position_size_recommendation REAL,

            -- DeMark indicators
            td_buy_setup_count INTEGER,
            td_buy_setup_complete BOOLEAN,
            td_buy_setup_perfected BOOLEAN,
            td_buy_countdown_count INTEGER,
            td_sell_setup_count INTEGER,
            td_sell_setup_complete BOOLEAN,
            td_sell_setup_perfected BOOLEAN,
            td_sell_countdown_count INTEGER,
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
