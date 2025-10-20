#!/usr/bin/env python3
"""
Load Latest Technical Weekly - Fetches the latest weekly technical indicators for stocks
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
from psycopg2.extras import execute_values

# Register numpy type adapters for psycopg2
def adapt_numpy_int64(numpy_int64):
    return psycopg2.extensions.AsIs(int(numpy_int64))

def adapt_numpy_float64(numpy_float64):
    return psycopg2.extensions.AsIs(float(numpy_float64))

psycopg2.extensions.register_adapter(np.int64, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.int32, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.float64, adapt_numpy_float64)
psycopg2.extensions.register_adapter(np.float32, adapt_numpy_float64)

SCRIPT_NAME = "loadlatesttechnicalsweekly.py"
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)

def get_db_config():
    if os.environ.get("DB_SECRET_ARN"):
        secret_str = boto3.client("secretsmanager").get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
        sec = json.loads(secret_str)
        return {"host": sec["host"], "port": int(sec.get("port", 5432)), "user": sec["username"], "password": sec["password"], "dbname": sec["dbname"]}
    else:
        return {"host": os.environ.get("DB_HOST", "localhost"), "port": int(os.environ.get("DB_PORT", "5432")), "user": os.environ.get("DB_USER", "postgres"), "password": os.environ.get("DB_PASSWORD", "password"), "dbname": os.environ.get("DB_NAME", "stocks")}

def get_latest_technical_data(symbol):
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)  # 1 year for weekly data
        
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=end_date, interval="1wk")
        
        if hist.empty or len(hist) < 20:
            return None
            
        # Calculate weekly indicators
        hist['sma_4'] = hist['Close'].rolling(window=4).mean()
        hist['sma_13'] = hist['Close'].rolling(window=13).mean()
        hist['sma_26'] = hist['Close'].rolling(window=min(26, len(hist))).mean()
        
        # Get latest values
        latest_row = hist.iloc[-1]
        
        indicators = {
            'symbol': symbol.upper(),
            'date': latest_row.name.strftime('%Y-%m-%d') if hasattr(latest_row.name, 'strftime') else str(latest_row.name),
            'timeframe': 'weekly',
            'close_price': float(latest_row['Close']) if not pd.isna(latest_row['Close']) else None,
            'volume': int(latest_row['Volume']) if not pd.isna(latest_row['Volume']) else None,
            'sma_4': float(latest_row['sma_4']) if not pd.isna(latest_row['sma_4']) else None,
            'sma_13': float(latest_row['sma_13']) if not pd.isna(latest_row['sma_13']) else None,
            'sma_26': float(latest_row['sma_26']) if not pd.isna(latest_row['sma_26']) else None,
            'updated_at': datetime.now()
        }
        return indicators
    except Exception as e:
        logging.error(f"Error fetching weekly technical data for {symbol}: {e}")
        return None

def create_table(conn):
    try:
        cursor = conn.cursor()
        # Verify the technical_data_weekly table exists (created by main loader)
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'technical_data_weekly'
            );
        """)
        exists = cursor.fetchone()[0]
        cursor.close()
        if exists:
            logging.info("technical_data_weekly table verified successfully")
        else:
            raise Exception("technical_data_weekly table does not exist - run loadtechnicalsweekly.py first")
    except Exception as e:
        logging.error(f"Error verifying technical_data_weekly table: {e}")
        raise

def load_symbols_from_db(conn):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return symbols
    except Exception as e:
        raise  # Raise instead of silencing - we have real data to use

def upsert_data(conn, data):
    if not data:
        return
    try:
        cursor = conn.cursor()
        # Only upsert the columns we actually calculate
        columns = ['symbol', 'date', 'close_price', 'volume', 'sma_4', 'sma_13', 'sma_26']
        values = [tuple(d.get(col) for col in columns) for d in data]
        # For ON CONFLICT, only update indicator columns (skip symbol, date which are the key)
        update_columns = ', '.join([f"{col} = EXCLUDED.{col}" for col in columns[2:]])
        sql = f"INSERT INTO technical_data_weekly ({', '.join(columns)}) VALUES %s ON CONFLICT (symbol, date) DO UPDATE SET {update_columns}"
        execute_values(cursor, sql, values, template=None)
        conn.commit()
        cursor.close()
        logging.info(f"Upserted {len(values)} weekly records")
    except Exception as e:
        logging.error(f"Error upserting: {e}")
        conn.rollback()

def main():
    logging.info(f"Starting {SCRIPT_NAME}")
    start_time = time.time()
    
    try:
        conn = psycopg2.connect(**get_db_config())
        create_table(conn)
        symbols = load_symbols_from_db(conn)
        
        all_data = []
        for symbol in symbols[:10]:  # Limit for testing
            data = get_latest_technical_data(symbol)
            if data:
                all_data.append(data)
            time.sleep(0.1)
        
        upsert_data(conn, all_data)
        conn.close()
        
        logging.info(f" Completed! Processed {len(all_data)} symbols in {time.time() - start_time:.1f}s")
    except Exception as e:
        logging.error(f"L Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()