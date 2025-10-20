#!/usr/bin/env python3
"""
Load Latest Technical Daily - Fetches the latest daily technical indicators for stocks
This is a lightweight version that gets only the most recent technical data.
Updated: 2025-01-16 - Trigger technical data loading for APIs
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta

import boto3
import psycopg2
import psycopg2.extensions
import yfinance as yf
import pandas as pd
import numpy as np
from psycopg2.extras import RealDictCursor, execute_values

# Register numpy type adapters for psycopg2
def adapt_numpy_int64(numpy_int64):
    return psycopg2.extensions.AsIs(int(numpy_int64))

def adapt_numpy_float64(numpy_float64):
    return psycopg2.extensions.AsIs(float(numpy_float64))

psycopg2.extensions.register_adapter(np.int64, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.int32, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.float64, adapt_numpy_float64)
psycopg2.extensions.register_adapter(np.float32, adapt_numpy_float64)

# Script metadata & logging setup
SCRIPT_NAME = "loadlatesttechnicalsdaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

def get_db_config():
    """Get database configuration - works in AWS and locally"""
    if os.environ.get("DB_SECRET_ARN"):
        # AWS mode - use Secrets Manager
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

def calculate_simple_technical_indicators(df):
    """Calculate basic technical indicators for the latest data point"""
    try:
        if df.empty or len(df) < 20:
            return {}
            
        # Get the latest row
        latest = df.iloc[-1]
        
        # Simple Moving Averages
        df['sma_5'] = df['Close'].rolling(window=5).mean()
        df['sma_10'] = df['Close'].rolling(window=10).mean() 
        df['sma_20'] = df['Close'].rolling(window=20).mean()
        df['sma_50'] = df['Close'].rolling(window=min(50, len(df))).mean()
        
        # RSI (simplified calculation)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD (simplified)
        exp1 = df['Close'].ewm(span=12).mean()
        exp2 = df['Close'].ewm(span=26).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        # Bollinger Bands
        rolling_mean = df['Close'].rolling(window=20).mean()
        rolling_std = df['Close'].rolling(window=20).std()
        df['bb_upper'] = rolling_mean + (rolling_std * 2)
        df['bb_lower'] = rolling_mean - (rolling_std * 2)
        df['bb_middle'] = rolling_mean
        
        # Volume indicators
        df['volume_sma'] = df['Volume'].rolling(window=20).mean()
        
        # Get latest values
        latest_row = df.iloc[-1]
        
        indicators = {
            'date': latest_row.name.strftime('%Y-%m-%d') if hasattr(latest_row.name, 'strftime') else str(latest_row.name),
            'close_price': float(latest_row['Close']) if not pd.isna(latest_row['Close']) else None,
            'volume': int(latest_row['Volume']) if not pd.isna(latest_row['Volume']) else None,
            'sma_5': float(latest_row['sma_5']) if not pd.isna(latest_row['sma_5']) else None,
            'sma_10': float(latest_row['sma_10']) if not pd.isna(latest_row['sma_10']) else None,
            'sma_20': float(latest_row['sma_20']) if not pd.isna(latest_row['sma_20']) else None,
            'sma_50': float(latest_row['sma_50']) if not pd.isna(latest_row['sma_50']) else None,
            'rsi': float(latest_row['rsi']) if not pd.isna(latest_row['rsi']) else None,
            'macd': float(latest_row['macd']) if not pd.isna(latest_row['macd']) else None,
            'macd_signal': float(latest_row['macd_signal']) if not pd.isna(latest_row['macd_signal']) else None,
            'macd_histogram': float(latest_row['macd_histogram']) if not pd.isna(latest_row['macd_histogram']) else None,
            'bb_upper': float(latest_row['bb_upper']) if not pd.isna(latest_row['bb_upper']) else None,
            'bb_middle': float(latest_row['bb_middle']) if not pd.isna(latest_row['bb_middle']) else None,
            'bb_lower': float(latest_row['bb_lower']) if not pd.isna(latest_row['bb_lower']) else None,
            'volume_sma': float(latest_row['volume_sma']) if not pd.isna(latest_row['volume_sma']) else None,
        }
        
        return indicators
        
    except Exception as e:
        logging.error(f"Error calculating technical indicators: {e}")
        return {}

def get_latest_technical_data(symbol):
    """Fetch latest technical data for a symbol"""
    try:
        # Get 3 months of data to calculate indicators
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=end_date, interval="1d")
        
        if hist.empty:
            logging.warning(f"No historical data found for {symbol}")
            return None
            
        # Calculate indicators
        indicators = calculate_simple_technical_indicators(hist)
        
        if not indicators:
            return None
            
        # Add symbol and metadata
        indicators['symbol'] = symbol.upper()
        indicators['updated_at'] = datetime.now()
        indicators['timeframe'] = 'daily'
        
        return indicators
        
    except Exception as e:
        logging.error(f"Error fetching technical data for {symbol}: {e}")
        return None

def load_symbols_from_db(conn):
    """Load all active symbols from database"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        logging.info(f"Loaded {len(symbols)} symbols from database")
        return symbols
    except Exception as e:
        logging.error(f"Error loading symbols from database: {e}")
        raise  # Raise instead of silencing - we have real data to use

def create_latest_technicals_table(conn):
    """Verify technical_data_daily table exists (created by main loader)"""
    try:
        cursor = conn.cursor()
        # Just verify the table exists - it should be created by loadtechnicalsdaily.py
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'technical_data_daily'
            );
        """)
        exists = cursor.fetchone()[0]
        cursor.close()
        if exists:
            logging.info("technical_data_daily table verified successfully")
        else:
            raise Exception("technical_data_daily table does not exist - run loadtechnicalsdaily.py first")
    except Exception as e:
        logging.error(f"Error verifying technical_data_daily table: {e}")
        raise

def upsert_technical_data(conn, technical_data):
    """Upsert technical data for latest daily indicators (delta updates)"""
    if not technical_data:
        return

    try:
        cursor = conn.cursor()

        # Only upsert the technical indicators we actually calculate
        # (not price data - that's handled by other loaders)
        columns = [
            'symbol', 'date',
            'sma_10', 'sma_20', 'sma_50', 'rsi',
            'macd', 'macd_signal', 'macd_hist',
            'bbands_upper', 'bbands_middle', 'bbands_lower'
        ]

        # Build values - map from calculated indicators to table columns
        values = []
        for data in technical_data:
            # Handle the mapping of calculated values
            row = (
                data.get('symbol'),
                data.get('date'),
                data.get('sma_10'),          # We calculate sma_10 directly
                data.get('sma_20'),          # We calculate sma_20 directly
                data.get('sma_50'),          # We calculate sma_50 directly
                data.get('rsi'),
                data.get('macd'),
                data.get('macd_signal'),
                data.get('macd_histogram'),  # Maps to macd_hist in DB
                data.get('bb_upper'),        # Maps to bbands_upper in DB
                data.get('bb_middle'),       # Maps to bbands_middle in DB
                data.get('bb_lower')         # Maps to bbands_lower in DB
            )
            values.append(row)

        # Build the INSERT statement for only the columns we calculate
        columns_str = ', '.join(columns)

        # For ON CONFLICT, we only update the indicator columns (skip symbol and date which are the key)
        update_cols = [f"{col} = EXCLUDED.{col}" for col in columns[2:]]  # Skip symbol, date
        update_str = ', '.join(update_cols)

        # execute_values expects VALUES %s for the tuple placeholder
        upsert_sql = f"""
        INSERT INTO technical_data_daily ({columns_str})
        VALUES %s
        ON CONFLICT (symbol, date)
        DO UPDATE SET {update_str}
        """

        # Use execute_values with proper template format for bulk insert
        from psycopg2.extras import execute_values
        execute_values(cursor, upsert_sql, values, template=None, page_size=100)
        conn.commit()
        cursor.close()

        logging.info(f"Successfully upserted {len(values)} latest daily technical records")

    except Exception as e:
        logging.error(f"Error upserting technical data: {e}")
        conn.rollback()
        raise

def main():
    """Main execution function"""
    logging.info(f"Starting {SCRIPT_NAME}")
    start_time = time.time()
    
    try:
        # Get database configuration and connect
        db_config = get_db_config()
        logging.info("Connecting to database...")
        
        conn = psycopg2.connect(**db_config)
        logging.info("Database connected successfully")
        
        # Create table if needed
        create_latest_technicals_table(conn)
        
        # Load symbols to process
        symbols = load_symbols_from_db(conn)
        logging.info(f"Processing {len(symbols)} symbols for latest technical data")
        
        # Process symbols in batches
        batch_size = 10
        all_technical_data = []
        
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            logging.info(f"Processing batch {i//batch_size + 1}/{(len(symbols) + batch_size - 1)//batch_size}: {batch_symbols}")
            
            batch_data = []
            for symbol in batch_symbols:
                tech_data = get_latest_technical_data(symbol)
                if tech_data:
                    batch_data.append(tech_data)
                time.sleep(0.1)  # Rate limiting
            
            # Insert batch
            if batch_data:
                upsert_technical_data(conn, batch_data)
                all_technical_data.extend(batch_data)
            
            # Progress logging
            if (i // batch_size + 1) % 5 == 0:
                elapsed = time.time() - start_time
                logging.info(f"Processed {i + len(batch_symbols)} symbols in {elapsed:.1f}s")
        
        conn.close()
        
        # Final summary
        total_time = time.time() - start_time
        logging.info(f" {SCRIPT_NAME} completed successfully!")
        logging.info(f"=� Processed {len(symbols)} symbols")
        logging.info(f"( Loaded {len(all_technical_data)} latest technical records")
        logging.info(f"�  Total time: {total_time:.1f}s")
        
    except Exception as e:
        logging.error(f"L Error in {SCRIPT_NAME}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()