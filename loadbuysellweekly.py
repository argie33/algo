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

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadbuysellweekly.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

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
    DB_USER     = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
    DB_PORT     = int(os.environ.get("DB_PORT", 5432))
    DB_NAME     = os.environ.get("DB_NAME", "stocks")
else:
    logging.info("Using AWS Secrets Manager for DB configuration")
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
    cur.execute("DROP TABLE IF EXISTS buy_sell_weekly;")
    cur.execute("""
      CREATE TABLE buy_sell_weekly (
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
        buylevel            REAL,
        stoplevel           REAL,
        inposition          BOOLEAN,
        strength            REAL,
        avg_volume_50d      BIGINT,
        volume_surge_pct    FLOAT,
        risk_reward_ratio   FLOAT,
        breakout_quality    VARCHAR(10) DEFAULT 'WEAK',
        UNIQUE(symbol, timeframe, date)
      );
    """)

def insert_symbol_results(cur, symbol, timeframe, df):
    # Calculate metrics
    df['avg_volume_50d'] = df['volume'].rolling(window=50).mean().fillna(0).astype('int64')

    # REAL DATA ONLY: Use None if avg_volume is missing, not fake 0
    df['volume_surge_pct'] = df.apply(
        lambda row: round(((row['volume'] / row['avg_volume_50d'] - 1) * 100), 2)
        if row['avg_volume_50d'] > 0 else None,
        axis=1
    )

    # REAL DATA ONLY: Use None if calculation cannot be performed, not fake 0
    df['risk_reward_ratio'] = df.apply(
        lambda row: round(
            (((row['close'] * 1.25) - row['buyLevel']) / (row['buyLevel'] - row['stopLevel']))
            if (row['stopLevel'] > 0 and row['buyLevel'] > 0 and (row['buyLevel'] - row['stopLevel']) != 0) else None,
            2
        ) if (row['stopLevel'] > 0 and row['buyLevel'] > 0 and (row['buyLevel'] - row['stopLevel']) != 0) else None,
        axis=1
    )

    def calc_breakout_quality(row):
        # REAL DATA ONLY: Return None for invalid data, not fake 'WEAK'
        if row['low'] <= 0 or row['avg_volume_50d'] <= 0 or row['volume_surge_pct'] is None:
            return None  # Insufficient data
        daily_range_pct = ((row['high'] - row['low']) / row['low']) * 100
        volume_surge = row['volume_surge_pct']
        if daily_range_pct > 3.0 and volume_surge > 50:
            return 'STRONG'
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
    df['base_type'] = None  # Requires base pattern analysis
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

    # Entry quality and market analysis - set to None (requires complex calculations)
    df['entry_quality_score'] = None  # Requires multi-factor analysis
    df['market_stage'] = None  # Requires stage detection
    df['stage_number'] = None  # Requires market stage
    df['stage_confidence'] = None  # Requires stage analysis
    df['substage'] = None  # Requires substage detection
    df['sell_level'] = None  # Not applicable for buy signals

    insert_q = """
      INSERT INTO buy_sell_weekly (
        symbol, timeframe, date,
        open, high, low, close, volume,
        signal, buylevel, stoplevel, inposition, strength,
        signal_type, pivot_price, buy_zone_start, buy_zone_end,
        exit_trigger_1_price, exit_trigger_2_price, exit_trigger_3_condition, exit_trigger_3_price,
        exit_trigger_4_condition, exit_trigger_4_price, initial_stop, trailing_stop,
        base_type, base_length_days, avg_volume_50d, volume_surge_pct,
        rs_rating, breakout_quality, risk_reward_ratio, current_gain_pct, days_in_position,
        entry_quality_score, market_stage, stage_number, stage_confidence, substage,
        profit_target_8pct, profit_target_20pct, profit_target_25pct,
        risk_pct, position_size_recommendation, sell_level
      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (symbol, timeframe, date) DO NOTHING;
    """
    # === POSITION SIZE RECOMMENDATION (based on risk) ===
    df['position_size_recommendation'] = df.apply(
        lambda row: round(
            min(5.0, 0.5 / row['risk_pct'] * 100),  # Risk 0.5% of account per trade
            2
        ) if (row['risk_pct'] is not None and row['risk_pct'] > 0) else None,
        axis=1
    )

    inserted = 0
    skipped = 0
    for idx, row in df.iterrows():
        try:
            # Check for NaNs or missing values in core fields
            vals = [row.get('open'), row.get('high'), row.get('low'), row.get('close'), row.get('volume'),
                    row.get('Signal'), row.get('buyLevel'), row.get('stopLevel'), row.get('inPosition'), row.get('strength')]
            if any(pd.isnull(v) for v in vals):
                logging.debug(f"Skipping row {idx} for {symbol} {timeframe} due to NaN: {vals}")
                skipped += 1
                continue

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
            signal_type = row.get('signal_type')
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
            market_stage = row.get('market_stage')
            stage_num = row.get('stage_number')
            stage_conf = row.get('stage_confidence')
            substage = row.get('substage')
            profit_8 = row.get('profit_target_8pct')
            profit_20 = row.get('profit_target_20pct')
            profit_25 = row.get('profit_target_25pct')
            risk_pct = row.get('risk_pct')
            pos_size = row.get('position_size_recommendation')
            sell_level = row.get('sell_level')

            cur.execute(insert_q, (
                symbol,
                timeframe,
                row['date'].date(),
                float(row['open']), float(row['high']), float(row['low']),
                float(row['close']), int(row['volume']),
                row['Signal'], float(row['buyLevel']),
                float(row['stopLevel']), bool(row['inPosition']), float(row['strength']),
                signal_type, pivot_price, buy_zone_start, buy_zone_end,
                exit_1, exit_2, exit_3_cond, exit_3_price,
                exit_4_cond, exit_4_price, initial_stop, trailing_stop,
                base_type, base_length, avg_vol, vol_surge,
                rs_rating, breakout_qual, risk_reward, current_gain, days_held,
                entry_qual, market_stage, stage_num, stage_conf, substage,
                profit_8, profit_20, profit_25,
                risk_pct, pos_size, sell_level
            ))
            inserted += 1
        except Exception as e:
            logging.error(f"Insert failed for {symbol} {timeframe} row {idx}: {e} | row={row}")
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
        if sma_50 is not None:
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
# 5) SIGNAL GENERATION & IN-POSITION LOGIC
###############################################################################
def generate_signals(df, atrMult=1.0, useADX=True, adxS=30, adxW=20):
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

    if useADX:
        flt    = ((df['adx']>adxS) |
                  ((df['adx']>adxW) & (df['adx']>df['adx'].shift(1))))
        adxOK  = (df['plus_di']>df['minus_di']) & flt
        exitD  = ((df['plus_di'].shift(1)>df['minus_di'].shift(1)) &
                  (df['plus_di']<df['minus_di']))
        df['finalBuy']  = ((df['rsiBuy'] & df['TrendOK'] & adxOK) | df['breakoutBuy'])
        df['finalSell'] = (df['rsiSell'] | df['breakoutSell'] | exitD)
    else:
        df['finalBuy']  = ((df['rsiBuy'] & df['TrendOK']) | df['breakoutBuy'])
        df['finalSell'] = (df['rsiSell'] | df['breakoutSell'])

    in_pos, sigs, pos = False, [], []
    for i in range(len(df)):
        if in_pos and df.loc[i,'finalSell']:
            sigs.append('Sell'); in_pos=False
        elif not in_pos and df.loc[i,'finalBuy']:
            sigs.append('Buy'); in_pos=True
        else:
            sigs.append('None')
        pos.append(in_pos)

    df['Signal']    = sigs
    df['inPosition']= pos
    
    # Calculate signal strength for each row
    strengths = []
    for i in range(len(df)):
        strength = calculate_signal_strength(df, i)
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

    conn = get_db_connection()
    cur  = conn.cursor()
    create_buy_sell_table(cur)
    conn.commit()

    results = {'Daily':{'rets':[],'durs':[]},
               'Weekly':{'rets':[],'durs':[]},
               'Monthly':{'rets':[],'durs':[]}}

    for sym in symbols:
        logging.info(f"=== {sym} ===")
        # Weekly loader processes only Weekly timeframe
        tf = 'Weekly'
        logging.info(f"  [main] Processing {sym} {tf}")
        df = process_symbol(sym, tf)
        logging.info(f"  [main] Done processing {sym} {tf}")
        if not df.empty:
            insert_symbol_results(cur, sym, tf, df)
            conn.commit()
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
    main()
