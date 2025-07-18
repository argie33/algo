#!/usr/bin/env python3
"""
Latest Buy/Sell Daily Signals - Incremental Loading
Efficiently updates only the most recent buy/sell signals instead of full reload.
Based on proven incremental loading patterns from loadlatestpricedaily.py.
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

SCRIPT_NAME = "loadlatestbuyselldaily.py"
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
            sslmode='require'
    )

def create_buy_sell_table_if_not_exists(cur):
    """Create buy_sell_daily table if it doesn't exist"""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS buy_sell_daily (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            timeframe VARCHAR(10) NOT NULL DEFAULT 'daily',
            signal_type VARCHAR(10) NOT NULL,
            confidence DECIMAL(5,2) NOT NULL DEFAULT 0.0,
            price DECIMAL(12,4),
            rsi DECIMAL(5,2),
            macd DECIMAL(10,6),
            volume BIGINT,
            volume_avg_10d BIGINT,
            price_vs_ma20 DECIMAL(5,2),
            price_vs_ma50 DECIMAL(5,2),
            bollinger_position DECIMAL(5,2),
            support_level DECIMAL(12,4),
            resistance_level DECIMAL(12,4),
            pattern_score DECIMAL(5,2),
            momentum_score DECIMAL(5,2),
            risk_score DECIMAL(5,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date, timeframe, signal_type)
        );
        
        CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_symbol_date 
        ON buy_sell_daily (symbol, date);
        
        CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_signal_date 
        ON buy_sell_daily (signal_type, date);
    """)

def get_last_signal_date(cur, symbol, timeframe='daily'):
    """Get the last date we have signals for this symbol"""
    cur.execute("""
        SELECT MAX(date) as last_date 
        FROM buy_sell_daily 
        WHERE symbol = %s AND timeframe = %s
    """, (symbol, timeframe))
    
    result = cur.fetchone()
    return result['last_date'] if result and result['last_date'] else None

def get_available_data_range(cur, symbol):
    """Get the date range of available price and technical data"""
    cur.execute("""
        SELECT 
            MIN(p.date) as min_price_date,
            MAX(p.date) as max_price_date,
            MIN(t.date) as min_tech_date,
            MAX(t.date) as max_tech_date
        FROM price_daily p
        LEFT JOIN technical_data_daily t ON p.symbol = t.symbol AND p.date = t.date
        WHERE p.symbol = %s
    """, (symbol,))
    
    return cur.fetchone()

def calculate_buy_sell_signals(price_tech_data):
    """
    Calculate buy/sell signals based on technical indicators
    Returns list of signal records
    """
    signals = []
    
    if len(price_tech_data) < 50:  # Need enough data for indicators
        return signals
    
    df = pd.DataFrame(price_tech_data)
    df = df.sort_values('date')
    
    # Calculate additional indicators if not present
    if 'ma20' not in df.columns:
        df['ma20'] = df['close'].rolling(20).mean()
    if 'ma50' not in df.columns:
        df['ma50'] = df['close'].rolling(50).mean()
    if 'volume_avg_10d' not in df.columns:
        df['volume_avg_10d'] = df['volume'].rolling(10).mean()
    
    # Calculate Bollinger Bands if not present
    if 'bb_upper' not in df.columns:
        bb_period = 20
        bb_std = 2
        rolling_mean = df['close'].rolling(bb_period).mean()
        rolling_std = df['close'].rolling(bb_period).std()
        df['bb_upper'] = rolling_mean + (rolling_std * bb_std)
        df['bb_lower'] = rolling_mean - (rolling_std * bb_std)
        df['bb_middle'] = rolling_mean
    
    # Calculate support/resistance levels
    window = 20
    df['support'] = df['low'].rolling(window).min()
    df['resistance'] = df['high'].rolling(window).max()
    
    for idx, row in df.iterrows():
        if pd.isna(row['rsi']) or pd.isna(row['macd']) or pd.isna(row['ma20']):
            continue
            
        date = row['date']
        symbol = row['symbol']
        close = row['close']
        volume = row['volume']
        rsi = row['rsi']
        macd = row['macd']
        ma20 = row['ma20']
        ma50 = row['ma50']
        volume_avg = row['volume_avg_10d']
        bb_upper = row['bb_upper']
        bb_lower = row['bb_lower']
        bb_middle = row['bb_middle']
        support = row['support']
        resistance = row['resistance']
        
        # Calculate derived metrics
        price_vs_ma20 = ((close - ma20) / ma20) * 100 if ma20 > 0 else 0
        price_vs_ma50 = ((close - ma50) / ma50) * 100 if ma50 > 0 else 0
        bollinger_pos = ((close - bb_lower) / (bb_upper - bb_lower)) * 100 if (bb_upper - bb_lower) > 0 else 50
        volume_ratio = volume / volume_avg if volume_avg > 0 else 1
        
        # Signal calculation logic
        buy_score = 0
        sell_score = 0
        
        # RSI signals
        if rsi < 30:
            buy_score += 25
        elif rsi > 70:
            sell_score += 25
        
        # MACD signals
        if macd > 0:
            buy_score += 15
        else:
            sell_score += 15
        
        # Moving average signals
        if close > ma20 > ma50:
            buy_score += 20
        elif close < ma20 < ma50:
            sell_score += 20
        
        # Bollinger Band signals
        if bollinger_pos < 10:  # Near lower band
            buy_score += 15
        elif bollinger_pos > 90:  # Near upper band
            sell_score += 15
        
        # Volume confirmation
        if volume_ratio > 1.5:
            if buy_score > sell_score:
                buy_score += 10
            else:
                sell_score += 10
        
        # Support/resistance signals
        if abs(close - support) / close < 0.02:  # Near support
            buy_score += 10
        elif abs(close - resistance) / close < 0.02:  # Near resistance
            sell_score += 10
        
        # Pattern recognition (simplified)
        pattern_score = min(buy_score, sell_score) / max(buy_score, sell_score, 1) * 50
        momentum_score = abs(macd) * 10 if abs(macd) < 10 else 100
        risk_score = min(rsi, 100 - rsi) + (volume_ratio * 10)
        
        # Generate signals based on scores
        if buy_score >= 40:
            signals.append({
                'symbol': symbol,
                'date': date,
                'timeframe': 'daily',
                'signal_type': 'BUY',
                'confidence': min(buy_score, 95),
                'price': close,
                'rsi': rsi,
                'macd': macd,
                'volume': volume,
                'volume_avg_10d': int(volume_avg) if not pd.isna(volume_avg) else None,
                'price_vs_ma20': price_vs_ma20,
                'price_vs_ma50': price_vs_ma50,
                'bollinger_position': bollinger_pos,
                'support_level': support,
                'resistance_level': resistance,
                'pattern_score': pattern_score,
                'momentum_score': momentum_score,
                'risk_score': risk_score
            })
        
        if sell_score >= 40:
            signals.append({
                'symbol': symbol,
                'date': date,
                'timeframe': 'daily',
                'signal_type': 'SELL',
                'confidence': min(sell_score, 95),
                'price': close,
                'rsi': rsi,
                'macd': macd,
                'volume': volume,
                'volume_avg_10d': int(volume_avg) if not pd.isna(volume_avg) else None,
                'price_vs_ma20': price_vs_ma20,
                'price_vs_ma50': price_vs_ma50,
                'bollinger_position': bollinger_pos,
                'support_level': support,
                'resistance_level': resistance,
                'pattern_score': pattern_score,
                'momentum_score': momentum_score,
                'risk_score': risk_score
            })
    
    return signals

def process_symbol_incremental(cur, symbol, timeframe='daily'):
    """Process buy/sell signals for a symbol using incremental approach"""
    
    # Get last signal date
    last_signal_date = get_last_signal_date(cur, symbol, timeframe)
    
    # Get available data range
    data_range = get_available_data_range(cur, symbol)
    if not data_range or not data_range['max_price_date']:
        logging.warning(f"No price data available for {symbol}")
        return 0
    
    # Determine date range to process
    if last_signal_date:
        # Incremental update: process from last signal date minus buffer
        start_date = last_signal_date - timedelta(days=2)  # 2-day buffer for recalculation
        logging.info(f"{symbol}: Incremental update from {start_date}")
        
        # Delete existing signals in the date range we're recalculating
        cur.execute("""
            DELETE FROM buy_sell_daily 
            WHERE symbol = %s AND timeframe = %s AND date >= %s
        """, (symbol, timeframe, start_date))
        
    else:
        # Full history processing for new symbol
        start_date = data_range['min_price_date']
        logging.info(f"{symbol}: Full history processing from {start_date}")
    
    # Fetch price and technical data for the date range
    cur.execute("""
        SELECT 
            p.symbol, p.date, p.open, p.high, p.low, p.close, p.adj_close, p.volume,
            t.rsi, t.macd, t.signal_line, t.macd_histogram, t.bb_upper, t.bb_lower,
            t.stoch_k, t.stoch_d, t.williams_r, t.cci, t.adx
        FROM price_daily p
        LEFT JOIN technical_data_daily t ON p.symbol = t.symbol AND p.date = t.date
        WHERE p.symbol = %s AND p.date >= %s
        ORDER BY p.date
    """, (symbol, start_date))
    
    price_tech_data = cur.fetchall()
    
    if not price_tech_data:
        logging.warning(f"No data found for {symbol} from {start_date}")
        return 0
    
    # Calculate signals
    signals = calculate_buy_sell_signals(price_tech_data)
    
    if not signals:
        logging.info(f"{symbol}: No signals generated")
        return 0
    
    # Insert new signals
    insert_sql = """
        INSERT INTO buy_sell_daily (
            symbol, date, timeframe, signal_type, confidence, price, rsi, macd,
            volume, volume_avg_10d, price_vs_ma20, price_vs_ma50, bollinger_position,
            support_level, resistance_level, pattern_score, momentum_score, risk_score
        ) VALUES %s
        ON CONFLICT (symbol, date, timeframe, signal_type) 
        DO UPDATE SET
            confidence = EXCLUDED.confidence,
            price = EXCLUDED.price,
            rsi = EXCLUDED.rsi,
            macd = EXCLUDED.macd,
            volume = EXCLUDED.volume,
            volume_avg_10d = EXCLUDED.volume_avg_10d,
            price_vs_ma20 = EXCLUDED.price_vs_ma20,
            price_vs_ma50 = EXCLUDED.price_vs_ma50,
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
            signal['volume'], signal['volume_avg_10d'], signal['price_vs_ma20'],
            signal['price_vs_ma50'], signal['bollinger_position'], signal['support_level'],
            signal['resistance_level'], signal['pattern_score'], signal['momentum_score'],
            signal['risk_score']
        ))
    
    execute_values(cur, insert_sql, signal_rows)
    
    logging.info(f"{symbol}: Processed {len(signals)} signals")
    return len(signals)

def main():
    log_mem("Script start")
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Create table if needed
        create_buy_sell_table_if_not_exists(cur)
        conn.commit()
        
        # Get list of symbols to process
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
        
        logging.info(f"Processing {len(symbols)} symbols for latest buy/sell signals")
        
        total_signals = 0
        processed_count = 0
        failed_count = 0
        
        for symbol in symbols:
            try:
                log_mem(f"Processing {symbol}")
                signals_count = process_symbol_incremental(cur, symbol)
                total_signals += signals_count
                processed_count += 1
                
                if processed_count % 10 == 0:
                    conn.commit()
                    logging.info(f"Progress: {processed_count}/{len(symbols)} symbols processed")
                    log_mem(f"After {processed_count} symbols")
                
                # Small delay to avoid overwhelming the database
                time.sleep(0.1)
                
            except Exception as e:
                logging.error(f"Failed to process {symbol}: {e}")
                failed_count += 1
                continue
        
        conn.commit()
        
        logging.info(f"=== SUMMARY ===")
        logging.info(f"Symbols processed: {processed_count}")
        logging.info(f"Symbols failed: {failed_count}")
        logging.info(f"Total signals generated: {total_signals}")
        
        # Cleanup old signals (keep last 90 days)
        cleanup_date = datetime.now().date() - timedelta(days=90)
        cur.execute("""
            DELETE FROM buy_sell_daily 
            WHERE date < %s
        """, (cleanup_date,))
        
        deleted_count = cur.rowcount
        if deleted_count > 0:
            logging.info(f"Cleaned up {deleted_count} old signals before {cleanup_date}")
        
        conn.commit()
        
    except Exception as e:
        logging.error(f"Script failed: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
        log_mem("Script end")

if __name__ == "__main__":
    main()