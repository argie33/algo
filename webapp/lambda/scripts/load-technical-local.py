#!/usr/bin/env python3
"""
Local technical indicators loader
Modified from existing AWS loader to work locally and in AWS
"""
import os
import sys
import json
import logging
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

def get_db_config():
    """
    Get database configuration - works in AWS and locally
    """
    # Check if we're in AWS (has DB_SECRET_ARN)
    if os.environ.get("DB_SECRET_ARN"):
        # AWS mode - use Secrets Manager
        import boto3
        secret_str = boto3.client("secretsmanager").get_secret_value(
            SecretId=os.environ["DB_SECRET_ARN"]
        )["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"],
        }
    else:
        # Local mode - use environment variables or defaults
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", "5432")),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", "password"),
            "dbname": os.environ.get("DB_NAME", "stocks"),
        }

def calculate_sma(prices, window):
    """Calculate Simple Moving Average"""
    return prices.rolling(window=window).mean()

def calculate_ema(prices, span):
    """Calculate Exponential Moving Average"""
    return prices.ewm(span=span).mean()

def calculate_rsi(prices, window=14):
    """Calculate RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_bollinger_bands(prices, window=20, num_std=2):
    """Calculate Bollinger Bands"""
    sma = calculate_sma(prices, window)
    std = prices.rolling(window=window).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return upper, lower, sma

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calculate MACD"""
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def process_symbol_technical_data(symbol, db_config):
    """Calculate and update technical indicators for a symbol"""
    logging.info(f"Processing technical data for {symbol}")
    
    try:
        # Connect to database
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        
        # Get price data (last 200 days for proper calculation)
        cur.execute("""
            SELECT date, close_price, high_price, low_price, volume 
            FROM price_daily 
            WHERE symbol = %s 
            ORDER BY date ASC
            LIMIT 200
        """, (symbol,))
        
        rows = cur.fetchall()
        if not rows:
            logging.warning(f"No price data found for {symbol}")
            return
            
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=['date', 'close', 'high', 'low', 'volume'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        # Calculate technical indicators
        df['sma_20'] = calculate_sma(df['close'], 20)
        df['sma_50'] = calculate_sma(df['close'], 50)
        df['ema_12'] = calculate_ema(df['close'], 12)
        df['ema_26'] = calculate_ema(df['close'], 26)
        df['rsi'] = calculate_rsi(df['close'])
        
        # Bollinger Bands
        df['bollinger_upper'], df['bollinger_lower'], df['bollinger_middle'] = calculate_bollinger_bands(df['close'])
        
        # MACD
        df['macd'], df['macd_signal'], df['macd_histogram'] = calculate_macd(df['close'])
        
        # Update technical_data_daily table
        updates = []
        for date, row in df.iterrows():
            if pd.notna(row['sma_20']):  # Only update if we have calculated values
                updates.append((
                    float(row['sma_20']) if pd.notna(row['sma_20']) else None,
                    float(row['sma_50']) if pd.notna(row['sma_50']) else None,
                    float(row['ema_12']) if pd.notna(row['ema_12']) else None,
                    float(row['ema_26']) if pd.notna(row['ema_26']) else None,
                    float(row['rsi']) if pd.notna(row['rsi']) else None,
                    float(row['macd']) if pd.notna(row['macd']) else None,
                    float(row['macd_signal']) if pd.notna(row['macd_signal']) else None,
                    float(row['macd_histogram']) if pd.notna(row['macd_histogram']) else None,
                    float(row['bollinger_upper']) if pd.notna(row['bollinger_upper']) else None,
                    float(row['bollinger_lower']) if pd.notna(row['bollinger_lower']) else None,
                    float(row['bollinger_middle']) if pd.notna(row['bollinger_middle']) else None,
                    symbol,
                    date.strftime('%Y-%m-%d')
                ))
        
        if updates:
            # Update existing records
            execute_values(
                cur,
                """
                UPDATE technical_data_daily SET 
                    sma_20 = data.sma_20,
                    sma_50 = data.sma_50,
                    ema_12 = data.ema_12,
                    ema_26 = data.ema_26,
                    rsi = data.rsi,
                    macd = data.macd,
                    macd_signal = data.macd_signal,
                    macd_histogram = data.macd_histogram,
                    bollinger_upper = data.bollinger_upper,
                    bollinger_lower = data.bollinger_lower,
                    bollinger_middle = data.bollinger_middle
                FROM (VALUES %s) AS data(sma_20, sma_50, ema_12, ema_26, rsi, macd, macd_signal, macd_histogram, bollinger_upper, bollinger_lower, bollinger_middle, symbol, date)
                WHERE technical_data_daily.symbol = data.symbol 
                AND technical_data_daily.date = data.date::date
                """,
                updates
            )
            
            conn.commit()
            logging.info(f"Updated {len(updates)} technical records for {symbol}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        logging.error(f"Error processing {symbol}: {e}")

def main():
    """Main function to process all symbols"""
    logging.info("Starting technical indicators calculation")
    
    # Get database config (works locally and in AWS)
    db_config = get_db_config()
    logging.info(f"Connecting to database at {db_config['host']}")
    
    # Get all symbols
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM stocks ORDER BY symbol")
    symbols = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    
    logging.info(f"Processing {len(symbols)} symbols: {symbols}")
    
    # Process each symbol
    for symbol in symbols:
        process_symbol_technical_data(symbol, db_config)
    
    logging.info("Technical indicators calculation completed")

if __name__ == "__main__":
    main()