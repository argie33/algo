#!/usr/bin/env python3
"""
Enhanced commodity data loader - adds technicals, macro drivers, and events
Complements the main loadcommodities.py with additional intelligence data
"""
import os
import sys
import json
import pandas as pd
import numpy as np
import psycopg2
from datetime import datetime, timedelta
import logging
import requests
from typing import Dict, List, Any
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env.local')

SCRIPT_NAME = "loadcommodities_enhanced.py"
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)

# DB Config
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_USER = os.environ.get("DB_USER", "stocks")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "stocks")

def get_db_connection():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)

def create_enhanced_tables():
    """Create tables for technicals, macro drivers, inventory, events"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Technicals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commodity_technicals (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                rsi DECIMAL(8,2), macd DECIMAL(15,4), macd_signal DECIMAL(15,4), macd_hist DECIMAL(15,4),
                sma_20 DECIMAL(15,4), sma_50 DECIMAL(15,4), sma_200 DECIMAL(15,4),
                bb_upper DECIMAL(15,4), bb_lower DECIMAL(15,4), bb_pct DECIMAL(8,2),
                atr DECIMAL(15,4), signal VARCHAR(10),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            )
        """)

        # Macro drivers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commodity_macro_drivers (
                id SERIAL PRIMARY KEY,
                series_id VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                value DECIMAL(15,4),
                series_name VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(series_id, date)
            )
        """)

        # Inventory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commodity_inventory (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                report_date DATE NOT NULL,
                inventory_level DECIMAL(15,2),
                inventory_change DECIMAL(15,2),
                inventory_yoy_change DECIMAL(8,2),
                data_source VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        """)

        # Events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commodity_events (
                id SERIAL PRIMARY KEY,
                event_name VARCHAR(100) NOT NULL,
                event_date TIMESTAMP NOT NULL,
                event_type VARCHAR(50),
                description TEXT,
                impact VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        logging.info("✅ Enhanced tables created")
    except Exception as e:
        logging.error(f"❌ Error creating tables: {e}")
    finally:
        cursor.close()
        conn.close()

def calculate_technicals(symbol: str, historical_data: List[Dict]) -> List[Dict]:
    """Calculate RSI, MACD, SMA, Bollinger Bands, ATR"""
    if not historical_data or len(historical_data) < 200:
        return []

    try:
        df = pd.DataFrame(historical_data)
        df = df.sort_values('date').reset_index(drop=True)
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')

        # RSI(14)
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        df['rsi'] = 100 - (100 / (1 + gain.rolling(14).mean() / loss.rolling(14).mean()))

        # MACD
        df['ema12'] = df['close'].ewm(span=12).mean()
        df['ema26'] = df['close'].ewm(span=26).mean()
        df['macd'] = df['ema12'] - df['ema26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # SMA & Bollinger
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        df['sma_200'] = df['close'].rolling(200).mean()
        df['bb_upper'] = df['sma_20'] + (df['close'].rolling(20).std() * 2)
        df['bb_lower'] = df['sma_20'] - (df['close'].rolling(20).std() * 2)
        df['bb_pct'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower']) * 100

        # ATR
        df['atr'] = pd.concat([df['high'] - df['low'], abs(df['high'] - df['close'].shift()), abs(df['low'] - df['close'].shift())], axis=1).max(axis=1).rolling(14).mean()

        # Signal
        def signal(row):
            if pd.isna(row['rsi']) or pd.isna(row['sma_200']): return 'NEUTRAL'
            if row['close'] > row['sma_200'] and row['rsi'] < 70: return 'BUY' if row['rsi'] < 30 else 'BULLISH'
            if row['close'] < row['sma_200'] and row['rsi'] > 30: return 'SELL' if row['rsi'] > 70 else 'BEARISH'
            return 'NEUTRAL'
        df['signal'] = df.apply(signal, axis=1)

        # Return last 252 days
        return [{
            'symbol': symbol, 'date': row['date'],
            'rsi': float(row['rsi']) if pd.notna(row['rsi']) else None,
            'macd': float(row['macd']) if pd.notna(row['macd']) else None,
            'macd_signal': float(row['macd_signal']) if pd.notna(row['macd_signal']) else None,
            'macd_hist': float(row['macd_hist']) if pd.notna(row['macd_hist']) else None,
            'sma_20': float(row['sma_20']) if pd.notna(row['sma_20']) else None,
            'sma_50': float(row['sma_50']) if pd.notna(row['sma_50']) else None,
            'sma_200': float(row['sma_200']) if pd.notna(row['sma_200']) else None,
            'bb_upper': float(row['bb_upper']) if pd.notna(row['bb_upper']) else None,
            'bb_lower': float(row['bb_lower']) if pd.notna(row['bb_lower']) else None,
            'bb_pct': float(row['bb_pct']) if pd.notna(row['bb_pct']) else None,
            'atr': float(row['atr']) if pd.notna(row['atr']) else None,
            'signal': row['signal']
        } for _, row in df.tail(252).iterrows()]
    except Exception as e:
        logging.error(f"Error calculating technicals for {symbol}: {e}")
        return []

def fetch_and_save_technicals():
    """Fetch historical data, calculate technicals, save to DB"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get all symbols
        cursor.execute("SELECT DISTINCT symbol FROM commodity_prices")
        symbols = [row[0] for row in cursor.fetchall()]

        for symbol in symbols:
            # Get historical data
            cursor.execute("SELECT date, open, high, low, close, volume FROM commodity_price_history WHERE symbol=%s ORDER BY date", [symbol])
            hist_data = [{'date': row[0], 'open': row[1], 'high': row[2], 'low': row[3], 'close': row[4], 'volume': row[5]} for row in cursor.fetchall()]

            if not hist_data:
                continue

            technicals = calculate_technicals(symbol, hist_data)

            # Save to DB
            for tech in technicals:
                cursor.execute("""
                    INSERT INTO commodity_technicals (symbol, date, rsi, macd, macd_signal, macd_hist, sma_20, sma_50, sma_200, bb_upper, bb_lower, bb_pct, atr, signal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET rsi=EXCLUDED.rsi, macd=EXCLUDED.macd, signal=EXCLUDED.signal
                """, (tech['symbol'], tech['date'], tech['rsi'], tech['macd'], tech['macd_signal'], tech['macd_hist'],
                      tech['sma_20'], tech['sma_50'], tech['sma_200'], tech['bb_upper'], tech['bb_lower'], tech['bb_pct'], tech['atr'], tech['signal']))

            logging.info(f" ✅ Technicals saved for {symbol} ({len(technicals)} records)")

        conn.commit()
    except Exception as e:
        logging.error(f"Error saving technicals: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def fetch_and_save_fred_macro():
    """Fetch USD, rates, CPI from FRED"""
    try:
        from fredapi import Fred
    except ImportError:
        logging.warning("fredapi not installed. Run: pip install fredapi")
        return

    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        logging.warning("FRED_API_KEY not set")
        return

    fred = Fred(api_key=api_key)

    SERIES = {
        'DTWEXBGS': 'USD Index (Broad)',
        'FEDFUNDS': 'Fed Funds Rate',
        'DGS10': '10-Year Yield',
        'CPIAUCSL': 'CPI',
    }

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        for series_id, series_name in SERIES.items():
            try:
                data = fred.get_series(series_id, observations=120)

                for date, value in data.items():
                    cursor.execute(
                        "INSERT INTO commodity_macro_drivers (series_id, date, value, series_name) VALUES (%s, %s, %s, %s) ON CONFLICT (series_id, date) DO UPDATE SET value=EXCLUDED.value",
                        (series_id, date.date(), float(value), series_name)
                    )

                logging.info(f" ✅ Fetched {len(data)} FRED records for {series_id}")
            except Exception as e:
                logging.debug(f"Error fetching FRED {series_id}: {e}")

        conn.commit()
    except Exception as e:
        logging.error(f"Error fetching FRED: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def create_event_calendar():
    """Create economic event calendar"""
    events = []
    today = datetime.now()

    # EIA weekly (next 52 weeks, Wednesdays at 10:30 AM ET)
    current_date = today
    for _ in range(52):
        next_wed = current_date + timedelta(days=(2 - current_date.weekday()) % 7)
        if next_wed <= current_date: next_wed += timedelta(days=7)

        events.append({
            'event_name': 'EIA Petroleum Report',
            'event_date': next_wed.replace(hour=10, minute=30),
            'event_type': 'ENERGY',
            'description': 'Weekly crude oil, gasoline, distillate inventory',
            'impact': 'HIGH'
        })
        current_date = next_wed + timedelta(days=1)

    # USDA WASDE (10th of Mar, May, Aug, Nov at 12:00 PM ET)
    for month in [3, 5, 8, 11]:
        wasde = datetime(today.year, month, 10, 12, 0)
        if wasde < today: wasde = datetime(today.year + 1, month, 10, 12, 0)

        events.append({
            'event_name': 'USDA WASDE',
            'event_date': wasde,
            'event_type': 'AGRICULTURE',
            'description': 'World Agricultural Supply and Demand Estimates',
            'impact': 'HIGH'
        })

    # Save to DB
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("TRUNCATE TABLE commodity_events")
        for event in events:
            cursor.execute(
                "INSERT INTO commodity_events (event_name, event_date, event_type, description, impact) VALUES (%s, %s, %s, %s, %s)",
                (event['event_name'], event['event_date'], event['event_type'], event['description'], event['impact'])
            )
        conn.commit()
        logging.info(f" ✅ Created event calendar with {len(events)} events")
    except Exception as e:
        logging.error(f"Error saving events: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def main():
    logging.info(f"Starting {SCRIPT_NAME}")
    create_enhanced_tables()
    fetch_and_save_technicals()
    fetch_and_save_fred_macro()
    create_event_calendar()
    logging.info(f"✅ {SCRIPT_NAME} completed successfully")

if __name__ == "__main__":
    main()
