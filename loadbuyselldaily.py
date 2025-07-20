#!/usr/bin/env python3 
# Buy/Sell daily signals - Trading signals data population v1 - Data loading phase
import os
import sys
import json
import time
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
SECRET_ARN   = os.environ["DB_SECRET_ARN"]

sm_client   = boto3.client("secretsmanager")
secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
creds       = json.loads(secret_resp["SecretString"])

DB_USER     = creds["username"]
DB_PASSWORD = creds["password"]
DB_HOST     = creds["host"]
DB_PORT     = int(creds.get("port", 5432))
DB_NAME     = creds["dbname"]

def get_db_connection():
    # Clean SSL strategy using working configuration
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"🔌 Connection attempt {attempt}/{max_retries} to {DB_HOST}:{DB_PORT}")
            
            ssl_config = {
                'host': DB_HOST,
                'port': DB_PORT,
                'user': DB_USER,
                'password': DB_PASSWORD,
                'dbname': DB_NAME,
                'sslmode': 'require',
                'connect_timeout': 30,
                'application_name': 'buy-sell-daily-loader',
                'options': '-c statement_timeout=30000'
            }
            
            logging.info("🔐 Using SSL with require mode")
            conn = psycopg2.connect(**ssl_config)
            logging.info("✅ Database connection established successfully")
            break
            
        except psycopg2.OperationalError as e:
            error_msg = str(e)
            logging.error(f"❌ PostgreSQL connection error (attempt {attempt}/{max_retries}): {error_msg}")
            
            if attempt < max_retries:
                logging.info(f"⏳ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                logging.error(f"❌ All {max_retries} connection attempts failed")
                raise
    
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

def insert_symbol_results(cur, symbol, timeframe, df):
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
      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
    for idx, row in df.iterrows():
        try:
            # Check for NaNs or missing values in core fields
            vals = [row.get('open'), row.get('high'), row.get('low'), row.get('close'), row.get('volume'),
                    row.get('Signal'), row.get('buyLevel'), row.get('stopLevel'), row.get('inPosition'), row.get('strength')]
            if any(pd.isnull(v) for v in vals[:10]):  # Only check core fields
                logging.warning(f"Skipping row {idx} for {symbol} {timeframe} due to NaN: {vals}")
                continue
            cur.execute(insert_q, (
                symbol, timeframe, row['date'].date(),
                float(row['open']), float(row['high']), float(row['low']),
                float(row['close']), int(row['volume']),
                row['Signal'], float(row['buyLevel']),
                float(row['stopLevel']), bool(row['inPosition']), float(row['strength']),
                # O'Neill methodology fields
                row.get('signal_type'), row.get('pivot_price'), row.get('buy_zone_start'), row.get('buy_zone_end'),
                row.get('exit_trigger_1_price'), row.get('exit_trigger_2_price'), row.get('exit_trigger_3_condition'), row.get('exit_trigger_3_price'),
                row.get('exit_trigger_4_condition'), row.get('exit_trigger_4_price'), row.get('initial_stop'), row.get('trailing_stop'),
                row.get('base_type'), row.get('base_length_days'), row.get('avg_volume_50d'), row.get('volume_surge_pct'),
                row.get('rs_rating'), row.get('breakout_quality'), row.get('risk_reward_ratio'), row.get('current_gain_pct'), row.get('days_in_position')
            ))
            inserted += 1
        except Exception as e:
            logging.error(f"Insert failed for {symbol} {timeframe} row {idx}: {e} | row={row}")
    logging.info(f"Inserted {inserted} rows for {symbol} {timeframe}")

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
    """Calculate signal strength score (0-100) for a given row"""
    try:
        row = df.iloc[index]
        signal_type = row.get('Signal', 'None')
        
        if signal_type == 'None':
            return 50.0
        
        # Get required values
        rsi = row.get('rsi', 50)
        adx = row.get('adx', 25)
        close = row.get('close', 0)
        high = row.get('high', close)
        low = row.get('low', close)
        volume = row.get('volume', 0)
        sma_50 = row.get('sma_50', close)
        atr = row.get('atr', 0)
        pivot_high = row.get('pivot_high', 0)
        pivot_low = row.get('pivot_low', 0)
        
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
        
        # ADX trend strength
        if adx > 40:
            strength += 9   # Very strong trend
        elif adx > 30:
            strength += 6   # Strong trend
        elif adx > 20:
            strength += 3   # Moderate trend
        else:
            strength += 1   # Weak trend
        
        # Price vs SMA-50
        if signal_type == 'Buy' and close > sma_50:
            price_above_sma = ((close - sma_50) / sma_50) * 100
            strength += min(9, max(0, price_above_sma * 3))
        elif signal_type == 'Sell' and close < sma_50:
            price_below_sma = ((sma_50 - close) / sma_50) * 100
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
        
        # 3. Price Action (25%)
        if high != low:
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
        else:
            strength += 12.5  # Default if no price action
        
        # 4. Volatility Context (10%)
        if close > 0 and atr > 0:
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
        
        # 5. Breakout Magnitude (10%)
        if signal_type == 'Buy' and pivot_high > 0:
            breakout_percent = ((close - pivot_high) / pivot_high) * 100
            if breakout_percent > 3.0:
                strength += 10  # Strong breakout
            elif breakout_percent > 1.5:
                strength += 7   # Good breakout
            elif breakout_percent > 0.5:
                strength += 5   # Moderate breakout
            else:
                strength += 2   # Weak breakout
        elif signal_type == 'Sell' and pivot_low > 0:
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
        return 50.0

def calculate_signal_strength_enhanced(df, index):
    """Enhanced signal strength calculation with O'Neill factors"""
    try:
        row = df.iloc[index]
        signal_type = row.get('Signal', 'None')
        
        if signal_type == 'None':
            return 50.0
        
        strength = 0.0
        
        # 1. Volume Surge (30%) - Critical for O'Neill
        volume_surge = row.get('volume_surge_pct', 0)
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
        return 50.0

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
    """Rate breakout quality A+ to C based on O'Neill criteria"""
    score = 0
    
    # Volume (0-30 points)
    if volume_surge >= 100:
        score += 30
    elif volume_surge >= 50:
        score += 20
    elif volume_surge >= 40:
        score += 10
    
    # RS Rating (0-30 points)
    rs_rating = row.get('rs_rating', 50)
    if rs_rating >= 90:
        score += 30
    elif rs_rating >= 80:
        score += 20
    elif rs_rating >= 70:
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
    """Generate signals with O'Neill methodology including volume-confirmed exits"""
    
    # Calculate additional indicators needed for O'Neill method
    df['sma_50'] = df['close'].rolling(window=50).mean()
    df['avg_volume_50d'] = df['volume'].rolling(window=50).mean()
    
    # Original signal logic
    df['TrendOK']     = df['close'] > df['sma_50']
    df['RSI_prev']    = df['rsi'].shift(1)
    df['rsiBuy']      = (df['rsi']>50)&(df['RSI_prev']<=50)
    df['rsiSell']     = (df['rsi']<50)&(df['RSI_prev']>=50)
    df['LastPH']      = df['pivot_high'].shift(1).ffill()
    df['LastPL']      = df['pivot_low'].shift(1).ffill()
    df['stopBuffer']  = df['atr'] * atrMult
    df['stopLevel']   = df['LastPL'] - df['stopBuffer']
    df['buyLevel']    = df['LastPH']
    df['breakoutBuy'] = df['high'] > df['buyLevel']
    df['breakoutSell']= df['low']  < df['stopLevel']

    # Initialize O'Neill methodology columns
    df['signal_type'] = 'None'
    df['pivot_price'] = np.nan
    df['buy_zone_start'] = np.nan
    df['buy_zone_end'] = np.nan
    df['exit_trigger_1_price'] = np.nan  # 20% profit
    df['exit_trigger_2_price'] = np.nan  # 25% profit
    df['exit_trigger_3_condition'] = None  # 50_SMA_BREACH_WITH_VOLUME
    df['exit_trigger_3_price'] = np.nan  # 50-day SMA level
    df['exit_trigger_4_condition'] = None  # STOP_LOSS_HIT
    df['exit_trigger_4_price'] = np.nan  # Stop loss price
    df['base_type'] = None
    df['base_length_days'] = 0
    df['volume_surge_pct'] = 0
    df['rs_rating'] = 50  # Default RS rating
    df['breakout_quality'] = None
    df['risk_reward_ratio'] = 0
    df['current_gain_pct'] = 0
    df['days_in_position'] = 0
    
    # Enhanced signal generation with O'Neill methodology
    in_pos = False
    sigs = []
    pos = []
    entry_price = None
    entry_date = None
    entry_idx = None
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        # Calculate volume surge percentage
        if pd.notna(row['avg_volume_50d']) and row['avg_volume_50d'] > 0:
            volume_surge = ((row['volume'] / row['avg_volume_50d']) - 1) * 100
            df.loc[i, 'volume_surge_pct'] = volume_surge
        else:
            volume_surge = 0
        
        # Check for base pattern
        base_type, base_length = identify_base_pattern(df, i)
        if base_type:
            df.loc[i, 'base_type'] = base_type
            df.loc[i, 'base_length_days'] = base_length
            
            # Calculate pivot price and buy zone
            pivot = calculate_pivot_price(df, i, base_type)
            df.loc[i, 'pivot_price'] = pivot
            df.loc[i, 'buy_zone_start'] = pivot
            df.loc[i, 'buy_zone_end'] = pivot * 1.05  # 5% buy zone
        
        # BUY SIGNAL LOGIC
        if not in_pos:
            buy_signal = False
            signal_type = 'None'
            
            # O'Neill breakout with volume (primary signal)
            if (row['breakoutBuy'] and volume_surge >= 40 and 
                pd.notna(df.loc[i, 'pivot_price']) and 
                row['close'] <= df.loc[i, 'buy_zone_end']):
                buy_signal = True
                signal_type = 'Breakout'
                entry_price = row['close']
                entry_date = row['date']
                entry_idx = i
                
                # Set exit triggers
                df.loc[i, 'exit_trigger_1_price'] = entry_price * 1.20  # 20% target
                df.loc[i, 'exit_trigger_2_price'] = entry_price * 1.25  # 25% target
                df.loc[i, 'exit_trigger_3_condition'] = '50_SMA_BREACH_WITH_VOLUME'
                df.loc[i, 'exit_trigger_3_price'] = row['sma_50']
                df.loc[i, 'exit_trigger_4_condition'] = 'STOP_LOSS_HIT'
                df.loc[i, 'exit_trigger_4_price'] = entry_price * 0.925  # 7.5% stop
                
                # Rate breakout quality
                base_info = {'pattern_type': base_type or 'Unknown'}
                df.loc[i, 'breakout_quality'] = rate_breakout_quality(row, base_info, volume_surge)
                
                # Calculate risk/reward
                risk = (entry_price - df.loc[i, 'exit_trigger_4_price']) / entry_price
                reward = 0.20  # Target 20% gain
                df.loc[i, 'risk_reward_ratio'] = reward / risk if risk > 0 else 0
                
            # RSI momentum buy (secondary signal)
            elif row['rsiBuy'] and row['TrendOK'] and volume_surge >= 25:
                buy_signal = True
                signal_type = 'Momentum'
                entry_price = row['close']
                entry_date = row['date']
                entry_idx = i
                
                # Set exit triggers
                df.loc[i, 'exit_trigger_1_price'] = entry_price * 1.20
                df.loc[i, 'exit_trigger_2_price'] = entry_price * 1.25
                df.loc[i, 'exit_trigger_3_condition'] = '50_SMA_BREACH_WITH_VOLUME'
                df.loc[i, 'exit_trigger_3_price'] = row['sma_50']
                df.loc[i, 'exit_trigger_4_condition'] = 'STOP_LOSS_HIT'
                df.loc[i, 'exit_trigger_4_price'] = entry_price * 0.925
                
            if buy_signal:
                sigs.append('Buy')
                in_pos = True
                df.loc[i, 'signal_type'] = signal_type
            else:
                sigs.append('None')
        
        # SELL SIGNAL LOGIC
        else:  # in position
            sell_signal = False
            sell_reason = 'None'
            
            # Calculate current gain and update position tracking
            if entry_price:
                current_gain = ((row['close'] - entry_price) / entry_price) * 100
                df.loc[i, 'current_gain_pct'] = current_gain
                
                # Days in position
                if entry_date:
                    days_held = (row['date'] - entry_date).days
                    df.loc[i, 'days_in_position'] = days_held
            
            # EXIT TRIGGER 4: Stop loss (7.5%) - Highest Priority
            if entry_price and row['close'] <= entry_price * 0.925:
                sell_signal = True
                sell_reason = 'Stop Loss (7.5%)'
                df.loc[i, 'signal_type'] = 'STOP_LOSS_HIT'
            
            # EXIT TRIGGER 3: 50-day SMA breach with volume confirmation
            elif (row['close'] < row['sma_50'] and volume_surge >= 40):
                sell_signal = True
                sell_reason = '50-day SMA Breach (Volume Confirmed)'
                df.loc[i, 'signal_type'] = '50_SMA_BREACH_WITH_VOLUME'
            
            # EXIT TRIGGER 1 & 2: Profit targets (discretionary)
            elif current_gain >= 25:
                # Could sell at 25% but keep as discretionary
                df.loc[i, 'signal_type'] = 'TARGET_2_REACHED'
            elif current_gain >= 20:
                # Could sell at 20% but keep as discretionary
                df.loc[i, 'signal_type'] = 'TARGET_1_REACHED'
            
            # Original sell signals as backup
            elif row['rsiSell'] or row['breakoutSell']:
                sell_signal = True
                sell_reason = 'Technical Sell'
                df.loc[i, 'signal_type'] = 'Technical'
            
            if sell_signal:
                sigs.append('Sell')
                in_pos = False
                entry_price = None
                entry_date = None
                entry_idx = None
            else:
                sigs.append('None')
        
        pos.append(in_pos)
    
    df['Signal'] = sigs
    df['inPosition'] = pos
    
    # Calculate enhanced signal strength
    strengths = []
    for i in range(len(df)):
        strength = calculate_signal_strength_enhanced(df, i)
        strengths.append(strength)
    
    df['strength'] = strengths
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


    symbols = get_symbols_from_db(limit=3)  # Limit for debugging, remove or increase as needed
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
        insert_symbol_results(cur, sym, tf, df)
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
