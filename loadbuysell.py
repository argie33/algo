#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import gc
import resource
import math

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import requests
import pandas as pd
import numpy as np

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadbuysell.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# DB config loader (matches loadpricedaily.py pattern)
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

# -------------------------------
# FRED API Key
# -------------------------------
FRED_API_KEY = os.environ["FRED_API_KEY"]

###############################################################################
# 1) DATABASE FUNCTIONS 
###############################################################################
def get_symbols_from_db(limit=None):
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    cur = conn.cursor()
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
    # Disable triggers and drop the old table if it exists
    cur.execute("DROP TABLE IF EXISTS buy_sell CASCADE;")
    cur.connection.commit()  # Commit the drop immediately
    
    # Create new table with minimal structure
    cur.execute("""
      CREATE TABLE buy_sell (
        id           SERIAL PRIMARY KEY,
        symbol       VARCHAR(20)    NOT NULL,
        timeframe    VARCHAR(10)    NOT NULL,
        date         DATE           NOT NULL,
        signal       VARCHAR(10),
        buylevel     REAL,
        stoplevel    REAL,
        inposition   BOOLEAN,
        UNIQUE(symbol, timeframe, date)
      );
    """)

def insert_symbol_results(cur, symbol, timeframe, df):
    insert_q = """
      INSERT INTO buy_sell (
        symbol, timeframe, date,
        signal, buylevel, stoplevel, inposition
      ) VALUES (%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (symbol, timeframe, date) DO NOTHING;
    """
    inserted = 0
    for idx, row in df.iterrows():
        try:
            # Check for NaNs or missing values
            vals = [row.get('Signal'), row.get('buyLevel'), 
                   row.get('stopLevel'), row.get('inPosition')]
            if any(pd.isnull(v) for v in vals):
                logging.warning(f"Skipping row {idx} for {symbol} {timeframe} due to NaN: {vals}")
                continue
            cur.execute(insert_q, (
                symbol,
                timeframe,
                row['date'].date(),
                row['Signal'],
                float(row['buyLevel']),
                float(row['stopLevel']),
                bool(row['inPosition'])
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
    tech_table = tech_table_map[tf]
    
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Updated SQL to work with actual database schema (no plus_di/minus_di)
        sql = f"""
          SELECT
            p.date, p.open, p.high, p.low, p.close, p.volume,
            t.rsi, t.atr, t.adx,
            t.sma_50    AS "TrendMA",
            t.pivot_high AS "PivotHighRaw",
            t.pivot_low  AS "PivotLowRaw"
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
                'rsi','atr','adx',
                'TrendMA','PivotHighRaw','PivotLowRaw']
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.reset_index(drop=True)

###############################################################################
# 4) SIGNAL GENERATION & IN-POSITION LOGIC (Simplified without ADX DI)
###############################################################################
def generate_signals(df, atrMult=1.0, useADX=True, adxThreshold=25):
    if df.empty:
        return df
    
    # Basic trend and RSI signals
    df['TrendOK'] = df['close'] > df['TrendMA']
    df['RSI_prev'] = df['rsi'].shift(1)
    df['rsiBuy'] = (df['rsi'] > 50) & (df['RSI_prev'] <= 50)
    df['rsiSell'] = (df['rsi'] < 50) & (df['RSI_prev'] >= 50)
    
    # Pivot levels
    df['LastPH'] = df['PivotHighRaw'].shift(1).ffill()
    df['LastPL'] = df['PivotLowRaw'].shift(1).ffill()
    
    # Stop and buy levels
    df['stopBuffer'] = df['atr'] * atrMult
    df['stopLevel'] = df['LastPL'] - df['stopBuffer']
    df['buyLevel'] = df['LastPH']
    
    # Breakout signals
    df['breakoutBuy'] = df['high'] > df['buyLevel']
    df['breakoutSell'] = df['low'] < df['stopLevel']
    
    # Simplified ADX logic (without plus_di/minus_di)
    if useADX:
        df['adxStrong'] = df['adx'] > adxThreshold
        df['finalBuy'] = ((df['rsiBuy'] & df['TrendOK'] & df['adxStrong']) | df['breakoutBuy'])
        df['finalSell'] = (df['rsiSell'] | df['breakoutSell'])
    else:
        df['finalBuy'] = ((df['rsiBuy'] & df['TrendOK']) | df['breakoutBuy'])
        df['finalSell'] = (df['rsiSell'] | df['breakoutSell'])

    # Generate position tracking
    in_pos, sigs, pos = False, [], []
    for i in range(len(df)):
        if in_pos and df.loc[i, 'finalSell']:
            sigs.append('Sell')
            in_pos = False
        elif not in_pos and df.loc[i, 'finalBuy']:
            sigs.append('Buy')
            in_pos = True
        else:
            sigs.append('None')
        pos.append(in_pos)

    df['Signal'] = sigs
    df['inPosition'] = pos
    return df

###############################################################################
# 5) BACKTEST & METRICS
###############################################################################
def backtest_fixed_capital(df):
    if df.empty:
        return [], [], [], None, None
        
    trades = []
    buys = df.index[df['Signal'] == 'Buy'].tolist()
    if not buys:
        return trades, [], [], None, None

    df2 = df.iloc[buys[0]:].reset_index(drop=True)
    pos_open = False
    
    for i in range(len(df2) - 1):
        sig, o, d = df2.loc[i, 'Signal'], df2.loc[i + 1, 'open'], df2.loc[i + 1, 'date']
        if sig == 'Buy' and not pos_open:
            pos_open = True
            trades.append({'date': d, 'action': 'Buy', 'price': o})
        elif sig == 'Sell' and pos_open:
            pos_open = False
            trades.append({'date': d, 'action': 'Sell', 'price': o})

    if pos_open:
        last = df2.iloc[-1]
        trades.append({'date': last['date'], 'action': 'Sell', 'price': last['close']})

    rets, durs = [], []
    i = 0
    while i < len(trades) - 1:
        if trades[i]['action'] == 'Buy' and trades[i + 1]['action'] == 'Sell':
            e, x = trades[i]['price'], trades[i + 1]['price']
            if e >= 1.0:
                rets.append((x - e) / e)
                durs.append((trades[i + 1]['date'] - trades[i]['date']).days)
            i += 2
        else:
            i += 1

    return trades, rets, durs, df['date'].iloc[0], df['date'].iloc[-1]

def compute_metrics_fixed_capital(rets, durs, annual_rfr=0.0):
    n = len(rets)
    if n == 0:
        return {}
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    avg = np.mean(rets) if n else 0.0
    std = np.std(rets, ddof=1) if n > 1 else 0.0
    return {
        'num_trades': n,
        'win_rate': len(wins) / n,
        'avg_return': avg,
        'profit_factor': sum(wins) / abs(sum(losses)) if losses else float('inf'),
        'sharpe_ratio': ((avg - annual_rfr) / std * np.sqrt(n)) if std > 0 else 0.0
    }

def analyze_trade_returns_fixed_capital(rets, durs, tag, annual_rfr=0.0):
    m = compute_metrics_fixed_capital(rets, durs, annual_rfr)
    if not m:
        logging.info(f"{tag}: No trades.")
        return
    logging.info(
        f"{tag} → Trades:{m['num_trades']} "
        f"WinRate:{m['win_rate']:.2%} "
        f"AvgRet:{m['avg_return'] * 100:.2f}% "
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
    log_mem("startup")

    try:
        annual_rfr = get_risk_free_rate_fred(FRED_API_KEY)
        logging.info(f"Annual RFR: {annual_rfr:.2%}")
    except Exception as e:
        logging.warning(f"Failed to get risk-free rate: {e}")
        annual_rfr = 0.0

    symbols = get_symbols_from_db(limit=3)  # Limit for debugging, remove or increase as needed
    if not symbols:
        logging.info("No symbols in DB.")
        return

    # Connect to DB using proven pattern
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor()

    create_buy_sell_table(cur)
    conn.commit()

    results = {'Daily': {'rets': [], 'durs': []},
               'Weekly': {'rets': [], 'durs': []},
               'Monthly': {'rets': [], 'durs': []}}

    for sym in symbols:
        logging.info(f"=== {sym} ===")
        for tf in ['Daily', 'Weekly', 'Monthly']:
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
    for tf in ['Daily', 'Weekly', 'Monthly']:
        analyze_trade_returns_fixed_capital(
            results[tf]['rets'], results[tf]['durs'],
            f"[{tf} (Overall)]", annual_rfr
        )

    logging.info("=== Global (All Timeframes) ===")
    all_rets = [r for tf in results for r in results[tf]['rets']]
    all_durs = [d for tf in results for d in results[tf]['durs']]
    analyze_trade_returns_fixed_capital(all_rets, all_durs, "[Global (All TFs)]", annual_rfr)

    # Record last run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info("Processing complete.")
    
    cur.close()
    conn.close()
    log_mem("shutdown")

if __name__ == "__main__":
    main()
