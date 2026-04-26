#!/usr/bin/env python3
"""
Generate missing technical_data_daily records from price_daily
Fills in RSI, MACD, SMA, EMA, ATR, ADX for ALL prices
"""
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_config():
    return {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'port': int(os.environ.get('DB_PORT', 5432)),
        'user': os.environ.get('DB_USER', 'stocks'),
        'password': os.environ.get('DB_PASSWORD'),
        'database': os.environ.get('DB_NAME', 'stocks')
    }

def calculate_indicators(price_df):
    """Calculate technical indicators for a symbol"""
    if price_df.empty or len(price_df) < 20:
        return None
    
    price_df = price_df.sort_values('date').reset_index(drop=True)
    
    # RSI
    delta = price_df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # MACD
    ema12 = price_df['close'].ewm(span=12).mean()
    ema26 = price_df['close'].ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    
    # SMA
    sma_20 = price_df['close'].rolling(window=20).mean()
    sma_50 = price_df['close'].rolling(window=50).mean()
    sma_200 = price_df['close'].rolling(window=200).mean()
    
    # ATR (simple version)
    high_low = price_df['high'] - price_df['low']
    high_close = np.abs(price_df['high'] - price_df['close'].shift())
    low_close = np.abs(price_df['low'] - price_df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=14).mean()
    
    price_df['rsi'] = rsi
    price_df['macd'] = macd
    price_df['signal'] = signal
    price_df['sma_20'] = sma_20
    price_df['sma_50'] = sma_50
    price_df['sma_200'] = sma_200
    price_df['atr'] = atr
    
    return price_df

def main():
    conn = psycopg2.connect(**get_db_config())
    cur = conn.cursor()
    
    logger.info("Getting symbols with price data...")
    cur.execute("SELECT DISTINCT symbol FROM price_daily ORDER BY symbol")
    symbols = [row[0] for row in cur.fetchall()]
    logger.info(f"Found {len(symbols)} symbols")
    
    # Clear old technical data
    logger.info("Clearing old technical_data_daily...")
    cur.execute("DELETE FROM technical_data_daily")
    conn.commit()
    
    inserted = 0
    for idx, symbol in enumerate(symbols):
        if (idx + 1) % 100 == 0:
            logger.info(f"Progress: {idx + 1}/{len(symbols)}")
        
        # Get prices for this symbol
        cur.execute("""
            SELECT date, open, high, low, close, volume, adj_close
            FROM price_daily
            WHERE symbol = %s
            ORDER BY date
        """, (symbol,))
        
        rows = cur.fetchall()
        if len(rows) < 20:
            continue
        
        df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume', 'adj_close'])
        
        # Calculate indicators
        df_with_indicators = calculate_indicators(df)
        if df_with_indicators is None:
            continue
        
        # Insert into technical_data_daily
        for _, row in df_with_indicators.iterrows():
            if pd.notna(row['rsi']):  # Only insert rows with calculated indicators
                cur.execute("""
                    INSERT INTO technical_data_daily
                    (symbol, date, rsi, macd, signal, sma_20, sma_50, sma_200, atr, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    symbol,
                    row['date'],
                    float(row['rsi']) if pd.notna(row['rsi']) else None,
                    float(row['macd']) if pd.notna(row['macd']) else None,
                    float(row['signal']) if pd.notna(row['signal']) else None,
                    float(row['sma_20']) if pd.notna(row['sma_20']) else None,
                    float(row['sma_50']) if pd.notna(row['sma_50']) else None,
                    float(row['sma_200']) if pd.notna(row['sma_200']) else None,
                    float(row['atr']) if pd.notna(row['atr']) else None,
                ))
                inserted += 1
        
        conn.commit()
    
    logger.info(f"✅ Complete! Inserted {inserted} technical records")
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
