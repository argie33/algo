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
    '/tmp/loadbuysell_etf_weekly.log',
    maxBytes=100*1024*1024,  # 100MB max per file
    backupCount=3  # Keep 3 backup files
)
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadbuysell_etf_weekly.py"
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
FRED_API_KEY = os.environ.get('FRED_API_KEY')
if not FRED_API_KEY:
    logging.warning('FRED_API_KEY environment variable is not set. Proceeding with risk-free rate = 0.')

# Support both local environment variables and AWS Secrets Manager
if os.environ.get("DB_HOST"):
    logging.info("Using local environment DB configuration")
    DB_HOST     = os.environ.get("DB_HOST", "localhost")
    DB_USER     = os.environ.get("DB_USER", "stocks")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "bed0elAn")
    DB_PORT     = int(os.environ.get("DB_PORT", 5432))
    DB_NAME     = os.environ.get("DB_NAME", "stocks")
elif os.environ.get("DB_SECRET_ARN"):
    logging.info("Using AWS Secrets Manager for DB configuration")
    try:
        SECRET_ARN   = os.environ.get("DB_SECRET_ARN")
        sm_client   = boto3.client("secretsmanager")
        secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
        creds       = json.loads(secret_resp["SecretString"])
        DB_USER     = creds["username"]
        DB_PASSWORD = creds["password"]
        DB_HOST     = creds["host"]
        DB_PORT     = int(creds.get("port", 5432))
        DB_NAME     = creds["dbname"]
    except Exception as e:
        logging.error(f"Failed to fetch from AWS Secrets Manager: {e}")
        raise
else:
    logging.error("DB_HOST or DB_SECRET_ARN not set. Please set local DB environment variables or AWS_SECRET_ARN")
    raise ValueError("Database configuration not provided")

def get_db_connection():
    # Set statement timeout to 30 seconds (30000 ms)
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
            FROM etf_symbols
           WHERE etf='Y'
        """
        # OPTIMIZATION: Skip symbols already processed in buy_sell_weekly_etf
        if skip_completed:
            q += " AND symbol NOT IN (SELECT DISTINCT symbol FROM buy_sell_weekly_etf)"

        if limit:
            q += " LIMIT %s"
            cur.execute(q, (limit,))
        else:
            cur.execute(q)
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

def create_buy_sell_table(cur, table_name="buy_sell_weekly_etf"):
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
        -- Technical indicators
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

def insert_symbol_results(cur, symbol, timeframe, df, table_name="buy_sell_weekly_etf"):
    # DEBUG: Check if pivot_price exists in DataFrame
    if 'pivot_price' in df.columns:
        non_null = df['pivot_price'].notna().sum()
        logging.info(f"[{symbol}] pivot_price column exists: {non_null}/{len(df)} non-null values")
    else:
        logging.warning(f"[{symbol}] pivot_price column NOT FOUND!")

    # Calculate metrics
    df['avg_volume_50d'] = df['volume'].rolling(window=50).mean().fillna(0).astype('int64')

    # === Calculate 30-week SMA for Weinstein Stage Analysis ===
    df['ma_30week'] = df['close'].rolling(window=30).mean()
    # Calculate MA slope to determine if it's rising, falling, or flattening
    ma_slope_window = 3  # Look at 3-week slope
    df['ma_30week_slope'] = df['ma_30week'].diff(periods=ma_slope_window)

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
            if (row['stopLevel'] is not None and row['stopLevel'] > 0 and row['buyLevel'] is not None and row['buyLevel'] > 0 and (row['buyLevel'] - row['stopLevel']) != 0) else None,
            2
        ) if (row['stopLevel'] is not None and row['stopLevel'] > 0 and row['buyLevel'] is not None and row['buyLevel'] > 0 and (row['buyLevel'] - row['stopLevel']) != 0) else None,
        axis=1
    )

    def calc_breakout_quality(row):
        # REAL DATA ONLY: Return None for invalid data, not fake 'WEAK'
        if row['low'] <= 0 or row['avg_volume_50d'] <= 0 or row['volume_surge_pct'] is None or row.get('close') is None:
            return None  # Insufficient data
        daily_range_pct = ((row['high'] - row['low']) / row['low']) * 100
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
        # ✅ FIXED: Add pd.notna() check in addition to is not None (NaN is not None!)
        if row.get('close') is not None and row.get('maFilter') is not None and pd.notna(row['close']) and pd.notna(row['maFilter']):
            if row['close'] > row['maFilter']:
                score += 15

        # Normalize to 0-100 based on available indicators
        max_possible = 25 * available_indicators  # Scale based on how many indicators we have
        normalized_score = (score / max_possible * 100) if max_possible > 0 else 0

        # Cap at 100
        return min(100, max(0, normalized_score))

    df['entry_quality_score'] = df.apply(calc_entry_quality, axis=1)

    # === MARKET STAGE (Stan Weinstein Stage Analysis using 30-week MA) ===
    def detect_market_stage(row, index):
        """Classify into Weinstein's 4-Stage model based on price position relative to 30-week MA"""
        if pd.isna(row.get('close')) or pd.isna(row.get('ma_30week')):
            return None

        close = row['close']
        ma_30week = row['ma_30week']
        ma_slope = row.get('ma_30week_slope')

        # Need sufficient data for MA calculation (30 weeks minimum)
        if index < 30:
            return None

        # Calculate price position relative to MA
        # ✅ FIXED: Add NaN/None check before comparison to prevent TypeError
        price_diff_pct = ((close - ma_30week) / ma_30week * 100) if (ma_30week is not None and not pd.isna(ma_30week) and ma_30week > 0) else None
        if price_diff_pct is None:
            return None

        # Detect MA direction - tuned thresholds for better discrimination
        is_ma_rising = ma_slope > 0.75 if pd.notna(ma_slope) else False  # ✅ Tuned: 0.5 → 0.75
        is_ma_falling = ma_slope < -0.75 if pd.notna(ma_slope) else False  # ✅ Tuned: -0.5 → -0.75
        is_ma_flat = not is_ma_rising and not is_ma_falling

        # === Weinstein Stage Detection ===

        # Stage 4: Declining - Price below declining MA (most bearish)
        if close < ma_30week and is_ma_falling:
            return 'Stage 4 - Declining'

        # Stage 3: Distribution/Topping - Price at/near flattening MA (improved detection)
        if is_ma_flat and -5 <= price_diff_pct <= 8:  # ✅ Expanded range: -3..5 → -5..8
            return 'Stage 3 - Topping'
        elif is_ma_flat and -8 <= price_diff_pct <= 10:  # ✅ Wider oscillation pattern
            return 'Stage 3 - Topping'

        # Stage 2: Advancing - Price above rising MA (most bullish)
        if close > ma_30week and is_ma_rising:
            return 'Stage 2 - Advancing'
        # ✅ NEW: If price clearly above MA, treat as advance even if MA slope weak
        if close > ma_30week and not is_ma_rising:
            return 'Stage 2 - Advancing'

        # Stage 1: Basing - Price oscillating around flat/rising MA or below rising MA
        if close < ma_30week and (is_ma_rising or is_ma_flat):
            return 'Stage 1 - Basing'

        # Default to Stage 1 if price is near MA without clear trend
        if -3 <= price_diff_pct <= 5:
            return 'Stage 1 - Basing'

        return None

    df['market_stage'] = [detect_market_stage(row, idx) for idx, row in df.iterrows()]

    # === STAGE NUMBER (Extract numeric stage from market_stage) ===
    df['stage_number'] = df['market_stage'].apply(
        lambda x: int(x.split()[1]) if pd.notna(x) and 'Stage' in str(x) else None
    )

    # === STAGE CONFIDENCE (Based on signal strength and price action) ===
    def calc_stage_confidence(row):
        """Calculate confidence in market stage (0-100) - based on distance from 30-week MA"""
        if pd.isna(row.get('market_stage')):
            return None

        close = row['close']
        ma_30week = row.get('ma_30week')  # ✅ FIXED: Use ma_30week not buyLevel!

        if pd.isna(ma_30week) or ma_30week is None or ma_30week <= 0:
            return None

        # Distance from 30-week MA as % (matches stage detection logic)
        distance_pct = abs((close - ma_30week) / ma_30week * 100)

        # Confidence based on distance from MA
        if distance_pct > 15:
            return 95  # Very clear stage separation
        elif distance_pct > 10:
            return 85
        elif distance_pct > 5:
            return 75  # Moderate clarity
        elif distance_pct > 2:
            return 60  # Weak clarity
        else:
            return 40  # Very close to MA (ambiguous)

    df['stage_confidence'] = df.apply(calc_stage_confidence, axis=1)

    # === SUBSTAGE (Early vs Late in stage) ===
    def detect_substage(row):
        """Detect substage within the 4-stage cycle - Distinguishes breakout vs breakdown"""
        stage = row.get('market_stage')
        if pd.isna(stage):
            return None

        if 'Basing' in str(stage):
            # Check if early or late in basing
            vol_surge = row.get('volume_surge_pct')
            if vol_surge is not None and vol_surge > 30:
                # HIGH VOLUME: Distinguish breakout (upside) vs breakdown (downside)
                signal = row.get('Signal')
                risk_reward = row.get('risk_reward_ratio')

                # Breakout = Buy signal with positive risk/reward
                if signal == 'Buy' and (risk_reward is None or pd.isna(risk_reward) or risk_reward > 0):
                    return 'Late Basing - Breakout Imminent'
                # Breakdown = Sell signal or negative risk/reward
                elif signal == 'Sell' or (risk_reward is not None and not pd.isna(risk_reward) and risk_reward < 0):
                    return 'Late Basing - Breakdown'
                # Ambiguous = default to Breakout Imminent
                else:
                    return 'Late Basing - Breakout Imminent'
            return 'Early Basing'

        elif 'Advancing' in str(stage):
            # Check trend strength
            strength = row.get('strength')
            if strength is not None and strength > 70:
                return 'Strong Advance'
            return 'Early Advance'

        elif 'Topping' in str(stage):
            return 'Late Stage - Exit'

        elif 'Declining' in str(stage):
            return 'Distribution'

        return None

    df['substage'] = df.apply(detect_substage, axis=1)

    df['sell_level'] = None  # Not applicable for buy signals

    insert_q = f"""
      INSERT INTO {table_name} (
        symbol, timeframe, date,
        open, high, low, close, volume,
        signal, signal_triggered_date, buylevel, stoplevel, inposition, strength,
        signal_type, pivot_price, buy_zone_start, buy_zone_end,
        exit_trigger_1_price, exit_trigger_2_price, exit_trigger_3_condition, exit_trigger_3_price,
        exit_trigger_4_condition, exit_trigger_4_price, initial_stop, trailing_stop,
        base_type, base_length_days, avg_volume_50d, volume_surge_pct,
        rs_rating, breakout_quality, risk_reward_ratio,
        profit_target_8pct, profit_target_20pct, profit_target_25pct,
        risk_pct, entry_quality_score, market_stage, stage_number, stage_confidence, substage,
        position_size_recommendation, current_gain_pct, days_in_position, sell_level,
        mansfield_rs, sata_score,
        rsi, adx, atr, sma_50, sma_200, ema_21, pct_from_ema21, pct_from_sma50, entry_price
      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (symbol, timeframe, date) DO UPDATE SET
        open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close, volume = EXCLUDED.volume,
        signal = EXCLUDED.signal, signal_triggered_date = EXCLUDED.signal_triggered_date, buylevel = EXCLUDED.buylevel, stoplevel = EXCLUDED.stoplevel, inposition = EXCLUDED.inposition, strength = EXCLUDED.strength,
        signal_type = EXCLUDED.signal_type, pivot_price = EXCLUDED.pivot_price, buy_zone_start = EXCLUDED.buy_zone_start, buy_zone_end = EXCLUDED.buy_zone_end,
        exit_trigger_1_price = EXCLUDED.exit_trigger_1_price, exit_trigger_2_price = EXCLUDED.exit_trigger_2_price, exit_trigger_3_condition = EXCLUDED.exit_trigger_3_condition, exit_trigger_3_price = EXCLUDED.exit_trigger_3_price,
        exit_trigger_4_condition = EXCLUDED.exit_trigger_4_condition, exit_trigger_4_price = EXCLUDED.exit_trigger_4_price, initial_stop = EXCLUDED.initial_stop, trailing_stop = EXCLUDED.trailing_stop,
        base_type = EXCLUDED.base_type, base_length_days = EXCLUDED.base_length_days, avg_volume_50d = EXCLUDED.avg_volume_50d, volume_surge_pct = EXCLUDED.volume_surge_pct,
        rs_rating = EXCLUDED.rs_rating, breakout_quality = EXCLUDED.breakout_quality, risk_reward_ratio = EXCLUDED.risk_reward_ratio, current_gain_pct = EXCLUDED.current_gain_pct, days_in_position = EXCLUDED.days_in_position,
        market_stage = EXCLUDED.market_stage, stage_number = EXCLUDED.stage_number, stage_confidence = EXCLUDED.stage_confidence, substage = EXCLUDED.substage, entry_quality_score = EXCLUDED.entry_quality_score,
        risk_pct = EXCLUDED.risk_pct, position_size_recommendation = EXCLUDED.position_size_recommendation, profit_target_8pct = EXCLUDED.profit_target_8pct, profit_target_20pct = EXCLUDED.profit_target_20pct, profit_target_25pct = EXCLUDED.profit_target_25pct, sell_level = EXCLUDED.sell_level,
        mansfield_rs = EXCLUDED.mansfield_rs, sata_score = EXCLUDED.sata_score,
        rsi = EXCLUDED.rsi, adx = EXCLUDED.adx, atr = EXCLUDED.atr, sma_50 = EXCLUDED.sma_50, sma_200 = EXCLUDED.sma_200, ema_21 = EXCLUDED.ema_21, pct_from_ema21 = EXCLUDED.pct_from_ema21, pct_from_sma50 = EXCLUDED.pct_from_sma50, entry_price = EXCLUDED.entry_price
      RETURNING xmax;
    """
    # === POSITION SIZE RECOMMENDATION (based on risk) ===
    df['position_size_recommendation'] = df.apply(
        lambda row: round(
            min(5.0, 0.5 / row['risk_pct'] * 100),  # Risk 0.5% of account per trade
            2
        ) if (row['risk_pct'] is not None and row['risk_pct'] > 0) else None,
        axis=1
    )

    # === GET MANSFIELD RS FROM STOCK_SCORES ===
    # DISABLED: mansfield_rs column was moved out of stock_scores table
    # This query was causing loader to crash. Keeping fields as None for now.
    df['mansfield_rs'] = None
    df['sata_score'] = None
    # Previous code that queried non-existent column is commented out:
    # try:
    #     stock_scores_q = "SELECT date, mansfield_rs FROM stock_scores WHERE symbol = %s"
    #     cur.execute(stock_scores_q, (symbol,))
    #     scores_rows = cur.fetchall()
    #     if scores_rows:
    #         rs_by_date = {row[0]: row[1] for row in scores_rows if row[1] is not None}
    #         df['mansfield_rs'] = df['date'].apply(
    #             lambda d: rs_by_date.get(d.date() if hasattr(d, 'date') else d)
    #         )
    # except Exception as e:
    #     logging.debug(f"Could not fetch mansfield_rs for {symbol}: {e}")

    # === CALCULATE SATA SCORE (0-10 scale) ===
    # SATA = Stage Analysis Technical Attributes
    # Components: stage_number (1-4) + RS strength + momentum confirmation + volume
    def calculate_sata(row):
        """Calculate SATA score 0-10 based on technical attributes"""
        try:
            stage_num = row.get('stage_number')
            rs_rating_val = row.get('rs_rating')
            vol_surge = row.get('volume_surge_pct')
            strength_val = row.get('strength')

            # If critical data missing, return None
            if stage_num is None or pd.isna(stage_num):
                return None

            # Base score from stage number (1-4 maps to 1-4 points)
            sata = float(stage_num)

            # RS strength bonus (RS rating 0-99, add up to 3 points)
            if rs_rating_val is not None and not pd.isna(rs_rating_val):
                rs_bonus = min(3.0, (float(rs_rating_val) / 99.0) * 3.0)
                sata += rs_bonus

            # Volume surge confirmation (add up to 2 points)
            if vol_surge is not None and not pd.isna(vol_surge):
                vol_bonus = min(2.0, (float(vol_surge) / 100.0) * 2.0)
                sata += vol_bonus

            # Strength/momentum confirmation (add up to 1 point)
            if strength_val is not None and not pd.isna(strength_val):
                strength_bonus = min(1.0, (float(strength_val) / 100.0) * 1.0)
                sata += strength_bonus

            # Clamp to 0-10 range
            return max(0, min(10, int(round(sata))))
        except Exception as e:
            return None

    df['sata_score'] = df.apply(calculate_sata, axis=1)

    # === CRITICAL: Replace ALL NaN values with None before INSERT ===
    # PostgreSQL cannot handle NaN floats/ints - convert all numeric NaNs to None
    # This must happen BEFORE the insert loop and for ALL columns (float, int, object)
    for col in df.columns:
        # Convert all NaN/NaT values to None for ANY column type
        if df[col].dtype == 'object' or df[col].dtype.name.startswith(('float', 'int')):
            df[col] = df[col].astype('object').where(pd.notnull(df[col]), None)
        else:
            # For other dtypes (bool, datetime, etc), also convert NaN to None
            df[col] = df[col].where(pd.notnull(df[col]), None)

    # === EXTRA SAFETY: Explicitly handle position_size_recommendation and sata_score for NaN ===
    # These are calculated after the initial columns and may contain NaN values
    if 'position_size_recommendation' in df.columns:
        df['position_size_recommendation'] = df['position_size_recommendation'].where(pd.notnull(df['position_size_recommendation']), None)
    if 'sata_score' in df.columns:
        df['sata_score'] = df['sata_score'].where(pd.notnull(df['sata_score']), None)

    inserted = 0
    skipped = 0
    for idx, row in df.iterrows():
        try:
            # Check for NaNs in CORE required fields only (price data + signals)
            # Allow NULL for calculated fields like buyLevel/stopLevel (derived from pivot data)
            # Convert NaN to None for strength field (optional field, not required)
            strength_val = row.get('strength')
            if pd.isna(strength_val):
                strength_val = None

            # Only validate actual required core fields (price data + signals)
            core_fields = {
                'open': row.get('open'),
                'high': row.get('high'),
                'low': row.get('low'),
                'close': row.get('close'),
                'volume': row.get('volume'),
                'Signal': row.get('Signal'),
                'inPosition': row.get('inPosition')
            }

            null_fields = [field for field, val in core_fields.items() if pd.isnull(val)]
            if null_fields:
                logging.warning(f"Skipping row {idx} for {symbol}: NULL fields = {null_fields}, values = {[(f, core_fields[f]) for f in null_fields]}")
                skipped += 1
                continue

            # CRITICAL: Only insert Buy/Sell signals, skip 'None' signals
            signal = row.get('Signal')
            if signal not in ('Buy', 'Sell'):
                skipped += 1
                continue

            # Helper function to safely convert NaN to None
            def safe_float(val):
                if val is None or pd.isna(val):
                    return None
                return float(val)

            def safe_int(val):
                if val is None or pd.isna(val):
                    return None
                return int(val)

            def safe_bool(val):
                if val is None or pd.isna(val):
                    return None
                return bool(val)

            # Handle optional fields with None (REAL DATA ONLY)
            avg_vol = row.get('avg_volume_50d')
            if pd.isna(avg_vol) or avg_vol is None:
                avg_vol = None
            else:
                avg_vol = int(avg_vol)

            vol_surge = row.get('volume_surge_pct')
            if pd.isna(vol_surge) or vol_surge is None:
                vol_surge = None
            else:
                vol_surge = float(vol_surge)

            risk_reward = row.get('risk_reward_ratio')
            if pd.isna(risk_reward) or risk_reward is None:
                risk_reward = None
            else:
                risk_reward = float(risk_reward)

            breakout_qual = row.get('breakout_quality')
            if pd.isna(breakout_qual) or breakout_qual is None:
                breakout_qual = None

            # Get all calculated fields (most will be None for weekly/monthly)
            signal_type = row.get('Signal') if row.get('Signal') in ('Buy', 'Sell') else None
            pivot_price = row.get('pivot_price')
            buy_zone_start = row.get('buy_zone_start')
            buy_zone_end = row.get('buy_zone_end')
            exit_1 = row.get('exit_trigger_1_price')
            exit_2 = row.get('exit_trigger_2_price')
            exit_3_cond = row.get('exit_trigger_3_condition')
            exit_3_price = row.get('exit_trigger_3_price')
            exit_4_cond = row.get('exit_trigger_4_condition')
            exit_4_price = row.get('exit_trigger_4_price')
            initial_stop = row.get('initial_stop')
            trailing_stop = row.get('trailing_stop')
            base_type = row.get('base_type')
            base_length = row.get('base_length_days')
            rs_rating = row.get('rs_rating')
            current_gain = row.get('current_gain_pct')
            days_held = row.get('days_in_position')
            entry_qual = row.get('entry_quality_score')
            if pd.isna(entry_qual):
                entry_qual = None

            market_stage = row.get('market_stage')
            stage_num = row.get('stage_number')
            if pd.isna(stage_num):
                stage_num = None
            elif stage_num is not None:
                try:
                    stage_num = int(float(stage_num))  # Convert to float first to handle any NaN, then int
                except (ValueError, TypeError):
                    stage_num = None

            stage_conf = row.get('stage_confidence')
            if pd.isna(stage_conf):
                stage_conf = None
            elif stage_conf is not None:
                try:
                    stage_conf = float(stage_conf)
                except (ValueError, TypeError):
                    stage_conf = None

            substage = row.get('substage')
            profit_8 = row.get('profit_target_8pct')
            if pd.isna(profit_8):
                profit_8 = None
            else:
                try:
                    profit_8 = float(profit_8)
                except (ValueError, TypeError):
                    profit_8 = None
            profit_20 = row.get('profit_target_20pct')
            if pd.isna(profit_20):
                profit_20 = None
            else:
                try:
                    profit_20 = float(profit_20)
                except (ValueError, TypeError):
                    profit_20 = None
            profit_25 = row.get('profit_target_25pct')
            if pd.isna(profit_25):
                profit_25 = None
            else:
                try:
                    profit_25 = float(profit_25)
                except (ValueError, TypeError):
                    profit_25 = None
            risk_pct = row.get('risk_pct')
            if pd.isna(risk_pct) or risk_pct is None:
                risk_pct = None
            else:
                try:
                    risk_pct = float(risk_pct)
                except (ValueError, TypeError):
                    risk_pct = None
            pos_size = row.get('position_size_recommendation')
            if pd.isna(pos_size) or pos_size is None:
                pos_size = None
            else:
                try:
                    pos_size = float(pos_size)
                except (ValueError, TypeError):
                    pos_size = None
            sell_level = row.get('sell_level')
            if pd.isna(sell_level) or sell_level is None:
                sell_level = None
            else:
                try:
                    sell_level = float(sell_level)
                except (ValueError, TypeError):
                    sell_level = None
            mansfield_rs = row.get('mansfield_rs')
            if mansfield_rs is not None:
                mansfield_rs = float(mansfield_rs)

            # pos_size and sata_score - just convert safely
            sata_score = row.get('sata_score')
            try:
                if sata_score is None:
                    sata_score = None
                else:
                    sata_score = int(float(sata_score))  # Convert to float first to handle NaN, then int
            except (ValueError, TypeError, OverflowError):
                sata_score = None

            # Extract technical indicators
            rsi_val = safe_float(row.get('rsi'))
            adx_val = safe_float(row.get('adx'))
            atr_val = safe_float(row.get('atr'))
            sma_50_val = safe_float(row.get('sma_50'))
            sma_200_val = safe_float(row.get('sma_200'))
            ema_21_val = safe_float(row.get('ema_21'))
            pct_from_ema21_val = safe_float(row.get('pct_from_ema21'))
            pct_from_sma50_val = safe_float(row.get('pct_from_sma50'))
            entry_price_val = safe_float(row.get('buyLevel')) if row['Signal'] == 'Buy' else None

            # Set signal_triggered_date: if signal is Buy/Sell, use the current row date; otherwise NULL
            row_date = row['date'].date()
            signal_triggered_date = row_date if row['Signal'] in ('Buy', 'Sell') else None

            try:
                cur.execute(insert_q, (
                    symbol,
                    timeframe,
                    row_date,
                    float(row['open']), float(row['high']), float(row['low']),
                    float(row['close']), int(row['volume']),
                    row['Signal'], signal_triggered_date, safe_float(row.get('buyLevel')),
                    safe_float(row.get('stopLevel')), safe_bool(row.get('inPosition')), safe_float(row.get('strength')),
                    signal_type, pivot_price, buy_zone_start, buy_zone_end,
                    exit_1, exit_2, exit_3_cond, exit_3_price,
                    exit_4_cond, exit_4_price, initial_stop, trailing_stop,
                    base_type, base_length, avg_vol, vol_surge,
                    rs_rating, breakout_qual, risk_reward,
                    profit_8, profit_20, profit_25,
                    risk_pct, entry_qual, market_stage, stage_num, stage_conf, substage,
                    pos_size, current_gain, days_held, sell_level,
                    mansfield_rs, sata_score,
                    rsi_val, adx_val, atr_val, sma_50_val, sma_200_val, ema_21_val, pct_from_ema21_val, pct_from_sma50_val, entry_price_val
                ))
                cur.connection.commit()  # Commit after each successful insert
                inserted += 1
            except Exception as insert_err:
                # Rollback failed transaction and continue
                cur.connection.rollback()
                logging.error(f"Insert failed for {symbol} {timeframe} row {idx}: {insert_err}")
                skipped += 1
        except Exception as e:
            logging.error(f"Field processing failed for {symbol} {timeframe} row {idx}: {e} | row={row}")
            skipped += 1
    logging.info(f"Inserted {inserted} rows, skipped {skipped} rows for {symbol} {timeframe}")

###############################################################################
# 2) RISK-FREE RATE (FRED)
###############################################################################
def get_risk_free_rate_fred(api_key):
    url = (
      "https://api.stlouisfed.org/fred/series/observations"
      f"?series_id=DGS3MO&api_key={api_key}&file_type=json"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
    return float(obs[-1]["value"]) / 100.0 if obs else 0.0

###############################################################################
# 3) FETCH FROM DB (prices + technicals)
###############################################################################
def fetch_symbol_from_db(symbol, timeframe):
    """Fetch PRICE DATA ONLY - all technical calculations done inline"""
    tf = timeframe.lower()
    price_table_map = {
        "daily": "etf_price_daily",
        "weekly": "etf_price_weekly",
        "monthly": "etf_price_monthly"
    }
    if tf not in price_table_map:
        raise ValueError(f"Invalid timeframe: {timeframe}")
    price_table = price_table_map[tf]

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        sql = f"""
          SELECT date, open, high, low, close, volume
          FROM {price_table}
          WHERE symbol = %s
          ORDER BY date ASC;
        """
        logging.info(f"[fetch_symbol_from_db] Executing SQL for {symbol} {timeframe}")
        cur.execute(sql, (symbol,))
        rows = cur.fetchall()
        logging.info(f"[fetch_symbol_from_db] Got {len(rows)} rows for {symbol} {timeframe}")
    except Exception as e:
        logging.error(f"[fetch_symbol_from_db] SQL error for {symbol} {timeframe}: {e}")
        rows = []
    finally:
        cur.close()
        conn.close()

    if not rows:
        return pd.DataFrame()

    # CRITICAL: Skip symbols with insufficient data for SMA-50 calculation
    if len(rows) < 50:
        logging.warning(f"Skipping {symbol} {timeframe}: insufficient data ({len(rows)} bars, need 50+ for SMA-50)")
        return pd.DataFrame()

    # CRITICAL: Skip symbols with excessive zero-volume data (causes rolling window to hang)
    zero_volume_count = sum(1 for r in rows if r.get('volume', 0) == 0)
    zero_volume_pct = (zero_volume_count / len(rows)) * 100 if rows else 0
    if zero_volume_pct > 50:
        logging.warning(f"Skipping {symbol} {timeframe}: {zero_volume_pct:.1f}% zero-volume bars (causes calculation hang)")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    num_cols = ['open','high','low','close','volume']
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.reset_index(drop=True)

###############################################################################
# 4) SIGNAL STRENGTH CALCULATION
###############################################################################
def calculate_signal_strength(df, index):
    """Calculate signal strength score (0-100) for a given row"""
    try:
        row = df.iloc[index]
        signal_type = row.get('Signal', 'None')

        if signal_type == 'None':
            return None  # No real signal - return None instead of fake 50.0

        # Get required values - REAL DATA ONLY
        # Return None if critical technical data is missing
        rsi = row.get('rsi')
        close = row.get('close')
        volume = row.get('volume')

        # If critical data missing, can't calculate meaningful signal strength
        if pd.isna(rsi) or pd.isna(close) or pd.isna(volume):
            return None

        # Optional technical indicators (use None if missing, not fake defaults)
        adx = row.get('adx')
        high = row.get('high')
        low = row.get('low')
        sma_200 = row.get('sma_200')
        atr = row.get('atr')
        pivot_high = row.get('pivot_high')
        pivot_low = row.get('pivot_low')
        
        # Calculate average volume (20-period rolling average)
        start_idx = max(0, index - 19)
        avg_volume = df.iloc[start_idx:index+1]['volume'].mean()
        
        strength = 0.0
        
        # 1. Technical Momentum (30%)
        if signal_type == 'Buy':
            if rsi > 70:
                strength += 12  # Very bullish
            elif rsi > 60:
                strength += 9   # Bullish
            elif rsi > 50:
                strength += 6   # Neutral bullish
            else:
                strength += 3   # Weak
        elif signal_type == 'Sell':
            if rsi < 30:
                strength += 12  # Very bearish
            elif rsi < 40:
                strength += 9   # Bearish
            elif rsi < 50:
                strength += 6   # Neutral bearish
            else:
                strength += 3   # Weak
        
        # ADX trend strength (only if ADX data available)
        if adx is not None:
            if adx > 40:
                strength += 9   # Very strong trend
            elif adx > 30:
                strength += 6   # Strong trend
            elif adx > 20:
                strength += 3   # Moderate trend
            else:
                strength += 1   # Weak trend

        # Price vs SMA-50 (only if SMA-50 data available)
        if sma_200 is not None:
            if signal_type == 'Buy' and close > sma_200:
                price_above_sma = ((close - sma_200) / sma_200) * 100
                strength += min(9, max(0, price_above_sma * 3))
            elif signal_type == 'Sell' and close < sma_200:
                price_below_sma = ((sma_200 - close) / sma_200) * 100
                strength += min(9, max(0, price_below_sma * 3))
        
        # 2. Volume Confirmation (25%)
        if avg_volume > 0:
            volume_ratio = volume / avg_volume
            if volume_ratio > 2.0:
                strength += 25  # Exceptional volume
            elif volume_ratio > 1.5:
                strength += 20  # High volume
            elif volume_ratio > 1.2:
                strength += 15  # Above average volume
            elif volume_ratio > 0.8:
                strength += 10  # Normal volume
            else:
                strength += 5   # Low volume
        else:
            strength += 12.5  # Default if no volume data
        
        # 3. Price Action (25%) - only if high/low data available
        if high is not None and low is not None and high != low:
            close_position = (close - low) / (high - low)
            if signal_type == 'Buy':
                if close_position > 0.8:
                    strength += 25  # Strong bullish close
                elif close_position > 0.6:
                    strength += 19  # Good bullish close
                elif close_position > 0.4:
                    strength += 12  # Neutral
                else:
                    strength += 6   # Weak bullish close
            elif signal_type == 'Sell':
                if close_position < 0.2:
                    strength += 25  # Strong bearish close
                elif close_position < 0.4:
                    strength += 19  # Good bearish close
                elif close_position < 0.6:
                    strength += 12  # Neutral
                else:
                    strength += 6   # Weak bearish close

        # 4. Volatility Context (10%) - only if ATR data available
        if atr is not None and close > 0 and atr > 0:
            atr_percentage = (atr / close) * 100
            if 1.5 <= atr_percentage <= 3.0:
                strength += 10  # Ideal volatility
            elif 1.0 <= atr_percentage <= 4.0:
                strength += 8   # Good volatility
            elif 0.5 <= atr_percentage <= 5.0:
                strength += 6   # Acceptable volatility
            elif atr_percentage > 5.0:
                strength += 3   # High volatility (risky)
            else:
                strength += 4   # Low volatility (less opportunity)
        else:
            strength += 5  # Default if no volatility data
        
        # 5. Breakout Magnitude (10%) - only if pivot data available
        if signal_type == 'Buy' and pivot_high is not None and pivot_high > 0:
            breakout_percent = ((close - pivot_high) / pivot_high) * 100
            if breakout_percent > 3.0:
                strength += 10  # Strong breakout
            elif breakout_percent > 1.5:
                strength += 7   # Good breakout
            elif breakout_percent > 0.5:
                strength += 5   # Moderate breakout
            else:
                strength += 2   # Weak breakout
        elif signal_type == 'Sell' and pivot_low is not None and pivot_low > 0:
            breakdown_percent = ((pivot_low - close) / pivot_low) * 100
            if breakdown_percent > 3.0:
                strength += 10  # Strong breakdown
            elif breakdown_percent > 1.5:
                strength += 7   # Good breakdown
            elif breakdown_percent > 0.5:
                strength += 5   # Moderate breakdown
            else:
                strength += 2   # Weak breakdown
        
        return min(100.0, max(0.0, strength))
        
    except Exception as e:
        logging.warning(f"Error calculating signal strength at index {index}: {e}")
        return None  # Error - return None instead of fake 50.0

###############################################################################
# 5) TECHNICAL INDICATOR CALCULATIONS (Inline - No External Dependencies)
###############################################################################

def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index"""
    try:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        return pd.Series([None] * len(prices), index=prices.index)

def calculate_atr(high, low, close, period=14):
    """Calculate Average True Range"""
    try:
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr
    except Exception as e:
        return pd.Series([None] * len(high), index=high.index)

def calculate_adx(high, low, close, period=14):
    """Calculate Average Directional Index (simplified)"""
    try:
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_val = tr.rolling(window=period).mean()

        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr_val)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr_val)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        return adx
    except Exception as e:
        return pd.Series([None] * len(high), index=high.index)

def calculate_sma(prices, period):
    """Calculate Simple Moving Average"""
    try:
        return prices.rolling(window=period).mean()
    except Exception as e:
        return pd.Series([None] * len(prices), index=prices.index)

def calculate_ema(prices, period):
    """Calculate Exponential Moving Average"""
    try:
        return prices.ewm(span=period, adjust=False).mean()
    except Exception as e:
        return pd.Series([None] * len(prices), index=prices.index)

###############################################################################
# 6) SIGNAL GENERATION & IN-POSITION LOGIC - TradingView "Breakout Trend Follower" Strategy
###############################################################################
def generate_signals(df, pvtLenL=3, pvtLenR=3, useMaFilter=True, maLength=50, lookbackLen=15, shunt=1):
    """
    Implements TradingView "Breakout Trend Follower" strategy using swing point detection:
    - Swing High: bar is highest among all bars in [i-pvtLenL...i...i+pvtLenR]
    - Swing Low: bar is lowest among all bars in [i-pvtLenL...i...i+pvtLenR]
    - BUY when price breaks above swing high AND price > 50-MA
    - SELL when price breaks below swing low
    - State machine: only buy when flat, only sell when in position
    """

    # === CALCULATE ALL TECHNICAL INDICATORS INLINE ===
    # Self-contained - no dependencies on technical_data table
    logging.info("   Calculating technical indicators (SMA-50, SMA-200, RSI, ATR, ADX, EMA-21)...")

    df['sma_50'] = calculate_sma(df['close'], 50)
    df['sma_200'] = calculate_sma(df['close'], 200)
    df['rsi'] = calculate_rsi(df['close'], 14)
    df['atr'] = calculate_atr(df['high'], df['low'], df['close'], 14)
    df['adx'] = calculate_adx(df['high'], df['low'], df['close'], 14)

    # Calculate EMA-21 for shorter-term trend
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()

    # Calculate percentage distance from moving averages
    df['pct_from_sma50'] = ((df['close'] - df['sma_50']) / df['sma_50'] * 100).round(2)
    df['pct_from_ema21'] = ((df['close'] - df['ema_21']) / df['ema_21'] * 100).round(2)

    # Calculate pivot price (standard formula: (H + L + C) / 3)
    df['pivot_price'] = ((df['high'] + df['low'] + df['close']) / 3).round(2)

    # DEBUG: Log pivot_price statistics
    pivot_non_null = df['pivot_price'].notna().sum()
    logging.debug(f"[CALC] pivot_price calculated: {pivot_non_null}/{len(df)} non-null values")

    # Use SMA-50 as the MA filter (matching Pine Script "Breakout Trend Follower")
    # Pine Script: maLength = input(defval = 50, title = "MA Period for Filtering")
    df['maFilter'] = df['sma_50']

    # For bars without SMA-50 data, forward-fill from previous bar
    df['maFilter'] = df['maFilter'].ffill()

    # Use SMA-200 for Weinstein Stage Analysis (separate from entry filter)
    df['ma_200'] = df['sma_200']
    df['ma_200'] = df['ma_200'].ffill()

    # === DETECT SWING POINTS ===
    # A swing high at bar i is the highest high in range [i-pvtLenL...i+pvtLenR]
    # A swing low at bar i is the lowest low in range [i-pvtLenL...i+pvtLenR]
    # With shunt=1, swings detected at bar i are only confirmed at bar i+1 (matching Pine Script SHUNT=1)

    # === DETECT SWING POINTS ===
    # Detect raw swings and store at confirmation position (matching daily/monthly loaders)
    # Pine Script Shunt=1 means 1-bar confirmation delay for buyLevel/stopLevel
    # Swings detected at bar i are confirmed at bar i+shunt (matching Pine Script behavior)
    swing_highs = [None] * len(df)
    swing_lows = [None] * len(df)

    for i in range(len(df)):
        # Determine valid range for lookback/lookahead
        start_idx = max(0, i - pvtLenL)
        end_idx = min(len(df) - 1, i + pvtLenR)

        # Swing high: is this bar the highest in the window?
        if i >= pvtLenL and i <= len(df) - pvtLenR - 1:
            # Only valid swings when we have full lookback+lookahead
            high_in_window = df.loc[start_idx:end_idx, 'high'].max()
            if df.loc[i, 'high'] == high_in_window:
                # Store at confirmation position with shunt=1 (Pine Script SHUNT=1)
                confirm_idx = min(i + shunt, len(df) - 1)
                # Store the CURRENT HIGH price (this bar's high, not offset bars back)
                swing_highs[confirm_idx] = df.loc[i, 'high']

        # Swing low: is this bar the lowest in the window?
        if i >= pvtLenL and i <= len(df) - pvtLenR - 1:
            # Only valid swings when we have full lookback+lookahead
            low_in_window = df.loc[start_idx:end_idx, 'low'].min()
            if df.loc[i, 'low'] == low_in_window:
                # Store at confirmation position with shunt=1 (Pine Script SHUNT=1)
                confirm_idx = min(i + shunt, len(df) - 1)
                # Store the CURRENT LOW price (this bar's low, not offset bars back)
                swing_lows[confirm_idx] = df.loc[i, 'low']

    df['swingHigh'] = [v is not None for v in swing_highs]
    df['swingLow'] = [v is not None for v in swing_lows]

    # === CALCULATE MOVING AVERAGE FILTER ===
    # Must come BEFORE swing tracking that references it
    df['ma50'] = df['close'].rolling(window=maLength, min_periods=1).mean()

    # === TRACK MOST RECENT SWING POINTS ===
    # swing_highs[i] and swing_lows[i] now contain the PRICE from valuewhen offset
    # Forward-fill them to get the most recent levels available on each bar
    buy_levels = [None] * len(df)
    stop_levels = [None] * len(df)

    last_buy_level = None
    last_stop_level = None

    for i in range(len(df)):
        # Update when new swing is detected
        if swing_lows[i] is not None:
            last_stop_level = swing_lows[i]

        if swing_highs[i] is not None:
            last_buy_level = swing_highs[i]

        # Forward fill the most recent levels
        if last_stop_level is not None:
            stop_levels[i] = last_stop_level

        if last_buy_level is not None:
            buy_levels[i] = last_buy_level

    df['buyLevel'] = buy_levels
    df['stopLevel'] = stop_levels

    # === GENERATE SIGNALS ===
    # BUY: high >= buyLevel AND close > ma50 (only when buyLevel exists)
    # SELL: close <= stopLevel (only when stopLevel exists) - check close not low to avoid intraday dips
    # State machine: only buy when flat, only sell when in position

    buy_signal = []
    sell_signal = []

    # Debug: track which date we're processing for logging
    debug_target_date = '2025-11-10'
    debug_rows = {}

    for i in range(len(df)):
        # Buy signal: high > buyLevel AND buyLevel > MA50 (strict > on both, filter on level not close)
        # ✅ FIXED: Add NaN checks to prevent comparison errors
        buy_check = (buy_levels[i] is not None and
                     not pd.isna(buy_levels[i]) and
                     not pd.isna(df.loc[i, 'high']) and
                     not pd.isna(df.loc[i, 'ma50']) and
                     df.loc[i, 'high'] > buy_levels[i] and
                     buy_levels[i] > df.loc[i, 'ma50'])

        if buy_check:
            buy_signal.append(True)
        else:
            buy_signal.append(False)

        # Sell signal: low < stopLevel (EXACT Pine Script match)
        # CRITICAL FIX: Pine Script uses "low < stopLevel", NOT "close <= stopLevel"
        sell_check = (stop_levels[i] is not None and
                      not pd.isna(stop_levels[i]) and
                      not pd.isna(df.loc[i, 'low']) and
                      df.loc[i, 'low'] < stop_levels[i])

        if sell_check:
            sell_signal.append(True)
        else:
            sell_signal.append(False)

        # Debug logging for target date
        if str(df.loc[i, 'date'].date()) == debug_target_date:
            debug_rows[i] = {
                'date': df.loc[i, 'date'],
                'high': df.loc[i, 'high'],
                'low': df.loc[i, 'low'],
                'close': df.loc[i, 'close'],
                'ma50': df.loc[i, 'ma50'],
                'buyLevel': buy_levels[i],
                'stopLevel': stop_levels[i],
                'buy_check': buy_check,
                'sell_check': sell_check,
                'buy_signal': buy_signal[-1],
                'sell_signal': sell_signal[-1]
            }

    # === PROPER STATE MACHINE SIGNAL GENERATION (matching Pine Script EXACTLY) ===
    # Pine Script code:
    #   inPosition := buy[1] ? true : sellSignal[1] ? false : inPosition[1]
    #   flat := not inPosition
    #   buyStudy = buy and flat
    #   sellStudy = sellSignal and inPosition
    #
    # Key insight: inPosition is updated FIRST using PREVIOUS bar's conditions [1]
    # Then signals are generated using CURRENT bar's conditions AND the UPDATED inPosition state

    in_pos, sigs, pos = False, [], []
    buy_prev = False   # Track PREVIOUS bar's buy signal (Pine Script: buy[1])
    sell_prev = False  # Track PREVIOUS bar's sell signal (Pine Script: sellSignal[1])

    for i in range(len(df)):
        # Debug: track state machine decisions for target date
        if i in debug_rows:
            debug_rows[i]['in_pos_before'] = in_pos

        # STEP 1: Update position state using PREVIOUS bar's signals
        # Pine Script: inPosition := buy[1] ? true : sellSignal[1] ? false : inPosition[1]
        if i == 0:
            in_pos = False
        else:
            if buy_prev:
                in_pos = True
            elif sell_prev:
                in_pos = False
            # else: in_pos remains unchanged

        # STEP 2: Check CURRENT bar's signals and determine action
        # flat = not inPosition (using CURRENT position state)
        flat = not in_pos

        # buyStudy = buy and flat (current buy condition AND not in position)
        buyStudy = buy_signal[i] and flat

        # sellStudy = sellSignal and inPosition (current sell condition AND in position)
        sellStudy = sell_signal[i] and in_pos

        # STEP 3: Assign signal and update position for NEXT bar
        # Position update for next bar happens here based on current signal
        if buyStudy:
            sigs.append('Buy')
            # Position will be True for next bar (set in buy_prev for next iteration)
        elif sellStudy:
            sigs.append('Sell')
            # Position will be False for next bar (set in sell_prev for next iteration)
        else:
            sigs.append('None')

        if i in debug_rows:
            debug_rows[i]['signal'] = sigs[-1]
            debug_rows[i]['in_pos_after'] = in_pos

        # Record position state (reflects state USED for this bar's decision, before next update)
        pos.append(in_pos)

        # Update previous bar tracking for next iteration
        # These will be used in STEP 1 of the NEXT bar to update in_pos
        buy_prev = buy_signal[i]
        sell_prev = sell_signal[i]

    # DEBUG: Removed excessive debug output that was slowing down the loader
    # This was printing detailed signal analysis for every bar matching target date (2025-11-10)
    # Keeping debug_rows tracking for future investigation if needed

    df['Signal'] = sigs
    df['inPosition'] = pos

    # Calculate signal strength for each row
    strengths = []
    for i in range(len(df)):
        strength = calculate_signal_strength(df, i)
        strengths.append(strength)

    df['strength'] = strengths

    # Set signal_type based on signal
    df['signal_type'] = df['Signal']

    # === CALCULATE MISSING FIELDS (match daily loader) ===
    # initial_stop = stopLevel
    df['initial_stop'] = df['stopLevel']
    # trailing_stop = stopLevel (no trailing for weekly)
    df['trailing_stop'] = df['stopLevel']

    # pivot_price is calculated earlier as technical indicator (H+L+C)/3
    # No need to override it here - use the technical pivot price

    # buy_zone_start and buy_zone_end: Zone around the pivot level for entry
    # buy_zone_start = 2% below buyLevel (pivot high)
    # buy_zone_end = buyLevel (pivot high) - defines entry zone
    df['buy_zone_start'] = df['buyLevel'] * 0.98  # 2% below pivot
    df['buy_zone_end'] = df['buyLevel']  # At pivot high

    # exit_trigger fields: Define profit targets and stop loss conditions
    df['exit_trigger_1_price'] = df['buyLevel'] * 1.20  # 20% profit target
    df['exit_trigger_2_price'] = df['buyLevel'] * 1.25  # 25% profit target
    df['exit_trigger_3_condition'] = '50_SMA_BREACH_WITH_VOLUME'  # Condition type
    df['exit_trigger_3_price'] = df['sma_50']  # Current 50-day SMA level
    df['exit_trigger_4_condition'] = 'STOP_LOSS_HIT'  # Hard stop condition
    df['exit_trigger_4_price'] = df['stopLevel']  # Stop loss price (pivot low)

    # === BASE/CONSOLIDATION ANALYSIS ===
    # base_type: Detect consolidation patterns by looking at price volatility (VECTORIZED)
    # Daily range % = (high - low) / close * 100 (standard formula to avoid infinity on penny stocks)
    df['daily_range_pct'] = ((df['high'] - df['low']) / df['close']) * 100
    df['base_type'] = df['daily_range_pct'].apply(
        lambda x: 'TIGHT_RANGE' if x < 1.0 else ('NORMAL_RANGE' if x < 2.5 else 'WIDE_RANGE')
    )
    logging.info(f"[generate_signals] base_type calculated, non-null count: {df['base_type'].notna().sum()}/{len(df)}")

    # base_length_days: Count consecutive days in consolidation (simplified - count at signal)
    # Calculate for all signals (Buy/Sell), showing consolidation length before signal
    df['base_length_days'] = None
    for i in range(1, len(df)):
        signal = df.iloc[i]['Signal']
        if signal in ['Buy', 'Sell']:
            # Count consecutive consolidation days before this signal (max 20 days)
            length = 0
            for j in range(i - 1, max(-1, i - 21), -1):
                if df.iloc[j]['base_type'] in ['TIGHT_RANGE', 'NORMAL_RANGE']:
                    length += 1
                else:
                    break
            df.at[i, 'base_length_days'] = length if length > 0 else None

    # === CALCULATE REAL METRICS ===
    # Calculate 200-day rolling average volume
    df['avg_volume_50d'] = df['volume'].rolling(window=50).mean().fillna(0).astype('int64')

    # Calculate volume surge percentage: (current_volume / avg_volume_50d - 1) * 100
    # REAL DATA ONLY: Use None if avg_volume is missing, not fake 0
    df['volume_surge_pct'] = df.apply(
        lambda row: round(((row['volume'] / row['avg_volume_50d'] - 1) * 100), 2)
        if row['avg_volume_50d'] > 0 else None,
        axis=1
    )

    # Calculate risk/reward ratio: (target_price - entry_price) / (entry_price - stop_loss)
    # target_price = buyLevel * 1.25 (25% profit target based on entry price)
    # REAL DATA ONLY: Use None if calculation cannot be performed, not fake 0
    df['risk_reward_ratio'] = df.apply(
        lambda row: round(
            (((row['buyLevel'] * 1.25) - row['buyLevel']) / (row['buyLevel'] - row['stopLevel'])),
            2
        ) if (row['stopLevel'] is not None and row['buyLevel'] is not None and row['stopLevel'] > 0 and row['buyLevel'] > 0 and (row['buyLevel'] - row['stopLevel']) != 0) else None,
        axis=1
    )

    # Calculate breakout quality based on price range and volume
    def calc_breakout_quality(row):
        # Validate OHLC invariants
        low = row.get('low')
        high = row.get('high')
        close = row.get('close')
        volume_surge = row.get('volume_surge_pct')

        # REAL DATA ONLY: Return None for missing/invalid data, not fake 'WEAK'
        if low is None or high is None or close is None or volume_surge is None:
            return None  # Insufficient data - no quality assessment possible

        if low <= 0 or high <= 0 or close <= 0:
            return None  # Invalid price data

        if high < low:
            logging.warning(f"Invalid OHLC: high ({high}) < low ({low})")
            return None  # Inverted prices = data error

        if row.get('avg_volume_50d', 0) <= 0:
            return None  # No volume data

        # Calculate daily range percentage
        # Formula: (high - low) / close * 100 (standard formula to avoid infinity on penny stocks)
        daily_range_pct = ((high - low) / close) * 100

        # Validate result is reasonable (not inf or nan)
        # NOTE: Extreme moves >100% occur with penny stocks, stock splits, data errors (acceptable)
        if not (0 <= daily_range_pct) or np.isinf(daily_range_pct) or np.isnan(daily_range_pct):
            return None  # Invalid calculation

        # Cap extreme ranges at 100% for scoring purposes (but allow the data through)
        daily_range_pct_capped = min(daily_range_pct, 100.0)

        # Determine if close is in upper or lower half of daily range (direction matters)
        range_midpoint = (high + low) / 2
        is_upper_half = close > range_midpoint

        # Real calculations - distinguish breakout (upside) vs breakdown (downside)
        # Use capped range for scoring (but extreme moves still score as STRONG)
        if daily_range_pct_capped > 3.0 and volume_surge > 50:
            # Only STRONG quality if move is in expected direction
            # For buy signals: upper half = breakout. For sell signals: lower half = breakdown
            signal = row.get('Signal')
            if signal == 'Buy' and is_upper_half:
                return 'STRONG'  # Strong breakout
            elif signal == 'Sell' and not is_upper_half:
                return 'STRONG'  # Strong breakdown
            else:
                return 'MODERATE'  # High volume/range but wrong direction for signal
        elif daily_range_pct_capped > 1.5 and volume_surge > 25:
            return 'MODERATE'
        else:
            return 'WEAK'  # Only return WEAK if data is valid but metrics don't meet thresholds

    df['breakout_quality'] = df.apply(calc_breakout_quality, axis=1)

    # === RS RATING (Relative Strength - Investor's Business Daily style) ===
    # Simple version: rank based on recent performance
    def calc_rs_rating(df_window):
        """Calculate RS rating 0-99 based on price performance vs 200-day high"""
        if len(df_window) < 200:
            return None

        current_price = df_window.iloc[-1]['close']
        high_200d = df_window.iloc[-200:]['high'].max()

        if high_200d <= 0:
            return None

        # RS = (current / 200-day high) * 100
        rs = (current_price / high_200d) * 100
        # Convert to 0-99 scale
        rs_rating = min(99, max(1, int(rs)))
        return rs_rating

    df['rs_rating'] = None
    for i in range(200, len(df)):
        rs = calc_rs_rating(df.iloc[0:i+1])
        if rs is not None:
            df.at[i, 'rs_rating'] = rs

    # === PROFIT TARGETS (25% profit target is standard) ===
    df['profit_target_8pct'] = df['buyLevel'] * 1.08  # 8% above buy level
    df['profit_target_20pct'] = df['buyLevel'] * 1.20  # 20% above buy level
    df['profit_target_25pct'] = df['buyLevel'] * 1.25  # 25% above buy level (standard)

    # === RISK PERCENT (Risk = entry - stop loss / entry) ===
    df['risk_pct'] = df.apply(
        lambda row: round(((row['buyLevel'] - row['stopLevel']) / row['buyLevel'] * 100), 2)
        if (row['buyLevel'] is not None and row['stopLevel'] is not None and row['buyLevel'] > 0) else None,
        axis=1
    )

    # === ENTRY QUALITY SCORE (Based on breakout quality, volume, and RS) ===
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

    # === MARKET STAGE (Stan Weinstein Stage Analysis using 200-day MA for ETFs) ===
    # Calculate MA slope to determine if it's rising, falling, or flattening
    ma_slope_window = 10  # Look at 10-day slope
    df['ma_200_slope'] = df['ma_200'].diff(periods=ma_slope_window)
    df['ma_200_slope'] = df['ma_200'].diff(periods=ma_slope_window)

    def detect_market_stage(row, index):
        """Classify into Weinstein's 4-Stage model based on price position relative to 200-day MA (for ETFs with limited data)"""
        # For ETFs: use ma_200 instead of ma_200 (93.8% coverage vs 3.8% for ma_200)
        if pd.isna(row.get('close')) or pd.isna(row.get('ma_200')):
            return None

        close = row['close']
        ma_200 = row['ma_200']
        ma_slope = row.get('ma_200_slope')

        # Need sufficient data for MA calculation (14 days minimum for SMA/RSI)
        if index < 200:
            return None

        # Calculate price position relative to MA
        price_diff_pct = ((close - ma_200) / ma_200 * 100) if ma_200 > 0 else None
        if price_diff_pct is None:
            return None

        # Detect MA direction (tuned threshold to 0.15 for better discrimination)
        is_ma_rising = ma_slope > 0.15 if pd.notna(ma_slope) else False
        is_ma_falling = ma_slope < -0.15 if pd.notna(ma_slope) else False
        is_ma_flat = not is_ma_rising and not is_ma_falling

        # === Weinstein Stage Detection ===

        # Stage 4: Declining - Price below declining MA (most bearish)
        if close < ma_200 and is_ma_falling:
            return 'Stage 4 - Declining'

        # Stage 3: Distribution/Topping - Price oscillating near MA
        # Includes: Price near MA, OR price oscillating around MA, OR MA flattening
        if is_ma_flat and -5 <= price_diff_pct <= 8:
            return 'Stage 3 - Topping'
        # Also catch oscillation pattern: price sometimes above, sometimes below MA (transition state)
        elif -8 <= price_diff_pct <= 10 and is_ma_flat:
            return 'Stage 3 - Topping'

        # Stage 2: Advancing - Price above rising MA (most bullish)
        if close > ma_200 and is_ma_rising:
            return 'Stage 2 - Advancing'

        # Stage 1: Basing - Price oscillating around flat/rising MA or below rising MA
        if close < ma_200 and (is_ma_rising or is_ma_flat):
            return 'Stage 1 - Basing'

        # Default fallback: Only if price is well above MA but MA not clearly rising (anomaly)
        if close > ma_200 and not is_ma_rising:
            return 'Stage 2 - Advancing'  # Changed from None - if price > MA, treat as advance

        return None

    df['market_stage'] = [detect_market_stage(row, idx) for idx, row in df.iterrows()]

    # === STAGE NUMBER (Extract numeric stage from market_stage) ===
    df['stage_number'] = df['market_stage'].apply(
        lambda x: int(x.split()[1]) if pd.notna(x) and 'Stage' in str(x) else None
    )

    # === STAGE CONFIDENCE (Based on price distance from MA_200, NOT MA_50) ===
    def calc_stage_confidence(row):
        """Calculate confidence in market stage (0-100) based on distance from 200-day MA"""
        if pd.isna(row.get('market_stage')):
            return None

        close = row['close']
        ma_200 = row['ma_200']  # ✅ FIXED: Use ma_200 (200-day MA) not ma_200!

        if pd.isna(ma_200) or ma_200 is None or ma_200 <= 0:
            return None

        # Distance from 200-day MA as % of price
        distance_pct = abs((close - ma_200) / ma_200 * 100)

        # More distance = more confidence (stage is clearer)
        if distance_pct > 15:
            return 95  # Very clear stage separation
        elif distance_pct > 10:
            return 85
        elif distance_pct > 5:
            return 75  # Moderate clarity
        elif distance_pct > 2:
            return 60  # Weak clarity
        else:
            return 40  # Very close to MA (ambiguous)

    df['stage_confidence'] = df.apply(calc_stage_confidence, axis=1)

    # === SUBSTAGE (Early vs Late in stage) ===
    def detect_substage(row):
        """Detect substage within the 4-stage cycle - Distinguishes breakout vs breakdown"""
        stage = row.get('market_stage')
        if pd.isna(stage):
            return None

        if 'Basing' in str(stage):
            # Check if early or late in basing
            vol_surge = row.get('volume_surge_pct')
            if vol_surge is not None and vol_surge > 30:
                # HIGH VOLUME: Distinguish breakout (upside) vs breakdown (downside)
                signal = row.get('Signal')
                risk_reward = row.get('risk_reward_ratio')

                # Breakout = Buy signal with positive risk/reward
                if signal == 'Buy' and (pd.isna(risk_reward) or risk_reward > 0):
                    return 'Late Basing - Breakout Imminent'
                # Breakdown = Sell signal or negative risk/reward
                elif signal == 'Sell' or (not pd.isna(risk_reward) and risk_reward < 0):
                    return 'Late Basing - Breakdown'
                # Ambiguous = default to Breakout Imminent
                else:
                    return 'Late Basing - Breakout Imminent'
            return 'Early Basing'

        elif 'Advancing' in str(stage):
            # Check trend strength
            rs = row.get('rs_rating')
            if rs is not None and rs > 75:
                return 'Strong Advance'
            return 'Early Advance'

        elif 'Topping' in str(stage):
            return 'Distribution'

        elif 'Declining' in str(stage):
            return 'Breakdown'

        return None

    df['substage'] = df.apply(detect_substage, axis=1)

    # === POSITION SIZING (Shares based on risk) ===
    df['position_size_pct'] = df.apply(
        lambda row: round(
            min(5.0, 0.5 / row['risk_pct'] * 100),  # Risk 0.5% of account per trade
            2
        ) if (row['risk_pct'] is not None and row['risk_pct'] > 0) else None,
        axis=1
    )

    # Initialize position tracking fields as None (not fake 0/50 values)
    df['current_gain_pct'] = None
    df['days_in_position'] = None

    logging.info(f"✅ Generated {len(df[df['Signal']=='Buy'])} Buy signals and {len(df[df['Signal']=='Sell'])} Sell signals")

    return df

###############################################################################
# 5) BACKTEST & METRICS
###############################################################################
def backtest_fixed_capital(df):
    trades = []
    buys   = df.index[df['Signal']=='Buy'].tolist()
    if not buys:
        return trades, [], [], None, None

    df2 = df.iloc[buys[0]:].reset_index(drop=True)
    pos_open = False
    for i in range(len(df2)-1):
        sig, o, d = df2.loc[i,'Signal'], df2.loc[i+1,'open'], df2.loc[i+1,'date']
        if sig=='Buy' and not pos_open:
            pos_open=True; trades.append({'date':d,'action':'Buy','price':o})
        elif sig=='Sell' and pos_open:
            pos_open=False; trades.append({'date':d,'action':'Sell','price':o})

    if pos_open:
        last = df2.iloc[-1]
        trades.append({'date':last['date'],'action':'Sell','price':last['close']})

    rets, durs = [], []
    i = 0
    while i < len(trades)-1:
        if trades[i]['action']=='Buy' and trades[i+1]['action']=='Sell':
            e, x = trades[i]['price'], trades[i+1]['price']
            if e is not None and x is not None and e >= 1.0:
                rets.append((x-e)/e)
                durs.append((trades[i+1]['date']-trades[i]['date']).days)
            i += 2
        else:
            i += 1

    return trades, rets, durs, df['date'].iloc[0], df['date'].iloc[-1]

def compute_metrics_fixed_capital(rets, durs, annual_rfr=0.0):
    n = len(rets)
    if n == 0:
        return {}
    wins   = [r for r in rets if r>0]
    losses = [r for r in rets if r<0]
    avg    = np.mean(rets) if n else 0.0
    std    = np.std(rets, ddof=1) if n>1 else 0.0
    return {
      'num_trades':     n,
      'win_rate':       len(wins)/n,
      'avg_return':     avg,
      'profit_factor':  sum(wins)/abs(sum(losses)) if losses else float('inf'),
      'sharpe_ratio':   ((avg-annual_rfr)/std*np.sqrt(n)) if std>0 else 0.0
    }

def analyze_trade_returns_fixed_capital(rets, durs, tag, annual_rfr=0.0):
    m = compute_metrics_fixed_capital(rets, durs, annual_rfr)
    if not m:
        logging.info(f"{tag}: No trades.")
        return
    logging.info(
      f"{tag} → Trades:{m['num_trades']} "
      f"WinRate:{m['win_rate']:.2%} "
      f"AvgRet:{m['avg_return']*100:.2f}% "
      f"PF:{m['profit_factor']:.2f} "
      f"Sharpe:{m['sharpe_ratio']:.2f}"
    )

###############################################################################






















# 6) PROCESS & MAIN
###############################################################################
def process_symbol(symbol, timeframe):
    logging.debug(f"  [process_symbol] Fetching {symbol} {timeframe}")
    try:
        df = fetch_symbol_from_db(symbol, timeframe)
        logging.info(f"  [process_symbol] Done fetching {symbol} {timeframe}, rows: {len(df)}")
        return generate_signals(df) if not df.empty else df
    except Exception as e:
        logging.error(f"Error in process_symbol for {symbol}: {e}", exc_info=True)
        raise

def main():

    try:
        annual_rfr = get_risk_free_rate_fred(FRED_API_KEY)
        print(f"Annual RFR: {annual_rfr:.2%}")
    except Exception as e:
        logging.warning(f"Failed to get risk-free rate: {e}")
        annual_rfr = 0.0

    symbols = get_symbols_from_db(limit=None, skip_completed=True)  # Process ONLY incomplete symbols
    if not symbols:
        logging.info("✅ No more symbols to process - all ETFs complete!")
        return

    logging.info(f"📊 Found {len(symbols)} incomplete ETF symbols to process")

    # Load country ETF symbols (from etf_symbols where etf='Y' AND country IS NOT NULL)
    # Also filter to skip already-completed
    country_symbols = []
    try:
        conn_temp = get_db_connection()
        cur_temp = conn_temp.cursor()
        cur_temp.execute("SELECT symbol FROM etf_symbols WHERE etf='Y' AND country IS NOT NULL AND symbol NOT IN (SELECT DISTINCT symbol FROM buy_sell_weekly_etf);")
        country_symbols = [r[0] for r in cur_temp.fetchall()]
        cur_temp.close()
        conn_temp.close()
    except:
        logging.warning("Could not load country ETF symbols from etf_symbols")

    conn = get_db_connection()
    cur  = conn.cursor()
    create_buy_sell_table(cur, "buy_sell_weekly_etf")
    conn.commit()

    results = {'Daily':{'rets':[],'durs':[]},
               'Weekly':{'rets':[],'durs':[]},
               'Monthly':{'rets':[],'durs':[]}}

    # Combine regular and country ETF symbols into single list
    all_etf_symbols = symbols + country_symbols
    logging.info(f"🚀 Processing {len(symbols)} incomplete regular ETFs + {len(country_symbols)} incomplete country ETFs = {len(all_etf_symbols)} total ETFs")

    # BLACKLIST: Skip bond ETFs that don't work with breakout strategy
    blacklist = {'SHY', 'IEF', 'TLT', 'SHV', 'BND', 'AGG'}  # Bond ETFs - too stable
    all_etf_symbols = [s for s in all_etf_symbols if s not in blacklist]
    logging.info(f"After filtering blacklist: {len(all_etf_symbols)} ETFs to process")

    for sym in all_etf_symbols:
        logging.info(f"=== {sym} ===")
        # Weekly loader processes only Weekly timeframe
        tf = 'Weekly'
        logging.info(f"  [main] Processing {sym} {tf}")
        df = process_symbol(sym, tf)
        logging.info(f"  [main] Done processing {sym} {tf}")
        if not df.empty:
            try:
                insert_symbol_results(cur, sym, tf, df)
                conn.commit()
            except Exception as e:
                logging.error(f"Transaction error for {sym}: {e}. Rolling back.")
                conn.rollback()
                continue
            _, rets, durs, _, _ = backtest_fixed_capital(df)
            results[tf]['rets'].extend(rets)
            results[tf]['durs'].extend(durs)
            analyze_trade_returns_fixed_capital(
                rets, durs, f"[{tf}] {sym}", annual_rfr
            )

    logging.info("=========================")
    logging.info(" AGGREGATED PERFORMANCE (FIXED $10k PER TRADE) ")
    logging.info("=========================")
    for tf in ['Daily','Weekly','Monthly']:
        analyze_trade_returns_fixed_capital(
            results[tf]['rets'], results[tf]['durs'],
            f"[{tf} (Overall)]", annual_rfr
        )

    logging.info("=== Global (All Timeframes) ===")
    all_rets = [r for tf in results for r in results[tf]['rets']]
    all_durs = [d for tf in results for d in results[tf]['durs']]
    analyze_trade_returns_fixed_capital(all_rets, all_durs, "[Global (All TFs)]", annual_rfr)

    logging.info("Processing complete.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    logging.info("Starting Weekly Signals Loader")
    main()
    logging.info("✅ Weekly Signals Loader completed")
