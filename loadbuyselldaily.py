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
from importlib import import_module

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadbuyselldaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

###############################################################################
# ─── Environment & Secrets ───────────────────────────────────────────────────
###############################################################################
FRED_API_KEY = os.environ.get('FRED_API_KEY', '')
if not FRED_API_KEY:
    logging.warning('FRED_API_KEY environment variable is not set. Risk-free rate will be set to 0.')

# Try local environment first, then AWS
if os.environ.get("DB_HOST"):
    DB_HOST     = os.environ.get("DB_HOST", "localhost")
    DB_USER     = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
    DB_PORT     = int(os.environ.get("DB_PORT", 5432))
    DB_NAME     = os.environ.get("DB_NAME", "stocks")
    logging.info("Using local environment DB configuration")
else:
    try:
        SECRET_ARN   = os.environ["DB_SECRET_ARN"]
        sm_client   = boto3.client("secretsmanager")
        secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
        creds       = json.loads(secret_resp["SecretString"])

        DB_USER     = creds["username"]
        DB_PASSWORD = creds["password"]
        DB_HOST     = creds["host"]
        DB_PORT     = int(creds.get("port", 5432))
        DB_NAME     = creds["dbname"]
        logging.info("Using AWS Secrets Manager DB configuration")
    except KeyError:
        logging.error("DB_HOST or DB_SECRET_ARN not set. Please set local DB environment variables or AWS_SECRET_ARN")
        raise

def get_db_connection():
    # Set statement timeout to 30 seconds (30000 ms)
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        options='-c statement_timeout=30000'
    )
    return conn

###############################################################################
# 1) DATABASE FUNCTIONS
###############################################################################
def get_symbols_from_db(limit=None):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        q = """
          SELECT symbol
            FROM stock_symbols
           WHERE exchange IN ('NASDAQ','New York Stock Exchange')
        """
        if limit:
            q += " LIMIT %s"
            cur.execute(q, (limit,))
        else:
            cur.execute(q)
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

def create_buy_sell_table(cur):
    cur.execute("DROP TABLE IF EXISTS buy_sell_daily;")
    cur.execute("""
      CREATE TABLE buy_sell_daily (
        id           SERIAL PRIMARY KEY,
        symbol       VARCHAR(20)    NOT NULL,
        timeframe    VARCHAR(10)    NOT NULL,
        date         DATE           NOT NULL,
        open         REAL,
        high         REAL,
        low          REAL,
        close        REAL,
        volume       BIGINT,
        signal       VARCHAR(10),
        buylevel     REAL,
        stoplevel    REAL,
        inposition   BOOLEAN,
        strength     REAL,
        -- O'Neill methodology columns
        signal_type  VARCHAR(50),
        pivot_price  REAL,
        buy_zone_start REAL,
        buy_zone_end REAL,
        exit_trigger_1_price REAL,     -- 20% profit target
        exit_trigger_2_price REAL,     -- 25% profit target
        exit_trigger_3_condition VARCHAR(50), -- '50_SMA_BREACH_WITH_VOLUME'
        exit_trigger_3_price REAL,     -- Current 50-day SMA level
        exit_trigger_4_condition VARCHAR(50), -- 'STOP_LOSS_HIT'
        exit_trigger_4_price REAL,     -- Stop loss price
        initial_stop REAL,
        trailing_stop REAL,
        base_type    VARCHAR(50),
        base_length_days INTEGER,
        avg_volume_50d BIGINT,
        volume_surge_pct REAL,
        rs_rating    INTEGER,
        breakout_quality VARCHAR(20),
        risk_reward_ratio REAL,
        current_gain_pct REAL,
        days_in_position INTEGER,
        UNIQUE(symbol, timeframe, date)
      );
    """)

def insert_symbol_results(cur, symbol, timeframe, df, conn):
    insert_q = """
      INSERT INTO buy_sell_daily (
        symbol, timeframe, date,
        open, high, low, close, volume,
        signal, buylevel, stoplevel, inposition, strength,
        signal_type, pivot_price, buy_zone_start, buy_zone_end,
        exit_trigger_1_price, exit_trigger_2_price, exit_trigger_3_condition, exit_trigger_3_price,
        exit_trigger_4_condition, exit_trigger_4_price, initial_stop, trailing_stop,
        base_type, base_length_days, avg_volume_50d, volume_surge_pct,
        rs_rating, breakout_quality, risk_reward_ratio, current_gain_pct, days_in_position
      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (symbol, timeframe, date) DO UPDATE SET
        open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
        close = EXCLUDED.close, volume = EXCLUDED.volume,
        signal = EXCLUDED.signal, buylevel = EXCLUDED.buylevel,
        stoplevel = EXCLUDED.stoplevel, inposition = EXCLUDED.inposition,
        strength = EXCLUDED.strength, signal_type = EXCLUDED.signal_type,
        pivot_price = EXCLUDED.pivot_price, buy_zone_start = EXCLUDED.buy_zone_start,
        buy_zone_end = EXCLUDED.buy_zone_end, exit_trigger_1_price = EXCLUDED.exit_trigger_1_price,
        exit_trigger_2_price = EXCLUDED.exit_trigger_2_price, exit_trigger_3_condition = EXCLUDED.exit_trigger_3_condition,
        exit_trigger_3_price = EXCLUDED.exit_trigger_3_price, exit_trigger_4_condition = EXCLUDED.exit_trigger_4_condition,
        exit_trigger_4_price = EXCLUDED.exit_trigger_4_price, initial_stop = EXCLUDED.initial_stop,
        trailing_stop = EXCLUDED.trailing_stop, base_type = EXCLUDED.base_type,
        base_length_days = EXCLUDED.base_length_days, avg_volume_50d = EXCLUDED.avg_volume_50d,
        volume_surge_pct = EXCLUDED.volume_surge_pct, rs_rating = EXCLUDED.rs_rating,
        breakout_quality = EXCLUDED.breakout_quality, risk_reward_ratio = EXCLUDED.risk_reward_ratio,
        current_gain_pct = EXCLUDED.current_gain_pct, days_in_position = EXCLUDED.days_in_position;
    """
    inserted = 0
    skipped = 0
    for idx, row in df.iterrows():
        try:
            # Validate and convert core fields before insertion (REAL DATA ONLY - no fake defaults)
            try:
                date_val = row['date'].date() if hasattr(row['date'], 'date') else row['date']
                # REAL DATA ONLY - if price is missing, return None (not fake 0.0)
                open_val = float(row.get('open')) if row.get('open') is not None else None
                high_val = float(row.get('high')) if row.get('high') is not None else None
                low_val = float(row.get('low')) if row.get('low') is not None else None
                close_val = float(row.get('close')) if row.get('close') is not None else None

                # Validate volume - REAL DATA ONLY (not fake 0)
                vol = row.get('volume')
                if pd.isna(vol) or vol is None:
                    vol = None
                elif isinstance(vol, (float, np.floating)):
                    vol = int(vol) if not np.isnan(vol) else None
                else:
                    vol = int(vol)

                # Ensure volume fits in BIGINT range (up to 2^63-1)
                if vol < 0 or vol > 9223372036854775807:
                    logging.warning(f"Skipping row {idx}: invalid volume {vol}")
                    skipped += 1
                    continue

                signal_val = row.get('Signal', 'None') or 'None'
                signal_triggered_val = row.get('signal_triggered', 'None') or 'None'
                buyLevel_val = float(row.get('buyLevel')) if pd.notna(row.get('buyLevel')) else None
                stopLevel_val = float(row.get('stopLevel')) if pd.notna(row.get('stopLevel')) else None
                inPos_val = bool(row.get('inPosition', False))
                strength_val = float(row.get('strength')) if pd.notna(row.get('strength')) else None

            except (ValueError, OverflowError) as ve:
                logging.warning(f"Skipping row {idx}: type conversion error: {ve}")
                skipped += 1
                continue

            # Check for NaNs or missing values in core fields
            if any(pd.isna(v) for v in [open_val, high_val, low_val, close_val, signal_val]):
                logging.debug(f"Skipping row {idx}: has NaN in core fields")
                skipped += 1
                continue

            # Get optional fields with defaults
            signal_type = row.get('signal_type') or None
            pivot_price = float(row.get('pivot_price')) if pd.notna(row.get('pivot_price')) else None
            buy_zone_start = float(row.get('buy_zone_start')) if pd.notna(row.get('buy_zone_start')) else None
            buy_zone_end = float(row.get('buy_zone_end')) if pd.notna(row.get('buy_zone_end')) else None

            exit_1_price = float(row.get('exit_trigger_1_price')) if pd.notna(row.get('exit_trigger_1_price')) else None
            exit_2_price = float(row.get('exit_trigger_2_price')) if pd.notna(row.get('exit_trigger_2_price')) else None
            exit_3_cond = row.get('exit_trigger_3_condition') or None
            exit_3_price = float(row.get('exit_trigger_3_price')) if pd.notna(row.get('exit_trigger_3_price')) else None
            exit_4_cond = row.get('exit_trigger_4_condition') or None
            exit_4_price = float(row.get('exit_trigger_4_price')) if pd.notna(row.get('exit_trigger_4_price')) else None

            initial_stop = float(row.get('initial_stop')) if pd.notna(row.get('initial_stop')) else None
            trailing_stop = float(row.get('trailing_stop')) if pd.notna(row.get('trailing_stop')) else None

            base_type = row.get('base_type') or None
            base_length_raw = row.get('base_length_days')
            base_length = int(base_length_raw) if base_length_raw is not None else None  # None if missing (not fake 0)

            avg_vol = row.get('avg_volume_50d')
            if pd.isna(avg_vol) or avg_vol is None:
                avg_vol = None  # None if missing (not fake 0)
            else:
                avg_vol = int(avg_vol) if not isinstance(avg_vol, float) else int(float(avg_vol))

            if avg_vol is not None and (avg_vol < 0 or avg_vol > 9223372036854775807):
                avg_vol = None  # REAL DATA ONLY: None instead of fake 0

            vol_surge = float(row.get('volume_surge_pct')) if pd.notna(row.get('volume_surge_pct')) else None
            rs_rating = int(row.get('rs_rating')) if pd.notna(row.get('rs_rating')) else None
            breakout_qual = row.get('breakout_quality') or None
            risk_reward = float(row.get('risk_reward_ratio')) if pd.notna(row.get('risk_reward_ratio')) else None
            current_gain = float(row.get('current_gain_pct')) if pd.notna(row.get('current_gain_pct')) else None
            days_held = int(row.get('days_in_position')) if pd.notna(row.get('days_in_position')) else None

            cur.execute(insert_q, (
                symbol, timeframe, date_val,
                open_val, high_val, low_val, close_val, vol,
                signal_val, buyLevel_val, stopLevel_val, inPos_val, strength_val,
                signal_type, pivot_price, buy_zone_start, buy_zone_end,
                exit_1_price, exit_2_price, exit_3_cond, exit_3_price,
                exit_4_cond, exit_4_price, initial_stop, trailing_stop,
                base_type, base_length, avg_vol, vol_surge,
                rs_rating, breakout_qual, risk_reward, current_gain, days_held
            ))
            inserted += 1

        except psycopg2.IntegrityError as ie:
            conn.rollback()
            logging.warning(f"Integrity error for {symbol} {timeframe} row {idx}: {ie}")
            skipped += 1
            continue
        except Exception as e:
            conn.rollback()
            logging.error(f"Insert failed for {symbol} {timeframe} row {idx}: {e}")
            skipped += 1
            continue

    try:
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to commit for {symbol} {timeframe}: {e}")
        conn.rollback()

    logging.info(f"Inserted {inserted} rows, skipped {skipped} rows for {symbol} {timeframe}")

###############################################################################
# 2) RISK-FREE RATE (FRED)
###############################################################################
def get_risk_free_rate_fred(api_key):
    """Get risk-free rate from FRED. Returns None if data unavailable (REAL DATA ONLY - no fake 0)."""
    if not api_key:
        return None  # No API key - can't get real data, so return None
    url = (
      "https://api.stlouisfed.org/fred/series/observations"
      f"?series_id=DGS3MO&api_key={api_key}&file_type=json"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
        return float(obs[-1]["value"]) / 100.0 if obs else None  # None if no data (not fake 0.0)
    except Exception as e:
        logging.warning(f"Failed to get FRED data: {e}")
        return None  # Error - return None (REAL DATA ONLY)

###############################################################################
# 3) FETCH FROM DB (prices + technicals)
###############################################################################
def fetch_symbol_from_db(symbol, timeframe):
    tf = timeframe.lower()
    # Table name mapping for consistency with loader scripts
    price_table_map = {
        "daily": "price_daily",
        "weekly": "price_weekly",
        "monthly": "price_monthly"
    }
    tech_table_map = {
        "daily": "technical_data_daily",
        "weekly": "technical_data_weekly",
        "monthly": "technical_data_monthly"
    }
    if tf not in price_table_map or tf not in tech_table_map:
        raise ValueError(f"Invalid timeframe: {timeframe}")
    price_table = price_table_map[tf]
    tech_table  = tech_table_map[tf]
    conn = get_db_connection()
    cur  = conn.cursor(cursor_factory=RealDictCursor)
    try:
        sql = f"""
          SELECT
            p.date, p.open, p.high, p.low, p.close, p.volume,
            t.rsi, t.atr, t.adx, t.plus_di, t.minus_di,
            t.sma_50,
            t.pivot_high,
            t.pivot_low
          FROM {price_table} p
          JOIN {tech_table}  t
            ON p.symbol = t.symbol AND p.date = t.date
          WHERE p.symbol = %s
          ORDER BY p.date ASC;
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

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    num_cols = ['open','high','low','close','volume',
                'rsi','atr','adx','plus_di','minus_di',
                'sma_50','pivot_high','pivot_low']
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.reset_index(drop=True)

###############################################################################
# 4) SIGNAL STRENGTH CALCULATION
###############################################################################
def calculate_signal_strength(df, index):
    """Calculate signal strength score (0-100) for a given row. Returns None if no real signal."""
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
        if rsi is None or close is None or volume is None:
            return None

        # Optional technical indicators (use None if missing, not fake defaults)
        adx = row.get('adx')
        high = row.get('high')
        low = row.get('low')
        sma_50 = row.get('sma_50')
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
        if sma_50 is not None and sma_50 > 0:
            if signal_type == 'Buy' and close > sma_50:
                price_above_sma = ((close - sma_50) / sma_50) * 100
                # Validate result is not inf/nan
                if np.isfinite(price_above_sma):
                    strength += min(9, max(0, price_above_sma * 3))
            elif signal_type == 'Sell' and close < sma_50:
                price_below_sma = ((sma_50 - close) / sma_50) * 100
                # Validate result is not inf/nan
                if np.isfinite(price_below_sma):
                    strength += min(9, max(0, price_below_sma * 3))
        
        # 2. Volume Confirmation (25%)
        if avg_volume > 0 and volume is not None and volume >= 0:
            volume_ratio = volume / avg_volume

            # Validate ratio is not inf/nan and reasonable
            if not np.isfinite(volume_ratio) or volume_ratio < 0:
                strength += 5  # Invalid volume data, minimal score
            elif volume_ratio > 5.0:
                # Cap extreme volume spikes (stock split, exchange halt, data error)
                strength += 25  # Treat 5x+ same as 2x+ to prevent skew
            elif volume_ratio > 2.0:
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
            # REAL DATA ONLY: If critical volume data missing, can't calculate meaningful strength
            if avg_volume <= 0 or volume is None:
                return None  # Insufficient volume data for real strength calculation
        
        # 3. Price Action (25%) - only if high/low data available
        if high is not None and low is not None and high > 0 and low > 0 and high >= low:
            # Validate OHLC range
            if high == low:
                # No range, can't calculate close position
                strength += 5
            else:
                close_position = (close - low) / (high - low)

                # Validate result is not inf/nan and within 0-1 range
                if not (0 <= close_position <= 1) or not np.isfinite(close_position):
                    strength += 5  # Invalid calculation
                else:
                    # Use the valid close_position
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

            # Validate result is not inf/nan
            if np.isfinite(atr_percentage):
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
                return None  # Invalid ATR calculation - can't calculate meaningful strength
        else:
            return None  # REAL DATA ONLY: ATR data missing - can't calculate meaningful strength
        
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
        else:
            strength += 5  # Default if no breakout data
        
        return min(100.0, max(0.0, strength))

    except Exception as e:
        logging.warning(f"Error calculating signal strength at index {index}: {e}")
        return None  # Error - return None instead of fake 50.0

def calculate_signal_strength_enhanced(df, index):
    """Enhanced signal strength calculation with O'Neill factors. Returns None if no real signal."""
    try:
        row = df.iloc[index]
        signal_type = row.get('Signal', 'None')

        if signal_type == 'None':
            return None  # No real signal - return None instead of fake 50.0

        # REAL DATA ONLY: Must have volume surge data (not fake default)
        volume_surge = row.get('volume_surge_pct')
        if volume_surge is None:
            return None  # Can't calculate meaningful strength without real volume data

        strength = 0.0

        # 1. Volume Surge (30%) - Critical for O'Neill
        if volume_surge >= 100:
            strength += 30
        elif volume_surge >= 50:
            strength += 25
        elif volume_surge >= 40:
            strength += 20
        elif volume_surge >= 25:
            strength += 15
        else:
            strength += 5
        
        # 2. Base Pattern Quality (25%)
        base_type = row.get('base_type', None)
        if base_type in ['Cup', 'Cup with Handle']:
            strength += 25
        elif base_type == 'Flat Base':
            strength += 20
        elif base_type == 'Double Bottom':
            strength += 15
        elif base_type:
            strength += 10
        else:
            strength += 5
        
        # 3. Price Action in Range (20%)
        if row['high'] != row['low']:
            close_position = (row['close'] - row['low']) / (row['high'] - row['low'])
            if signal_type == 'Buy' and close_position > 0.75:
                strength += 20
            elif signal_type == 'Buy' and close_position > 0.5:
                strength += 15
            elif signal_type == 'Sell' and close_position < 0.25:
                strength += 20
            elif signal_type == 'Sell' and close_position < 0.5:
                strength += 15
            else:
                strength += 10
        
        # 4. Trend Alignment (15%)
        if signal_type == 'Buy':
            if (pd.notna(row.get('sma_50')) and row['close'] > row['sma_50']):
                strength += 15
            else:
                strength += 5
        
        # 5. Buy Zone Position (10%) - O'Neill specific
        if signal_type == 'Buy':
            buy_zone_start = row.get('buy_zone_start')
            buy_zone_end = row.get('buy_zone_end')
            if (pd.notna(buy_zone_start) and pd.notna(buy_zone_end) and 
                buy_zone_start <= row['close'] <= buy_zone_end):
                strength += 10
            else:
                strength += 3
        
        return min(100, max(0, strength))

    except Exception as e:
        logging.error(f"Error calculating enhanced signal strength: {e}")
        return None  # Error - return None instead of fake 50.0

###############################################################################
# 5) SIGNAL GENERATION & IN-POSITION LOGIC
###############################################################################
def calculate_ema(prices, period):
    """Calculate Exponential Moving Average"""
    return prices.ewm(span=period, adjust=False).mean()

def identify_base_pattern(df, current_idx, lookback_days=65):
    """Identify O'Neill base patterns: Cup, Flat Base, Double Bottom"""
    if current_idx < lookback_days:
        return None, 0
    
    window = df.iloc[current_idx - lookback_days:current_idx + 1]
    high_price = window['high'].max()
    low_price = window['low'].min()
    depth_pct = ((high_price - low_price) / high_price) * 100
    
    # Simple pattern detection
    if 12 <= depth_pct <= 33:
        # Check for cup shape
        mid_point = len(window) // 2
        left_low = window.iloc[:mid_point]['low'].min()
        right_low = window.iloc[mid_point:]['low'].min()
        
        if abs(left_low - right_low) / low_price < 0.05:  # Within 5% of each other
            return 'Cup', lookback_days
    
    if depth_pct <= 15 and lookback_days >= 25:
        return 'Flat Base', lookback_days
    
    # Check for double bottom
    lows = window[window['low'] == low_price].index
    if len(lows) >= 2 and (lows[-1] - lows[0]) >= 10:
        return 'Double Bottom', lookback_days
    
    return None, 0

def calculate_pivot_price(df, current_idx, base_type):
    """Calculate pivot point based on base pattern type"""
    if base_type == 'Cup' or base_type == 'Cup with Handle':
        lookback = min(65, current_idx)
        base_high = df.iloc[current_idx - lookback:current_idx + 1]['high'].max()
        return base_high + 0.10
    elif base_type == 'Flat Base':
        lookback = min(25, current_idx)
        base_high = df.iloc[current_idx - lookback:current_idx + 1]['high'].max()
        return base_high * 1.01
    elif base_type == 'Double Bottom':
        lookback = min(50, current_idx)
        window = df.iloc[current_idx - lookback:current_idx + 1]
        return window['high'].median()
    else:
        lookback = min(20, current_idx)
        return df.iloc[current_idx - lookback:current_idx + 1]['high'].max()

def rate_breakout_quality(row, base_info, volume_surge):
    """Rate breakout quality A+ to C based on O'Neill criteria. Returns None if critical data missing."""
    # REAL DATA ONLY: Must have volume surge to calculate quality
    if volume_surge is None:
        return None  # Can't calculate quality without real volume data

    score = 0

    # Volume (0-30 points)
    if volume_surge >= 100:
        score += 30
    elif volume_surge >= 50:
        score += 20
    elif volume_surge >= 40:
        score += 10

    # RS Rating (0-30 points) - REAL DATA ONLY, no fake defaults
    rs_rating = row.get('rs_rating')  # Returns None if not available (no fake 50)
    if rs_rating is not None and rs_rating >= 90:
        score += 30
    elif rs_rating is not None and rs_rating >= 80:
        score += 20
    elif rs_rating is not None and rs_rating >= 70:
        score += 10
    
    # Base Quality (0-20 points)
    if base_info.get('pattern_type') in ['Cup', 'Cup with Handle']:
        score += 20
    elif base_info.get('pattern_type') == 'Flat Base':
        score += 15
    elif base_info.get('pattern_type') == 'Double Bottom':
        score += 10
    
    # Price action (0-20 points)
    price_range = row['high'] - row['low']
    if price_range > 0:
        close_position = (row['close'] - row['low']) / price_range
        if close_position >= 0.75:
            score += 20
        elif close_position >= 0.5:
            score += 10
    
    # Convert to letter grade
    if score >= 90:
        return 'A+'
    elif score >= 80:
        return 'A'
    elif score >= 70:
        return 'B+'
    elif score >= 60:
        return 'B'
    else:
        return 'C'

def generate_signals(df, atrMult=1.0, useADX=True, adxS=30, adxW=20):
    """
    Generate signals matching Pine Script: 'Breakout Trend Follower'

    Simple direct translation:
    - Buy: high > buyLevel (previous swing high breakout)
    - Sell: low < stopLevel (previous swing low - buffer)
    - Filter: Optional 50-day SMA filter (buyLevel > maFilter)

    Parameters from Pine Script:
    - pvtLenL = 3, pvtLenR = 3 (pivot lookback: 3 bars left, 3 bars right)
    - Shunt = 1 (Wait for pivot to be confirmed AFTER 3 bars)
    - atrMult default = 1.0 (multiplier for ATR buffer below swing low)

    KEY FIX: Pine Script's valuewhen(pvthi_, high[pvtLenR], 0) requires that
    the pivot is CONFIRMED (Shunt=1 means offset by 1+pvtLenR bars).
    This matches the way Pine Script plots: offset = -(pvtLenR + Shunt)
    """

    logging.info("🎯 Generating signals using Pine Script 'Breakout Trend Follower' logic with proper pivot confirmation")

    # === Calculate filter MA (50-day SMA) ===
    maLength = 50
    df['maFilter'] = df['close'].rolling(window=maLength).mean()

    # === Pivot High/Low Calculation with Proper Confirmation ===
    pvtLenL = 3  # Bars to the left
    pvtLenR = 3  # Bars to the right (confirmation window)
    Shunt = 1    # Wait for close confirmation

    # The pivot high/low needs to be confirmed after pvtLenR bars
    # offset = -(pvtLenR + Shunt) = -4
    # This means we use the pivot from 4 bars ago (or more recent non-None pivot)
    offset = pvtLenR + Shunt

    df['LastPH'] = df['pivot_high'].shift(offset).ffill()  # Confirmed swing high
    df['LastPL'] = df['pivot_low'].shift(offset).ffill()   # Confirmed swing low

    # === Stop Loss & Buy Level (Pine Script logic) ===
    df['stopBuffer'] = df['atr'] * atrMult if 'atr' in df.columns else 0.0
    df['stopLevel'] = df['LastPL'] - df['stopBuffer']  # Stop level = swing low - buffer
    df['buyLevel'] = df['LastPH']  # Buy level = swing high

    # === Buy/Sell Signals (Pure Pine Script Logic) ===
    # Track TWO separate signals:
    # 1. buySignal_triggered = high > buyLevel (intrabar touch - potential entry)
    # 2. buySignal_confirmed = close > buyLevel (close confirmation - TradingView displays this)
    df['buySignal_triggered'] = df['high'] > df['buyLevel']
    df['buySignal_confirmed'] = df['close'] > df['buyLevel']
    df['sellSignal'] = df['low'] < df['stopLevel']

    # === MA Filter (Pine Script: buyLevel > maFilterCheck) ===
    # Only take setups above 50-day SMA for trend filtering
    df['aboveMA'] = df['buyLevel'] > df['maFilter']

    # === Final Signal Generation (Study version from Pine Script) ===
    # Use CONFIRMED signals (close > buyLevel) for actual trading logic
    in_pos = False
    sigs = []
    sigs_triggered = []
    pos = []

    for i in range(len(df)):
        row = df.iloc[i]

        # BUY SIGNAL (Pine Script line: buyStudy = buy and flat)
        # Conditions: buySignal_confirmed AND time in range AND buyLevel > maFilter AND not in position
        if not in_pos and pd.notna(row['buySignal_confirmed']) and row['buySignal_confirmed']:
            # Check MA filter
            if pd.notna(row['aboveMA']) and row['aboveMA']:
                sigs.append('Buy')
                in_pos = True
            else:
                sigs.append('None')

        # SELL SIGNAL (Pine Script line: sellStudy = sellSignal and inPosition)
        # Condition: sellSignal AND in position
        elif in_pos and pd.notna(row['sellSignal']) and row['sellSignal']:
            sigs.append('Sell')
            in_pos = False

        else:
            sigs.append('None')

        # Track triggered signals separately (for analysis)
        if pd.notna(row['buySignal_triggered']) and row['buySignal_triggered']:
            sigs_triggered.append('Triggered')
        elif pd.notna(row['sellSignal']) and row['sellSignal']:
            sigs_triggered.append('Triggered')
        else:
            sigs_triggered.append('None')

        pos.append(in_pos)

    df['Signal'] = sigs
    df['signal_triggered'] = sigs_triggered
    df['inPosition'] = pos

    # === Simplified signal strength (just based on signal type) ===
    df['signal_type'] = df['Signal']
    df['strength'] = df['Signal'].apply(lambda x: 1.0 if x == 'Buy' else (0.5 if x == 'Sell' else 0.0))

    # === Clean up O'Neill columns (keep for compatibility but set to None only - no fake 0) ===
    df['pivot_price'] = np.nan
    df['buy_zone_start'] = np.nan
    df['buy_zone_end'] = np.nan
    df['exit_trigger_1_price'] = np.nan
    df['exit_trigger_2_price'] = np.nan
    df['exit_trigger_3_condition'] = None
    df['exit_trigger_3_price'] = np.nan
    df['exit_trigger_4_condition'] = None
    df['exit_trigger_4_price'] = np.nan
    df['base_type'] = None
    df['base_length_days'] = None  # REAL DATA ONLY: None instead of fake 0

    # === CALCULATE REAL METRICS ===
    # Calculate 50-day rolling average volume
    df['avg_volume_50d'] = df['volume'].rolling(window=50).mean().fillna(0).astype('int64')

    # Calculate volume surge percentage: (current_volume / avg_volume_50d - 1) * 100
    # REAL DATA ONLY: Use None if avg_volume is missing, not fake 0
    df['volume_surge_pct'] = df.apply(
        lambda row: round(((row['volume'] / row['avg_volume_50d'] - 1) * 100), 2)
        if row['avg_volume_50d'] > 0 else None,
        axis=1
    )

    # Calculate risk/reward ratio: (target_price - entry_price) / (entry_price - stop_loss)
    # target_price = close * 1.25 (25% profit target)
    # REAL DATA ONLY: Use None if calculation cannot be performed, not fake 0
    df['risk_reward_ratio'] = df.apply(
        lambda row: round(
            (((row['close'] * 1.25) - row['buyLevel']) / (row['buyLevel'] - row['stopLevel']))
            if (row['stopLevel'] > 0 and row['buyLevel'] > 0 and (row['buyLevel'] - row['stopLevel']) != 0) else None,
            2
        ) if (row['stopLevel'] > 0 and row['buyLevel'] > 0 and (row['buyLevel'] - row['stopLevel']) != 0) else None,
        axis=1
    )

    # Calculate breakout quality based on price range and volume
    def calc_breakout_quality(row):
        # Validate OHLC invariants
        low = row.get('low')
        high = row.get('high')
        volume_surge = row.get('volume_surge_pct')

        # REAL DATA ONLY: Return None for missing/invalid data, not fake 'WEAK'
        if low is None or high is None or volume_surge is None:
            return None  # Insufficient data - no quality assessment possible

        if low <= 0 or high <= 0:
            return None  # Invalid price data

        if high < low:
            logging.warning(f"Invalid OHLC: high ({high}) < low ({low})")
            return None  # Inverted prices = data error

        if row.get('avg_volume_50d', 0) <= 0:
            return None  # No volume data

        # Calculate daily range percentage
        daily_range_pct = ((high - low) / low) * 100

        # Validate result is reasonable (not inf or nan)
        if not (0 <= daily_range_pct <= 100):
            logging.warning(f"Invalid daily_range_pct: {daily_range_pct}")
            return None  # Invalid calculation

        # Real calculations - only return actual quality assessments
        if daily_range_pct > 3.0 and volume_surge > 50:
            return 'STRONG'
        elif daily_range_pct > 1.5 and volume_surge > 25:
            return 'MODERATE'
        else:
            return 'WEAK'  # Only return WEAK if data is valid but metrics don't meet thresholds

    df['breakout_quality'] = df.apply(calc_breakout_quality, axis=1)

    # Initialize position tracking fields as None (not fake 0/50 values)
    df['rs_rating'] = None
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
            if e >= 1.0:
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
    logging.info(f"  [process_symbol] Fetching {symbol} {timeframe}")
    df = fetch_symbol_from_db(symbol, timeframe)
    logging.info(f"  [process_symbol] Done fetching {symbol} {timeframe}, rows: {len(df)}")
    return generate_signals(df) if not df.empty else df

def main():

    try:
        annual_rfr = get_risk_free_rate_fred(FRED_API_KEY)
        print(f"Annual RFR: {annual_rfr:.2%}")
    except Exception as e:
        logging.warning(f"Failed to get risk-free rate: {e}")
        annual_rfr = 0.0


    symbols = get_symbols_from_db(limit=None)  # Load ALL stocks
    if not symbols:
        print("No symbols in DB.")
        return

    # Daily
    conn = get_db_connection()
    cur  = conn.cursor()
    create_buy_sell_table(cur)
    conn.commit()
    results = {'Daily':{'rets':[],'durs':[]}}
    for sym in symbols:
        logging.info(f"=== {sym} ===")
        tf = 'Daily'
        logging.info(f"  [main] Processing {sym} {tf}")
        df = process_symbol(sym, tf)
        logging.info(f"  [main] Done processing {sym} {tf}")
        if df.empty:
            logging.info(f"[{tf}] no data")
            continue
        insert_symbol_results(cur, sym, tf, df, conn)
        conn.commit()
        _, rets, durs, _, _ = backtest_fixed_capital(df)
        results[tf]['rets'].extend(rets)
        results[tf]['durs'].extend(durs)
        analyze_trade_returns_fixed_capital(
            rets, durs, f"[{tf}] {sym}", annual_rfr
        )
    cur.close()
    conn.close()

    # Weekly
    try:
        weekly_mod = import_module('loadbuysellweekly')
        weekly_mod.main()
    except Exception as e:
        logging.error(f"Weekly loader failed: {e}")

    # Monthly
    try:
        monthly_mod = import_module('loadbuysellmonthly')
        monthly_mod.main()
    except Exception as e:
        logging.error(f"Monthly loader failed: {e}")

    logging.info("=========================")
    logging.info(" AGGREGATED PERFORMANCE (FIXED $10k PER TRADE) ")
    logging.info("=========================")
    for tf in results:
        analyze_trade_returns_fixed_capital(
            results[tf]['rets'], results[tf]['durs'],
            f"[{tf} (Overall)]", annual_rfr
        )

    logging.info("Processing complete.")

if __name__ == "__main__":
    main()
