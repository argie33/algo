#!/usr/bin/env python3
import os
import sys
import json
import requests
import pandas as pd
import numpy as np
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import logging
from dotenv import load_dotenv

# Load environment from .env.local
load_dotenv('/home/stocks/algo/.env.local')

# Setup rotating log file handler to prevent disk exhaustion from excessive logging
from logging.handlers import RotatingFileHandler
log_handler = RotatingFileHandler(
    '/tmp/loadbuysellmonthly.log',
    maxBytes=100*1024*1024,  # 100MB max per file
    backupCount=3  # Keep 3 backup files
)
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadbuysellmonthly.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), log_handler]
)
# Set root logger to WARNING to reduce verbosity
logging.getLogger().setLevel(logging.INFO)

###############################################################################
# ─── Environment & Secrets ───────────────────────────────────────────────────
###############################################################################

# FRED_API_KEY: log a warning and continue with 0 risk-free rate if missing
FRED_API_KEY = os.environ.get('FRED_API_KEY')
if not FRED_API_KEY:
    logging.warning('FRED_API_KEY environment variable is not set. Risk-free rate will be set to 0.')

# Database configuration - Priority: AWS Secrets Manager, then environment variables
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
        logging.info("Using AWS Secrets Manager for database config")
    except Exception as e:
        logging.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")
        DB_SECRET_ARN = None  # Mark as failed to trigger fallback

if not DB_SECRET_ARN or DB_HOST is None:
    # Fall back to local environment variables
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_USER = os.environ.get("DB_USER", "stocks")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_PORT = int(os.environ.get("DB_PORT", 5432))
    DB_NAME = os.environ.get("DB_NAME", "stocks")
    logging.info("Using environment variables for database config")

def get_db_connection():
    # Set statement timeout to 300 seconds (300000 ms) to allow for large queries
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        options='-c statement_timeout=600000'
    )
    return conn

###############################################################################
# 1) DATABASE FUNCTIONS
###############################################################################
def get_symbols_from_db(limit=None, skip_completed=False):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        q = """
          SELECT symbol
            FROM stock_symbols
           WHERE (exchange IN ('NASDAQ','New York Stock Exchange')
              OR etf='Y')
        """
        # OPTIMIZATION: Skip symbols already processed in buy_sell_monthly
        if skip_completed:
            q += " AND symbol NOT IN (SELECT DISTINCT symbol FROM buy_sell_monthly)"

        q += " ORDER BY symbol"

        if limit:
            q += " LIMIT %s"
            cur.execute(q, (limit,))
        else:
            cur.execute(q)
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

def create_buy_sell_table(cur, table_name="buy_sell_monthly"):
    # CRITICAL: Do NOT drop table - preserve existing data for incremental loads
    # cur.execute(f"DROP TABLE IF EXISTS {table_name};")
    cur.execute(f"""
      CREATE TABLE IF NOT EXISTS {table_name} (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20)    NOT NULL,
        timeframe           VARCHAR(10)    NOT NULL,
        date                DATE           NOT NULL,
        open                REAL,
        high                REAL,
        low                 REAL,
        close               REAL,
        volume              BIGINT,
        signal              VARCHAR(10),
        signal_triggered_date DATE,
        buylevel            REAL,
        stoplevel           REAL,
        inposition          BOOLEAN,
        strength            REAL,
        signal_strength REAL,
        confirmed    BOOLEAN,
        -- O'Neill methodology columns
        signal_type  VARCHAR(50),
        pivot_price  REAL,
        buy_zone_start REAL,
        buy_zone_end REAL,
        exit_trigger_1_price REAL,
        exit_trigger_2_price REAL,
        exit_trigger_3_condition VARCHAR(50),
        exit_trigger_3_price REAL,
        exit_trigger_4_condition VARCHAR(50),
        exit_trigger_4_price REAL,
        initial_stop REAL,
        trailing_stop REAL,
        base_type    VARCHAR(50),
        base_length_days INTEGER,
        avg_volume_50d BIGINT,
        volume_surge_pct REAL,
        rs_rating    INTEGER,
        breakout_quality VARCHAR(20),
        risk_reward_ratio REAL,
        profit_target_8pct REAL,
        profit_target_20pct REAL,
        profit_target_25pct REAL,
        risk_pct REAL,
        entry_quality_score REAL,
        market_stage VARCHAR(50),
        stage_number INTEGER,
        stage_confidence REAL,
        substage VARCHAR(50),
        position_size_recommendation REAL,
        current_gain_pct REAL,
        days_in_position INTEGER,
        sell_level REAL,
        mansfield_rs REAL,
        sata_score INTEGER,
        rsi REAL,
        adx REAL,
        atr REAL,
        sma_50 REAL,
        sma_200 REAL,
        ema_21 REAL,
        pct_from_ema21 REAL,
        pct_from_sma50 REAL,
        entry_price REAL,
        UNIQUE(symbol, timeframe, date)
      );
    """)

def insert_symbol_results(cur, symbol, timeframe, df, table_name="buy_sell_monthly"):
    # DEBUG: Check if pivot_price exists in DataFrame
    if 'pivot_price' in df.columns:
        non_null = df['pivot_price'].notna().sum()
        logging.info(f"[{symbol}] pivot_price column exists: {non_null}/{len(df)} non-null values")
    else:
        logging.warning(f"[{symbol}] pivot_price column NOT FOUND!")

    # Calculate metrics
    # REAL DATA ONLY: Keep NaN for rows without enough data for 50-day average
    # Use pd.Int64Dtype() to allow nullable integers (NaN preserved as <NA>)
    df['avg_volume_50d'] = df['volume'].rolling(window=50).mean()
    # Convert to nullable integer type, preserving NaN as pd.NA
    # Keep as float - don't force Int64 conversion as rolling mean produces NaN values

    # === Calculate 30-month SMA for Weinstein Stage Analysis ===
    df['ma_30month'] = df['close'].rolling(window=30).mean()
    # Calculate MA slope to determine if it's rising, falling, or flattening
    ma_slope_window = 6  # Look at 6-month slope
    df['ma_30month_slope'] = df['ma_30month'].diff(periods=ma_slope_window)

    # REAL DATA ONLY: Use None if avg_volume is missing, not fake 0
    df['volume_surge_pct'] = df.apply(
        lambda row: round(((row['volume'] / row['avg_volume_50d'] - 1) * 100), 2)
        if row['avg_volume_50d'] > 0 else None,
        axis=1
    )

    # REAL DATA ONLY: Use None if calculation cannot be performed, not fake 0
    df['risk_reward_ratio'] = df.apply(
        lambda row: round(
            (((row['buyLevel'] * 1.25) - row['buyLevel']) / (row['buyLevel'] - row['stopLevel']))
            if (row['stopLevel'] is not None and row['buyLevel'] is not None and row['stopLevel'] > 0 and row['buyLevel'] > 0 and (row['buyLevel'] - row['stopLevel']) != 0) else None,
            2
        ) if (row['stopLevel'] is not None and row['buyLevel'] is not None and row['stopLevel'] > 0 and row['buyLevel'] > 0 and (row['buyLevel'] - row['stopLevel']) != 0) else None,
        axis=1
    )

    def calc_breakout_quality(row):
        # REAL DATA ONLY: Return None for invalid data, not fake 'WEAK'
        if row['low'] <= 0 or row['avg_volume_50d'] <= 0 or row['volume_surge_pct'] is None or row.get('close') is None:
            return None  # Insufficient data
        # FIX: Use close not low to avoid inflating low-priced stock scores (standard formula)
        daily_range_pct = ((row['high'] - row['low']) / row['close']) * 100
        volume_surge = row['volume_surge_pct']

        # Determine if close is in upper or lower half of daily range (direction matters)
        range_midpoint = (row['high'] + row['low']) / 2
        is_upper_half = row['close'] > range_midpoint

        # Distinguish breakout (upside) vs breakdown (downside)
        if daily_range_pct > 3.0 and volume_surge > 50:
            # Only STRONG quality if move is in expected direction
            signal = row.get('Signal')
            if signal == 'Buy' and is_upper_half:
                return 'STRONG'  # Strong breakout
            elif signal == 'Sell' and not is_upper_half:
                return 'STRONG'  # Strong breakdown
            else:
                return 'MODERATE'  # High volume/range but wrong direction for signal
        elif daily_range_pct > 1.5 and volume_surge > 25:
            return 'MODERATE'
        else:
            return 'WEAK'  # Only return WEAK if data is valid but metrics don't meet thresholds

    # ENABLED: Calculate breakout quality for complete data
    df['breakout_quality'] = df.apply(calc_breakout_quality, axis=1)

    # === Add all calculated fields (REAL DATA ONLY: None if unavailable) ===
    # REAL DATA ONLY: These fields require complex calculations from daily loader
    # For weekly/monthly, set to None rather than calculating incorrect values
    df['signal_type'] = None  # Would need full signal analysis
    df['pivot_price'] = None  # Would need pivot analysis
    df['buy_zone_start'] = None  # Requires technical analysis
    df['buy_zone_end'] = None  # Requires technical analysis
    df['exit_trigger_1_price'] = None  # Requires exit analysis
    df['exit_trigger_2_price'] = None  # Requires exit analysis
    df['exit_trigger_3_condition'] = None  # Requires exit analysis
    df['exit_trigger_3_price'] = None  # Requires exit analysis
    df['exit_trigger_4_condition'] = None  # Requires exit analysis
    df['exit_trigger_4_price'] = None  # Requires exit analysis
    df['initial_stop'] = None  # Requires stop analysis
    df['trailing_stop'] = None  # Requires trailing stop analysis
    # NOTE: base_type is calculated in generate_signals(), don't overwrite here!
    # df['base_type'] = None  # REMOVED: Already calculated in generate_signals
    df['base_length_days'] = None  # Requires base pattern analysis
    df['rs_rating'] = None  # Requires RS rating calculation
    df['current_gain_pct'] = None  # Requires position tracking
    df['days_in_position'] = None  # Requires position tracking

    # Risk calculations - available with buy/stop levels
    df['risk_pct'] = df.apply(
        lambda row: round(((row['buyLevel'] - row['stopLevel']) / row['buyLevel'] * 100), 2)
        if (row['buyLevel'] is not None and row['stopLevel'] is not None and row['buyLevel'] > 0) else None,
        axis=1
    )

    # DEBUG: Log risk_pct calculation results
    risk_pct_filled = df['risk_pct'].notna().sum()
    logging.info(f"[insert_symbol_results] {symbol} {timeframe}: risk_pct calculated: {risk_pct_filled}/{len(df)} rows filled")
    if risk_pct_filled > 0:
        sample_rows = df[df['risk_pct'].notna()][['date', 'buyLevel', 'stopLevel', 'risk_pct']].head(3)
        logging.info(f"[insert_symbol_results] Sample risk_pct: {sample_rows.to_dict('records')}")

    # Profit targets
    df['profit_target_8pct'] = df.apply(
        lambda row: row['buyLevel'] * 1.08 if row['buyLevel'] is not None else None,
        axis=1
    )
    df['profit_target_20pct'] = df.apply(
        lambda row: row['buyLevel'] * 1.20 if row['buyLevel'] is not None else None,
        axis=1
    )
    df['profit_target_25pct'] = df.apply(
        lambda row: row['buyLevel'] * 1.25 if row['buyLevel'] is not None else None,
        axis=1
    )

    # === ENTRY QUALITY SCORE (0-100 based on technical setup) ===
    def calc_entry_quality(row):
        """Calculate entry quality 0-100 based on multiple factors.

        CRITICAL: Requires at least 2 of 4 indicators to be non-None:
        - breakout_quality
        - volume_surge_pct
        - rs_rating
        - price position (close vs maFilter)

        Returns None if insufficient data (no fake scores from 1 data point).
        """
        # Count available indicators (REAL DATA ONLY)
        available_indicators = sum([
            row.get('breakout_quality') is not None,
            row.get('volume_surge_pct') is not None,
            row.get('rs_rating') is not None,
            row.get('close') is not None and row.get('maFilter') is not None
        ])

        # Require at least 2 indicators for valid quality assessment
        if available_indicators < 2:
            return None  # Insufficient data - no fake score

        score = 0  # Start at 0, earn every point

        # Breakout quality (0-40): Quality of price action at entry
        bq = row.get('breakout_quality')
        if bq == 'STRONG':
            score += 40
        elif bq == 'MODERATE':
            score += 20
        # WEAK or None: +0

        # Volume surge (0-25): Confirmation of move
        vs = row.get('volume_surge_pct')
        if vs is not None:
            if vs > 50:
                score += 25
            elif vs > 25:
                score += 15

        # RS Rating (0-20): Relative strength positioning
        rs = row.get('rs_rating')
        if rs is not None:
            if rs > 75:
                score += 20
            elif rs > 50:
                score += 10

        # Price positioning (0-15): Timing relative to short-term MA
        if row.get('close') is not None and row.get('maFilter') is not None:
            if row['close'] > row['maFilter']:
                score += 15

        # Normalize to 0-100 based on available indicators
        max_possible = 25 * available_indicators  # Scale based on how many indicators we have
        normalized_score = (score / max_possible * 100) if max_possible > 0 else 0

        # Cap at 100
        return min(100, max(0, normalized_score))

    df['entry_quality_score'] = df.apply(calc_entry_quality, axis=1)

    # === MARKET STAGE (Stan Weinstein Stage Analysis using 30-month MA) ===
    def detect_market_stage(row, index):
        """Classify into Weinstein's 4-Stage model based on price position relative to 30-month MA"""
        if pd.isna(row.get('close')) or pd.isna(row.get('ma_30month')):
            return None

        close = row['close']
        ma_30month = row['ma_30month']
        ma_slope = row.get('ma_30month_slope')

        # Need sufficient data for MA calculation (30 months minimum)
        if index < 30:
            return None

        # Calculate price position relative to MA
        price_diff_pct = ((close - ma_30month) / ma_30month * 100) if ma_30month > 0 else None
        if price_diff_pct is None:
            return None

        # Detect MA direction - standardized threshold (0.15) across all timeframes for consistency
        is_ma_rising = ma_slope > 0.15 if pd.notna(ma_slope) else False  # FIXED: Standardized to 0.15 (was 1.5)
        is_ma_falling = ma_slope < -0.15 if pd.notna(ma_slope) else False  # FIXED: Standardized to -0.15 (was -1.5)
        is_ma_flat = not is_ma_rising and not is_ma_falling

        # === Weinstein Stage Detection ===

        # Stage 4: Declining - Price below declining MA (most bearish)
        if close < ma_30month and is_ma_falling:
            return 'Stage 4 - Declining'

        # Stage 3: Distribution/Topping - Price at/near flattening MA (improved detection)
        if is_ma_flat and -5 <= price_diff_pct <= 8:  # ✅ Expanded range: -3..5 → -5..8
            return 'Stage 3 - Topping'
        elif is_ma_flat and -8 <= price_diff_pct <= 10:  # ✅ Wider oscillation pattern
            return 'Stage 3 - Topping'

        # Stage 2: Advancing - Price above rising MA (most bullish)
        if close > ma_30month and is_ma_rising:
            return 'Stage 2 - Advancing'
        # ✅ NEW: If price clearly above MA, treat as advance even if MA slope weak
        if close > ma_30month and not is_ma_rising:
            return 'Stage 2 - Advancing'

        # Stage 1: Basing - Price oscillating around flat/rising MA or below rising MA
        if close < ma_30month and (is_ma_rising or is_ma_flat):
            return 'Stage 1 - Basing'

        # Default to Stage 1 if price is near MA without clear trend
        if -3 <= price_diff_pct <= 5:
            return 'Stage 1 - Basing'

        return None

    # ENABLED: Detect market stage for complete data
    df['market_stage'] = df.apply(
        lambda row: detect_market_stage(row, row.name), axis=1
    )