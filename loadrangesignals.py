#!/usr/bin/env python3
"""
Fast Range Trading Signals Loader with 100% Data Parity to Swing Trading

Processes range trading signals with full technical analysis:
- Shared indicators from signal_utils.py (SMA, EMA, MACD, RSI, ADX, ATR)
- Market stage detection & SATA scoring
- Entry quality & breakout quality assessment
- Volume analysis & position sizing
- Risk/reward calculations & profit targets
"""

import os
import sys
import json
import pandas as pd
import numpy as np
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

try:
    from demark_indicators import compute_all_td_indicators
    HAS_DEMARK = True
except ImportError:
    HAS_DEMARK = False
    logging.warning("demark_indicators not available")

try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False
    logging.warning("talib not available")

env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Get DB connection
def get_db_connection():
    if os.environ.get("DB_SECRET_ARN"):
        import json
        import boto3
        secret_arn = os.environ.get("DB_SECRET_ARN")
        region = secret_arn.split(':')[3]
        client = boto3.client('secretsmanager', region_name=region)
        secret = json.loads(client.get_secret_value(SecretId=secret_arn)['SecretString'])
        return psycopg2.connect(
            host=secret['host'],
            port=secret.get('port', 5432),
            user=secret['username'],
            password=secret['password'],
            database=secret['dbname']
        )
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME', 'stocks')
    )

def create_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS range_signals_daily (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20),
            date DATE,
            timeframe VARCHAR(20) DEFAULT 'daily',
            open FLOAT, high FLOAT, low FLOAT, close FLOAT, volume BIGINT,
            signal VARCHAR(50), signal_type VARCHAR(50),

            -- Range-specific fields
            range_high FLOAT, range_low FLOAT, range_position FLOAT,
            range_age_days INT, range_strength INT, range_height_pct FLOAT,

            -- Entry/Exit levels
            entry_price FLOAT, stop_level FLOAT, initial_stop FLOAT, trailing_stop FLOAT,
            target_1 FLOAT, target_2 FLOAT,
            profit_target_8pct FLOAT, profit_target_20pct FLOAT, profit_target_25pct FLOAT,

            -- Risk/Reward
            risk_pct FLOAT, risk_reward_ratio FLOAT,

            -- Shared technical indicators
            rsi FLOAT, adx FLOAT, atr FLOAT,
            sma_20 FLOAT, sma_50 FLOAT, sma_200 FLOAT,
            ema_21 FLOAT, ema_26 FLOAT,
            pivot_price FLOAT, macd FLOAT, signal_line FLOAT,

            -- Volume analysis
            avg_volume_50d BIGINT, volume_surge_pct FLOAT, volume_ratio FLOAT,

            -- Relative position
            pct_from_ema21 FLOAT, pct_from_sma50 FLOAT, pct_from_sma200 FLOAT,

            -- Market analysis
            market_stage VARCHAR(50), stage_number INT, stage_confidence FLOAT, substage VARCHAR(50),
            daily_range_pct FLOAT, base_type VARCHAR(30), base_length_days INT,

            -- Quality metrics
            signal_strength FLOAT, entry_quality_score FLOAT, breakout_quality VARCHAR(20),
            sata_score INT, mansfield_rs FLOAT, rs_rating INT,

            -- Buy zone & exit triggers
            buy_zone_start FLOAT, buy_zone_end FLOAT,
            exit_trigger_1_price FLOAT, exit_trigger_2_price FLOAT,
            exit_trigger_3_price FLOAT, exit_trigger_4_price FLOAT,

            -- Position sizing
            position_size_recommendation FLOAT,

            -- DeMark indicators (if available)
            td_buy_setup_count INT, td_sell_setup_count INT,
            td_buy_setup_complete BOOLEAN, td_sell_setup_complete BOOLEAN,
            td_buy_setup_perfected BOOLEAN, td_sell_setup_perfected BOOLEAN,
            td_buy_countdown_count INT, td_sell_countdown_count INT, td_pressure FLOAT
        );
        CREATE INDEX IF NOT EXISTS idx_range_symbol_date ON range_signals_daily(symbol, date DESC);
        CREATE INDEX IF NOT EXISTS idx_range_signal_type ON range_signals_daily(signal, signal_type);
        CREATE INDEX IF NOT EXISTS idx_range_date ON range_signals_daily(date DESC);
    """)
    conn.commit()
    cur.close()

def get_top_symbols(conn, limit=200):
    """Get most traded/liquid symbols"""
    cur = conn.cursor()
    cur.execute(f"""
        SELECT symbol FROM stock_symbols
        WHERE symbol NOT LIKE '%.%' AND symbol NOT LIKE '%^%'
        ORDER BY symbol
        LIMIT {limit}
    """)
    symbols = [row[0] for row in cur.fetchall()]
    cur.close()
    return symbols

def get_price_data(conn, symbol, lookback_days=500):
    """Fetch price data for a symbol"""
    cur = conn.cursor()
    cur.execute(f"""
        SELECT date, open, high, low, close, volume
        FROM price_daily
        WHERE symbol = %s
        ORDER BY date ASC
    """, (symbol,))
    rows = cur.fetchall()
    cur.close()

    if not rows:
        return None

    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['symbol'] = symbol
    df['date'] = pd.to_datetime(df['date'])
    return df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']].copy()

def compute_indicators(df):
    """Compute all technical indicators using shared utilities + optional talib"""
    if len(df) < 50:
        return None

    df = df.copy()

    # Use talib if available for speed, otherwise use pandas-based calculations
    if HAS_TALIB:
        try:
            df['rsi'] = talib.RSI(df['close'].values, timeperiod=14)
            df['atr'] = talib.ATR(df['high'].values, df['low'].values, df['close'].values, timeperiod=14)
            df['adx'] = talib.ADX(df['high'].values, df['low'].values, df['close'].values, timeperiod=14)
        except Exception as e:
            logging.warning(f"talib calculation failed, using pandas-based indicators: {e}")
            df['rsi'] = calculate_rsi(df['close'], 14)
            df['atr'] = calculate_atr(df['high'], df['low'], df['close'], 14)
            df['adx'] = calculate_adx(df['high'], df['low'], df['close'], 14)
    else:
        # Pandas-based calculations
        df['rsi'] = calculate_rsi(df['close'], 14)
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

    # Buy zone (2% below high, at high)
    if 'range_high' in df.columns:
        df['buy_zone_start'] = df['range_high'] * 0.98
        df['buy_zone_end'] = df['range_high']
    else:
        df['buy_zone_start'] = None
        df['buy_zone_end'] = None

    # Exit triggers (based on entry_price)
    df['exit_trigger_1_price'] = None
    df['exit_trigger_2_price'] = None
    df['exit_trigger_3_price'] = None
    df['exit_trigger_4_price'] = None

    # Add DeMark indicators if available
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

    return df

def detect_range_and_signals(df):
    """Detect ranges and generate trading signals with quality metrics"""
    if df is None or len(df) < 20:
        return df

    df = df.copy()
    df['range_high'] = np.nan
    df['range_low'] = np.nan
    df['range_position'] = np.nan
    df['range_age_days'] = 0
    df['range_strength'] = 0
    df['signal'] = None
    df['signal_type'] = None
    df['entry_price'] = np.nan
    df['stop_level'] = np.nan
    df['target_1'] = np.nan
    df['target_2'] = np.nan
    df['risk_pct'] = np.nan
    df['risk_reward_ratio'] = np.nan
    df['initial_stop'] = np.nan
    df['trailing_stop'] = np.nan

    # Simple range detection: if last 20 bars have low ATR (tight range)
    for i in range(20, len(df)):
        lookback = 20
        high_20 = df.iloc[i-lookback:i]['high'].max()
        low_20 = df.iloc[i-lookback:i]['low'].min()
        range_height = high_20 - low_20
        atr_avg = df.iloc[i-lookback:i]['atr'].mean()

        if range_height < atr_avg * 2 and range_height > atr_avg * 0.5:
            # Valid range detected
            df.loc[i, 'range_high'] = high_20
            df.loc[i, 'range_low'] = low_20
            df.loc[i, 'range_position'] = ((df.iloc[i]['close'] - low_20) / range_height * 100) if range_height > 0 else 50
            df.loc[i, 'range_age_days'] = (df.iloc[i]['date'] - df.iloc[i-lookback]['date']).days
            df.loc[i, 'range_strength'] = len(set(pd.cut(df.iloc[i-lookback:i]['high'], bins=5)))

            # Generate signals at support/resistance
            current_price = df.iloc[i]['close']
            td_setup = df.iloc[i].get('td_buy_setup_count', 0) if 'td_buy_setup_count' in df.columns else 0

            if current_price < low_20 * 1.02 and td_setup >= 7:
                df.loc[i, 'signal'] = 'BUY'
                df.loc[i, 'signal_type'] = 'RANGE_BOUNCE_LOW'
                df.loc[i, 'entry_price'] = current_price
                df.loc[i, 'stop_level'] = low_20 * 0.98
                df.loc[i, 'initial_stop'] = low_20 * 0.98
                df.loc[i, 'trailing_stop'] = low_20 * 0.98
                df.loc[i, 'target_1'] = current_price + (high_20 - low_20) * 0.5
                df.loc[i, 'target_2'] = high_20

            elif current_price > high_20 * 0.98 and td_setup >= 5:
                df.loc[i, 'signal'] = 'SELL'
                df.loc[i, 'signal_type'] = 'RANGE_BOUNCE_HIGH'
                df.loc[i, 'entry_price'] = current_price
                df.loc[i, 'stop_level'] = high_20 * 1.02
                df.loc[i, 'initial_stop'] = high_20 * 1.02
                df.loc[i, 'trailing_stop'] = high_20 * 1.02
                df.loc[i, 'target_1'] = current_price - (high_20 - low_20) * 0.5
                df.loc[i, 'target_2'] = low_20

    # === PROFIT TARGETS ===
    df['profit_target_8pct'] = df['entry_price'] * 1.08
    df['profit_target_20pct'] = df['entry_price'] * 1.20
    df['profit_target_25pct'] = df['entry_price'] * 1.25

    # === EXIT TRIGGERS ===
    df['exit_trigger_1_price'] = df['profit_target_8pct']
    df['exit_trigger_2_price'] = df['profit_target_20pct']
    df['exit_trigger_3_price'] = df['profit_target_25pct']
    df['exit_trigger_4_price'] = df['stop_level']

    # === RISK/REWARD CALCULATIONS ===
    df['risk_pct'] = df.apply(
        lambda row: round(((row['entry_price'] - row['stop_level']) / row['entry_price'] * 100), 2)
        if pd.notna(row['entry_price']) and pd.notna(row['stop_level']) and row['entry_price'] > 0 else None,
        axis=1
    )

    df['risk_reward_ratio'] = df.apply(
        lambda row: round((row['target_1'] - row['entry_price']) / (row['entry_price'] - row['stop_level']), 2)
        if pd.notna(row['entry_price']) and pd.notna(row['stop_level']) and pd.notna(row['target_1'])
        and (row['entry_price'] - row['stop_level']) != 0 else None,
        axis=1
    )

    # === QUALITY METRICS ===
    # Compute signal strength
    df = compute_signal_strength(df)

    # Compute breakout quality
    df = compute_breakout_quality(df)

    # Compute entry quality
    df = compute_entry_quality(df)

    # Compute position sizing
    df = compute_position_sizing(df)

    # Compute SATA scores
    df = compute_sata_scores(df)

    return df

def insert_signals(conn, signals_df):
    """Batch insert signals into database with all enriched data"""
    if signals_df is None or len(signals_df) == 0:
        return 0

    # Filter for rows with signals
    signal_rows = signals_df[signals_df['signal'].notna()].copy()

    if len(signal_rows) == 0:
        return 0

    signal_rows = signal_rows.fillna(value=np.nan)

    def safe_val(val):
        """Convert NaN/None to None for database compatibility"""
        if pd.isna(val):
            return None
        return val

    values = [
        (
            # Basic fields
            row['symbol'], row['date'], 'daily',
            safe_val(row['open']), safe_val(row['high']), safe_val(row['low']), safe_val(row['close']), safe_val(row['volume']),
            safe_val(row['signal']), safe_val(row['signal_type']),

            # Range-specific
            safe_val(row['range_high']), safe_val(row['range_low']), safe_val(row['range_position']),
            int(row['range_age_days']) if pd.notna(row['range_age_days']) else None,
            int(row['range_strength']) if pd.notna(row['range_strength']) else None,
            safe_val(row.get('range_height_pct')),

            # Entry/Exit
            safe_val(row['entry_price']), safe_val(row['stop_level']),
            safe_val(row.get('initial_stop')), safe_val(row.get('trailing_stop')),
            safe_val(row['target_1']), safe_val(row['target_2']),
            safe_val(row.get('profit_target_8pct')), safe_val(row.get('profit_target_20pct')), safe_val(row.get('profit_target_25pct')),

            # Risk/Reward
            safe_val(row['risk_pct']), safe_val(row['risk_reward_ratio']),

            # Technical indicators
            safe_val(row.get('rsi')), safe_val(row.get('adx')), safe_val(row.get('atr')),
            safe_val(row.get('sma_20')), safe_val(row.get('sma_50')), safe_val(row.get('sma_200')),
            safe_val(row.get('ema_21')), safe_val(row.get('ema_26')),
            safe_val(row.get('pivot_price')), safe_val(row.get('macd')), safe_val(row.get('signal_line')),

            # Volume
            int(row.get('avg_volume_50d')) if pd.notna(row.get('avg_volume_50d')) else None,
            safe_val(row.get('volume_surge_pct')), safe_val(row.get('volume_ratio')),

            # Relative position
            safe_val(row.get('pct_from_ema21')), safe_val(row.get('pct_from_sma50')), safe_val(row.get('pct_from_sma200')),

            # Market analysis
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

            # Buy zone & exit triggers
            safe_val(row.get('buy_zone_start')), safe_val(row.get('buy_zone_end')),
            safe_val(row.get('exit_trigger_1_price')), safe_val(row.get('exit_trigger_2_price')),
            safe_val(row.get('exit_trigger_3_price')), safe_val(row.get('exit_trigger_4_price')),

            # Position sizing
            safe_val(row.get('position_size_recommendation')),

            # DeMark indicators
            int(row.get('td_buy_setup_count', 0)) if pd.notna(row.get('td_buy_setup_count')) else None,
            int(row.get('td_sell_setup_count', 0)) if pd.notna(row.get('td_sell_setup_count')) else None,
            bool(row.get('td_buy_setup_complete', False)) if pd.notna(row.get('td_buy_setup_complete')) else None,
            bool(row.get('td_sell_setup_complete', False)) if pd.notna(row.get('td_sell_setup_complete')) else None,
            bool(row.get('td_buy_setup_perfected', False)) if pd.notna(row.get('td_buy_setup_perfected')) else None,
            bool(row.get('td_sell_setup_perfected', False)) if pd.notna(row.get('td_sell_setup_perfected')) else None,
            int(row.get('td_buy_countdown_count', 0)) if pd.notna(row.get('td_buy_countdown_count')) else None,
            int(row.get('td_sell_countdown_count', 0)) if pd.notna(row.get('td_sell_countdown_count')) else None,
            safe_val(row.get('td_pressure'))
        )
        for _, row in signal_rows.iterrows()
    ]

    if not values:
        return 0

    cur = conn.cursor()
    execute_values(cur, """
        INSERT INTO range_signals_daily
        (symbol, date, timeframe, open, high, low, close, volume,
         signal, signal_type, range_high, range_low, range_position,
         range_age_days, range_strength, range_height_pct,
         entry_price, stop_level, initial_stop, trailing_stop,
         target_1, target_2, profit_target_8pct, profit_target_20pct, profit_target_25pct,
         risk_pct, risk_reward_ratio,
         rsi, adx, atr,
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
         td_buy_setup_count, td_sell_setup_count,
         td_buy_setup_complete, td_sell_setup_complete,
         td_buy_setup_perfected, td_sell_setup_perfected,
         td_buy_countdown_count, td_sell_countdown_count, td_pressure)
        VALUES %s ON CONFLICT DO NOTHING
    """, values, page_size=500)

    result = cur.rowcount
    conn.commit()
    cur.close()
    return result

def main():
    conn = get_db_connection()
    create_table(conn)

    symbols = get_top_symbols(conn, limit=200)
    logging.info(f"Processing {len(symbols)} top symbols")

    total_signals = 0
    for i, symbol in enumerate(symbols):
        if i % 50 == 0:
            logging.info(f"Progress: {i}/{len(symbols)}")

        try:
            # Get price data
            df = get_price_data(conn, symbol)
            if df is None or len(df) < 50:
                continue

            # Compute indicators
            df = compute_indicators(df)
            if df is None:
                continue

            # Detect ranges and generate signals
            df = detect_range_and_signals(df)

            # Insert signals
            inserted = insert_signals(conn, df)
            total_signals += inserted

        except Exception as e:
            logging.warning(f"Error processing {symbol}: {e}")
            continue

    conn.commit()
    logging.info(f"DONE: Inserted {total_signals} range signals from {len(symbols)} symbols")
    conn.close()

if __name__ == '__main__':
    main()
