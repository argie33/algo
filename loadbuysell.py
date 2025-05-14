#!/usr/bin/env python3
import os
import sys
import json
import requests
import pandas as pd
import numpy as np
import mysql.connector
import boto3
from datetime import datetime

###############################################################################
# ─── Environment & Secrets ─────────────────────────────────────────────────── 
###############################################################################
# FRED API key remains an env-var
FRED_API_KEY   = os.environ["FRED_API_KEY"]

# Pull all DB creds from one Secret ARN
SECRET_ARN     = os.environ["DB_SECRET_ARN"]
sm_client      = boto3.client("secretsmanager")
secret_resp    = sm_client.get_secret_value(SecretId=SECRET_ARN)
creds          = json.loads(secret_resp["SecretString"])

DB_USER        = creds["username"]
DB_PASSWORD    = creds["password"]
DB_HOST        = creds["host"]
DB_NAME        = creds["dbname"]

DB_CONFIG = {
    'user':     DB_USER,
    'password': DB_PASSWORD,
    'host':     DB_HOST,
    'database': DB_NAME,
}

###############################################################################
# 1) DATABASE FUNCTIONS
###############################################################################
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def get_symbols_from_db(limit=None):
    cnx    = get_db_connection()
    cursor = cnx.cursor()
    try:
        q = """
          SELECT symbol
            FROM stock_symbols
           WHERE exchange IN ('NASDAQ','New York Stock Exchange')
        """
        if limit:
            q += " LIMIT %s"
            cursor.execute(q, (limit,))
        else:
            cursor.execute(q)
        return [r[0] for r in cursor.fetchall()]
    finally:
        cursor.close()
        cnx.close()

def create_buy_sell_table(cursor):
    cursor.execute("DROP TABLE IF EXISTS buy_sell;")
    cursor.execute("""
      CREATE TABLE buy_sell (
        id INT AUTO_INCREMENT PRIMARY KEY,
        symbol      VARCHAR(20),
        timeframe   VARCHAR(10),
        date        DATE,
        open        FLOAT,
        high        FLOAT,
        low         FLOAT,
        close       FLOAT,
        volume      BIGINT,
        `signal`    VARCHAR(10),
        buyLevel    FLOAT,
        stopLevel   FLOAT,
        inPosition  BOOLEAN,
        UNIQUE KEY unique_buy_sell (symbol, timeframe, date)
      );
    """)

def insert_symbol_results(cursor, symbol, timeframe, df):
    insert_q = """
      INSERT IGNORE INTO buy_sell (
        symbol, timeframe, date,
        open, high, low, close, volume,
        `signal`, buyLevel, stopLevel, inPosition
      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
    """
    for _, row in df.iterrows():
        cursor.execute(insert_q, (
            symbol, timeframe, row['date'].strftime('%Y-%m-%d'),
            row['open'], row['high'], row['low'], row['close'], row['volume'],
            row['Signal'], row['buyLevel'], row['stopLevel'], row['inPosition']
        ))

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
    obs = [o for o in r.json().get("observations",[]) if o["value"]!="."]
    return float(obs[-1]["value"])/100.0 if obs else 0.0

###############################################################################
# 3) FETCH FROM DB (prices + technicals)
###############################################################################
def fetch_symbol_from_db(symbol, timeframe):
    tf = timeframe.lower()
    price_table = f"price_data_{tf}"
    tech_table  = f"technical_data_{tf}"
    cnx    = get_db_connection()
    cursor = cnx.cursor(dictionary=True)
    sql = f"""
      SELECT
        p.date, p.open, p.high, p.low, p.close, p.volume,
        t.rsi, t.atr, t.adx, t.plus_di, t.minus_di,
        t.sma_50 AS TrendMA,
        t.pivot_high AS PivotHighRaw,
        t.pivot_low  AS PivotLowRaw
      FROM {price_table} p
      JOIN {tech_table} t
        ON p.symbol=t.symbol AND p.date=t.date
      WHERE p.symbol=%s
      ORDER BY p.date ASC;
    """
    cursor.execute(sql, (symbol,))
    rows = cursor.fetchall()
    cursor.close()
    cnx.close()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    for c in ['open','high','low','close','volume',
              'rsi','atr','adx','plus_di','minus_di',
              'TrendMA','PivotHighRaw','PivotLowRaw']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.reset_index(drop=True)

###############################################################################
# 4) SIGNAL GENERATION & IN-POSITION LOGIC
###############################################################################
def generate_signals(df, atrMult=1.0, useADX=True,
                     adxS=30, adxW=20):
    # Trend filter
    df['TrendOK']    = df['close'] > df['TrendMA']
    # RSI cross
    df['RSI_prev']   = df['rsi'].shift(1)
    df['rsiBuy']     = (df['rsi']>50)&(df['RSI_prev']<=50)
    df['rsiSell']    = (df['rsi']<50)&(df['RSI_prev']>=50)
    # Pivot breakout
    df['PivotHighC'] = df['PivotHighRaw'].shift(1)
    df['PivotLowC']  = df['PivotLowRaw'].shift(1)
    df['LastPH']     = df['PivotHighC'].ffill()
    df['LastPL']     = df['PivotLowC'].ffill()
    df['stopBuffer'] = df['atr'] * atrMult
    df['stopLevel']  = df['LastPL'] - df['stopBuffer']
    df['buyLevel']   = df['LastPH']
    df['breakoutBuy']= df['high'] > df['buyLevel']
    df['breakoutSell']=df['low']  < df['stopLevel']
    # ADX/DMI filter
    if useADX:
        flt    = ((df['adx']>adxS)|
                  ((df['adx']>adxW)&(df['adx']>df['adx'].shift(1))))
        adxOK  = (df['plus_di']>df['minus_di']) & flt
        exitD  = ((df['plus_di'].shift(1)>df['minus_di'].shift(1)) &
                  (df['plus_di']<df['minus_di']))
        df['finalBuy']  = ((df['rsiBuy'] & df['TrendOK'] & adxOK) | df['breakoutBuy'])
        df['finalSell'] = (df['rsiSell'] | df['breakoutSell'] | exitD)
    else:
        df['finalBuy']  = ((df['rsiBuy'] & df['TrendOK']) | df['breakoutBuy'])
        df['finalSell'] = (df['rsiSell'] | df['breakoutSell'])
    df['buySignal']  = df['finalBuy']
    df['sellSignal'] = df['finalSell']
    in_pos, sigs, pos = False, [], []
    for i in range(len(df)):
        if in_pos and df.loc[i,'sellSignal']:
            sigs.append('Sell'); in_pos=False
        elif not in_pos and df.loc[i,'buySignal']:
            sigs.append('Buy');  in_pos=True
        else:
            sigs.append('None')
        pos.append(in_pos)
    df['Signal']     = sigs
    df['inPosition'] = pos
    return df

###############################################################################
# 5) BACKTEST & METRICS
###############################################################################
def backtest_fixed_capital(df):
    trades = []; buys=df.index[df['Signal']=='Buy'].tolist()
    if not buys:
        return trades,[],[],None,None
    df2 = df.iloc[buys[0]:].reset_index(drop=True)
    pos_open = False
    for i in range(len(df2)-1):
        sig,o,d = df2.loc[i,'Signal'], df2.loc[i+1,'open'], df2.loc[i+1,'date']
        if sig=='Buy' and not pos_open:
            pos_open=True; trades.append({'date':d,'action':'Buy','price':o})
        elif sig=='Sell' and pos_open:
            pos_open=False; trades.append({'date':d,'action':'Sell','price':o})
    if pos_open:
        last = df2.iloc[-1]
        trades.append({'date':last['date'],'action':'Sell','price':last['close']})
    rets, durs, i = [], [], 0
    while i < len(trades)-1:
        if trades[i]['action']=='Buy' and trades[i+1]['action']=='Sell':
            e,x = trades[i]['price'], trades[i+1]['price']
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
    win_rate = len(wins)/n
    avg_ret   = np.mean(rets)
    pf        = sum(wins)/abs(sum(losses)) if abs(sum(losses))>1e-12 else np.inf
    std       = np.std(rets, ddof=1) if n>1 else 0.0
    sharpe    = ((avg_ret-annual_rfr)/std*np.sqrt(n)) if std>1e-12 and n>1 else 0.0
    return {
      'num_trades': n,
      'win_rate':   win_rate,
      'avg_return': avg_ret,
      'profit_factor': pf,
      'sharpe_ratio':  sharpe
    }

def analyze_trade_returns_fixed_capital(rets, durs, tag, annual_rfr=0.0):
    m = compute_metrics_fixed_capital(rets, durs, annual_rfr)
    if not m:
        print(f"{tag}: No trades.")
        return
    print(
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
    df = fetch_symbol_from_db(symbol, timeframe)
    return generate_signals(df) if not df.empty else df

def main():
    try:
        annual_rfr = get_risk_free_rate_fred(FRED_API_KEY)
        print(f"Annual RFR: {annual_rfr:.2%}")
    except:
        annual_rfr = 0.0

    symbols = get_symbols_from_db()
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
        print(f"\n=== {sym} ===")
        for tf in ['Daily','Weekly','Monthly']:
            df = process_symbol(sym, tf)
            if df.empty:
                print(f"[{tf}] no data")
                continue
            insert_symbol_results(cur, sym, tf, df)
            conn.commit()
            _, rets, durs, _, _ = backtest_fixed_capital(df)
            results[tf]['rets'].extend(rets)
            results[tf]['durs'].extend(durs)
            analyze_trade_returns_fixed_capital(
                rets, durs, f"[{tf}] {sym}", annual_rfr
            )

    print("\n=========================")
    print(" AGGREGATED PERFORMANCE (FIXED $10k PER TRADE) ")
    print("=========================")
    for tf in ['Daily','Weekly','Monthly']:
        analyze_trade_returns_fixed_capital(
            results[tf]['rets'], results[tf]['durs'],
            f"[{tf} (Overall)]", annual_rfr
        )

    print("\n=== Global (All Timeframes) ===")
    all_rets = [r for tf in results for r in results[tf]['rets']]
    all_durs = [d for tf in results for d in results[tf]['durs']]
    analyze_trade_returns_fixed_capital(all_rets, all_durs, "[Global (All TFs)]", annual_rfr)

    print("Processing complete.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
