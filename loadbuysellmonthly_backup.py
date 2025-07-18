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
SCRIPT_NAME = "loadbuysellmonthly.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

###############################################################################
# ─── Environment & Secrets ───────────────────────────────────────────────────
###############################################################################

# FRED_API_KEY: log a warning and continue with 0 risk-free rate if missing
FRED_API_KEY = os.environ.get('FRED_API_KEY')
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
    # Set statement timeout to 30 seconds (30000 ms)
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        options='-c statement_timeout=30000'
    ,
            sslmode='disable'
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
    cur.execute("DROP TABLE IF EXISTS buy_sell_monthly;")
    cur.execute("""
      CREATE TABLE buy_sell_monthly (
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
        UNIQUE(symbol, timeframe, date)
      );
    """)

def insert_symbol_results(cur, symbol, timeframe, df):
    insert_q = """
      INSERT INTO buy_sell_monthly (
        symbol, timeframe, date,
        open, high, low, close, volume,
        signal, buylevel, stoplevel, inposition, strength
      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (symbol, timeframe, date) DO NOTHING;
    """
    inserted = 0
    for idx, row in df.iterrows():
        try:
            # Check for NaNs or missing values
            vals = [row.get('open'), row.get('high'), row.get('low'), row.get('close'), row.get('volume'),
                    row.get('Signal'), row.get('buyLevel'), row.get('stopLevel'), row.get('inPosition'), row.get('strength')]
            if any(pd.isnull(v) for v in vals):
                logging.warning(f"Skipping row {idx} for {symbol} {timeframe} due to NaN: {vals}")
                continue
            cur.execute(insert_q, (
                symbol,
                timeframe,
                row['date'].date(),
                float(row['open']), float(row['high']), float(row['low']),
                float(row['close']), int(row['volume']),
                row['Signal'], float(row['buyLevel']),
                float(row['stopLevel']), bool(row['inPosition']), float(row['strength'])
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
# 6) BACKTEST & METRICS
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
# 7) PROCESS & MAIN
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
        for tf in ['Daily','Weekly','Monthly']:
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
