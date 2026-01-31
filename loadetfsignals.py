#!/usr/bin/env python3
"""
Fast ETF signal generator - only processes the 20 ETFs we have
"""
import sys
import logging
import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime
import pandas as pd
import numpy as np
import boto3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_config():
    """Get database configuration from AWS Secrets Manager or environment variables.

    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager").get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logging.info("Using AWS Secrets Manager for database config")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")

    # Fall back to environment variables
    logging.info("Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

def generate_etf_signals(symbol, prices_df, timeframe, cur, conn):
    """Generate buy/sell signals for an ETF"""
    if prices_df.empty:
        return []
    
    prices_df = prices_df.sort_values('date')
    prices_df = prices_df[prices_df['open'].notna()]
    
    if len(prices_df) < 50:
        return []
    
    signals = []
    for idx in range(50, len(prices_df)):
        row = prices_df.iloc[idx]
        prev_close = prices_df.iloc[idx-1]['close']
        high_52w = prices_df.iloc[max(0, idx-52):idx]['high'].max()
        
        signal = None
        if row['close'] > high_52w * 0.98 and row['close'] > prev_close:
            signal = 'BUY'
        elif row['close'] < prev_close * 0.95:
            signal = 'SELL'
        
        if signal:
            signals.append({
                'symbol': symbol,
                'date': row['date'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'],
                'signal': signal,
                'signal_triggered_date': row['date'],
                'buylevel': row['close'],
                'stoplevel': row['close'] * 0.95,
                'strength': 0.5,
                'signal_type': 'breakout',
                'market_stage': 1,
                'stage_number': 1,
                'entry_quality_score': 0.5
            })
    
    return signals

def load_etf_signals():
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols ORDER BY symbol")
    etfs = [r['symbol'] for r in cur.fetchall()]
    
    logging.info(f"Processing {len(etfs)} ETFs")
    
    for timeframe, table_name, price_table in [
        ('daily', 'buy_sell_daily_etf', 'etf_price_daily'),
        ('weekly', 'buy_sell_weekly_etf', 'etf_price_weekly'),
        ('monthly', 'buy_sell_monthly_etf', 'etf_price_monthly')
    ]:
        logging.info(f"=== {timeframe.upper()} ===")
        cur.execute(f"DELETE FROM {table_name}")
        conn.commit()
        
        total_signals = 0
        for symbol in etfs:
            # Fetch price data
            cur.execute(f"SELECT date, open, high, low, close, volume FROM {price_table} WHERE symbol=%s ORDER BY date", (symbol,))
            rows = cur.fetchall()
            
            if not rows:
                logging.info(f"{symbol} {timeframe}: No price data")
                continue
            
            df = pd.DataFrame(rows)
            df['date'] = pd.to_datetime(df['date'])
            
            # Generate signals
            signals = generate_etf_signals(symbol, df, timeframe, cur, conn)
            
            if signals:
                signal_rows = [
                    (s['symbol'], timeframe, s['date'], float(s['open']), float(s['high']), float(s['low']), float(s['close']), int(s['volume']),
                     s['signal'], s['signal_triggered_date'], float(s['buylevel']), float(s['stoplevel']),
                     float(s['strength']), s['signal_type'], int(s['market_stage']), int(s['stage_number']), float(s['entry_quality_score']))
                    for s in signals
                ]

                sql = f"""
                    INSERT INTO {table_name}
                    (symbol, timeframe, date, open, high, low, close, volume, signal, signal_triggered_date,
                     buylevel, stoplevel, strength, signal_type, market_stage, stage_number, entry_quality_score)
                    VALUES %s
                """
                execute_values(cur, sql, signal_rows)
                conn.commit()
                total_signals += len(signals)
                logging.info(f"{symbol} {timeframe}: {len(signals)} signals")
        
        logging.info(f"{timeframe.upper()} Total: {total_signals} signals")
    
    # Final verification
    cur.execute("SELECT COUNT(*) as daily FROM buy_sell_daily_etf")
    daily = cur.fetchone()['daily']
    cur.execute("SELECT COUNT(*) as weekly FROM buy_sell_weekly_etf")
    weekly = cur.fetchone()['weekly']
    cur.execute("SELECT COUNT(*) as monthly FROM buy_sell_monthly_etf")
    monthly = cur.fetchone()['monthly']
    
    logging.info(f"\n✅ Complete:")
    logging.info(f"  Daily ETF Signals: {daily}")
    logging.info(f"  Weekly ETF Signals: {weekly}")
    logging.info(f"  Monthly ETF Signals: {monthly}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    load_etf_signals()
