#!/usr/bin/env python3
"""
Latest Buy/Sell Weekly Signals - Incremental Loading
Efficiently updates only the most recent weekly buy/sell signals.
Updated with SSL fix for database connectivity.
"""
import os
import sys
import json
import time
import logging
import gc
import resource
from datetime import datetime, timedelta
from importlib import import_module

import pandas as pd
import numpy as np
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

SCRIPT_NAME = "loadlatestbuysellweekly.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# Database configuration
FRED_API_KEY = os.environ.get('FRED_API_KEY', '')
SECRET_ARN = os.environ["DB_SECRET_ARN"]

sm_client = boto3.client("secretsmanager")
secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
creds = json.loads(secret_resp["SecretString"])

DB_CONFIG = {
    "host": creds["host"],
    "port": int(creds.get("port", 5432)),
    "user": creds["username"],
    "password": creds["password"],
    "dbname": creds["dbname"],
    "sslmode": "require"
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG,
            sslmode='disable'
    )

def create_buy_sell_table_if_not_exists(cur):
    """Create buy_sell_weekly table if it doesn't exist"""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS buy_sell_weekly (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            timeframe VARCHAR(10) NOT NULL DEFAULT 'weekly',
            signal_type VARCHAR(10) NOT NULL,
            confidence DECIMAL(5,2) NOT NULL DEFAULT 0.0,
            price DECIMAL(12,4),
            rsi DECIMAL(5,2),
            macd DECIMAL(10,6),
            volume BIGINT,
            volume_avg_4w BIGINT,
            price_vs_ma10w DECIMAL(5,2),
            price_vs_ma26w DECIMAL(5,2),
            bollinger_position DECIMAL(5,2),
            support_level DECIMAL(12,4),
            resistance_level DECIMAL(12,4),
            pattern_score DECIMAL(5,2),
            momentum_score DECIMAL(5,2),
            risk_score DECIMAL(5,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date, timeframe, signal_type)
        );
        
        CREATE INDEX IF NOT EXISTS idx_buy_sell_weekly_symbol_date 
        ON buy_sell_weekly (symbol, date);
        
        CREATE INDEX IF NOT EXISTS idx_buy_sell_weekly_signal_date 
        ON buy_sell_weekly (signal_type, date);
    """)

def get_last_signal_date(cur, symbol, timeframe='weekly'):
    """Get the last date we have signals for this symbol"""
    cur.execute("""
        SELECT MAX(date) as last_date 
        FROM buy_sell_weekly 
        WHERE symbol = %s AND timeframe = %s
    """, (symbol, timeframe))
    
    result = cur.fetchone()
    return result['last_date'] if result and result['last_date'] else None

def get_available_data_range(cur, symbol):
    """Get the date range of available weekly price and technical data"""
    cur.execute("""
        SELECT 
            MIN(p.date) as min_price_date,
            MAX(p.date) as max_price_date,
            MIN(t.date) as min_tech_date,
            MAX(t.date) as max_tech_date
        FROM price_weekly p
        LEFT JOIN technical_data_weekly t ON p.symbol = t.symbol AND p.date = t.date
        WHERE p.symbol = %s
    """, (symbol,))
    
    return cur.fetchone()

def calculate_buy_sell_signals_weekly(price_tech_data):
    """Calculate weekly buy/sell signals"""
    signals = []
    
    if len(price_tech_data) < 26:  # Need enough data for 26-week indicators
        return signals
    
    df = pd.DataFrame(price_tech_data)
    df = df.sort_values('date')
    
    # Calculate weekly moving averages
    if 'ma10w' not in df.columns:
        df['ma10w'] = df['close'].rolling(10).mean()
    if 'ma26w' not in df.columns:
        df['ma26w'] = df['close'].rolling(26).mean()
    if 'volume_avg_4w' not in df.columns:
        df['volume_avg_4w'] = df['volume'].rolling(4).mean()
    
    # Calculate weekly Bollinger Bands
    if 'bb_upper' not in df.columns:
        bb_period = 10  # 10 weeks for weekly data
        bb_std = 2
        rolling_mean = df['close'].rolling(bb_period).mean()
        rolling_std = df['close'].rolling(bb_period).std()
        df['bb_upper'] = rolling_mean + (rolling_std * bb_std)
        df['bb_lower'] = rolling_mean - (rolling_std * bb_std)
    
    # Calculate weekly support/resistance levels
    window = 8  # 8 weeks
    df['support'] = df['low'].rolling(window).min()
    df['resistance'] = df['high'].rolling(window).max()
    
    for idx, row in df.iterrows():
        if pd.isna(row['rsi']) or pd.isna(row['macd']) or pd.isna(row['ma10w']):
            continue
            
        date = row['date']
        symbol = row['symbol']
        close = row['close']
        volume = row['volume']
        rsi = row['rsi']
        macd = row['macd']
        ma10w = row['ma10w']
        ma26w = row['ma26w']
        volume_avg = row['volume_avg_4w']
        bb_upper = row['bb_upper']
        bb_lower = row['bb_lower']
        support = row['support']
        resistance = row['resistance']
        
        # Calculate derived metrics for weekly timeframe
        price_vs_ma10w = ((close - ma10w) / ma10w) * 100 if ma10w > 0 else 0
        price_vs_ma26w = ((close - ma26w) / ma26w) * 100 if ma26w > 0 else 0
        bollinger_pos = ((close - bb_lower) / (bb_upper - bb_lower)) * 100 if (bb_upper - bb_lower) > 0 else 50
        volume_ratio = volume / volume_avg if volume_avg > 0 else 1
        
        # Weekly signal calculation (more conservative thresholds)
        buy_score = 0
        sell_score = 0
        
        # RSI signals (more conservative for weekly)
        if rsi < 35:
            buy_score += 30
        elif rsi > 65:
            sell_score += 30
        
        # MACD signals
        if macd > 0:
            buy_score += 20
        else:
            sell_score += 20
        
        # Moving average signals (weekly trend confirmation)
        if close > ma10w > ma26w:
            buy_score += 25
        elif close < ma10w < ma26w:
            sell_score += 25
        
        # Bollinger Band signals
        if bollinger_pos < 15:
            buy_score += 15
        elif bollinger_pos > 85:
            sell_score += 15
        
        # Volume confirmation (weekly)
        if volume_ratio > 1.3:
            if buy_score > sell_score:
                buy_score += 10
            else:
                sell_score += 10
        
        # Support/resistance signals
        if abs(close - support) / close < 0.03:
            buy_score += 10
        elif abs(close - resistance) / close < 0.03:
            sell_score += 10
        
        # Pattern and momentum scores
        pattern_score = min(buy_score, sell_score) / max(buy_score, sell_score, 1) * 50
        momentum_score = abs(macd) * 10 if abs(macd) < 10 else 100
        risk_score = min(rsi, 100 - rsi) + (volume_ratio * 5)
        
        # Generate signals (higher threshold for weekly)
        if buy_score >= 50:
            signals.append({
                'symbol': symbol,
                'date': date,
                'timeframe': 'weekly',
                'signal_type': 'BUY',
                'confidence': min(buy_score, 95),
                'price': close,
                'rsi': rsi,
                'macd': macd,
                'volume': volume,
                'volume_avg_4w': int(volume_avg) if not pd.isna(volume_avg) else None,
                'price_vs_ma10w': price_vs_ma10w,
                'price_vs_ma26w': price_vs_ma26w,
                'bollinger_position': bollinger_pos,
                'support_level': support,
                'resistance_level': resistance,
                'pattern_score': pattern_score,
                'momentum_score': momentum_score,
                'risk_score': risk_score
            })
        
        if sell_score >= 50:
            signals.append({
                'symbol': symbol,
                'date': date,
                'timeframe': 'weekly',
                'signal_type': 'SELL',
                'confidence': min(sell_score, 95),
                'price': close,
                'rsi': rsi,
                'macd': macd,
                'volume': volume,
                'volume_avg_4w': int(volume_avg) if not pd.isna(volume_avg) else None,
                'price_vs_ma10w': price_vs_ma10w,
                'price_vs_ma26w': price_vs_ma26w,
                'bollinger_position': bollinger_pos,
                'support_level': support,
                'resistance_level': resistance,
                'pattern_score': pattern_score,
                'momentum_score': momentum_score,
                'risk_score': risk_score
            })
    
    return signals

def process_symbol_incremental(cur, symbol, timeframe='weekly'):
    """Process weekly buy/sell signals for a symbol using incremental approach"""
    
    last_signal_date = get_last_signal_date(cur, symbol, timeframe)
    data_range = get_available_data_range(cur, symbol)
    
    if not data_range or not data_range['max_price_date']:
        logging.warning(f"No weekly price data available for {symbol}")
        return 0
    
    # Determine date range to process
    if last_signal_date:
        # Incremental update with 2-week buffer
        start_date = last_signal_date - timedelta(weeks=2)
        logging.info(f"{symbol}: Weekly incremental update from {start_date}")
        
        # Delete existing signals in the date range
        cur.execute("""
            DELETE FROM buy_sell_weekly 
            WHERE symbol = %s AND timeframe = %s AND date >= %s
        """, (symbol, timeframe, start_date))
        
    else:
        # Full history processing
        start_date = data_range['min_price_date']
        logging.info(f"{symbol}: Weekly full history processing from {start_date}")
    
    # Fetch weekly price and technical data
    cur.execute("""
        SELECT 
            p.symbol, p.date, p.open, p.high, p.low, p.close, p.adj_close, p.volume,
            t.rsi, t.macd, t.signal_line, t.macd_histogram, t.bb_upper, t.bb_lower,
            t.stoch_k, t.stoch_d, t.williams_r, t.cci, t.adx
        FROM price_weekly p
        LEFT JOIN technical_data_weekly t ON p.symbol = t.symbol AND p.date = t.date
        WHERE p.symbol = %s AND p.date >= %s
        ORDER BY p.date
    """, (symbol, start_date))
    
    price_tech_data = cur.fetchall()
    
    if not price_tech_data:
        logging.warning(f"No weekly data found for {symbol} from {start_date}")
        return 0
    
    # Calculate weekly signals
    signals = calculate_buy_sell_signals_weekly(price_tech_data)
    
    if not signals:
        logging.info(f"{symbol}: No weekly signals generated")
        return 0
    
    # Insert new signals
    insert_sql = """
        INSERT INTO buy_sell_weekly (
            symbol, date, timeframe, signal_type, confidence, price, rsi, macd,
            volume, volume_avg_4w, price_vs_ma10w, price_vs_ma26w, bollinger_position,
            support_level, resistance_level, pattern_score, momentum_score, risk_score
        ) VALUES %s
        ON CONFLICT (symbol, date, timeframe, signal_type) 
        DO UPDATE SET
            confidence = EXCLUDED.confidence,
            price = EXCLUDED.price,
            rsi = EXCLUDED.rsi,
            macd = EXCLUDED.macd,
            volume = EXCLUDED.volume,
            volume_avg_4w = EXCLUDED.volume_avg_4w,
            price_vs_ma10w = EXCLUDED.price_vs_ma10w,
            price_vs_ma26w = EXCLUDED.price_vs_ma26w,
            bollinger_position = EXCLUDED.bollinger_position,
            support_level = EXCLUDED.support_level,
            resistance_level = EXCLUDED.resistance_level,
            pattern_score = EXCLUDED.pattern_score,
            momentum_score = EXCLUDED.momentum_score,
            risk_score = EXCLUDED.risk_score,
            created_at = CURRENT_TIMESTAMP
    """
    
    signal_rows = []
    for signal in signals:
        signal_rows.append((
            signal['symbol'], signal['date'], signal['timeframe'], signal['signal_type'],
            signal['confidence'], signal['price'], signal['rsi'], signal['macd'],
            signal['volume'], signal['volume_avg_4w'], signal['price_vs_ma10w'],
            signal['price_vs_ma26w'], signal['bollinger_position'], signal['support_level'],
            signal['resistance_level'], signal['pattern_score'], signal['momentum_score'],
            signal['risk_score']
        ))
    
    execute_values(cur, insert_sql, signal_rows)
    
    logging.info(f"{symbol}: Processed {len(signals)} weekly signals")
    return len(signals)

def main():
    log_mem("Weekly script start")
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        create_buy_sell_table_if_not_exists(cur)
        conn.commit()
        
        cur.execute("""
            SELECT DISTINCT symbol 
            FROM stock_symbols 
            WHERE status = 'active'
            ORDER BY symbol
        """)
        symbols = [row['symbol'] for row in cur.fetchall()]
        
        if not symbols:
            logging.warning("No active symbols found")
            return
        
        logging.info(f"Processing {len(symbols)} symbols for latest weekly buy/sell signals")
        
        total_signals = 0
        processed_count = 0
        failed_count = 0
        
        for symbol in symbols:
            try:
                signals_count = process_symbol_incremental(cur, symbol)
                total_signals += signals_count
                processed_count += 1
                
                if processed_count % 10 == 0:
                    conn.commit()
                    logging.info(f"Weekly progress: {processed_count}/{len(symbols)} symbols processed")
                
                time.sleep(0.1)
                
            except Exception as e:
                logging.error(f"Failed to process weekly signals for {symbol}: {e}")
                failed_count += 1
                continue
        
        conn.commit()
        
        logging.info(f"=== WEEKLY SUMMARY ===")
        logging.info(f"Symbols processed: {processed_count}")
        logging.info(f"Symbols failed: {failed_count}")
        logging.info(f"Total weekly signals generated: {total_signals}")
        
        # Cleanup old weekly signals (keep last 1 year)
        cleanup_date = datetime.now().date() - timedelta(days=365)
        cur.execute("""
            DELETE FROM buy_sell_weekly 
            WHERE date < %s
        """, (cleanup_date,))
        
        deleted_count = cur.rowcount
        if deleted_count > 0:
            logging.info(f"Cleaned up {deleted_count} old weekly signals before {cleanup_date}")
        
        conn.commit()
        
    except Exception as e:
        logging.error(f"Weekly script failed: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
        log_mem("Weekly script end")

if __name__ == "__main__":
    main()