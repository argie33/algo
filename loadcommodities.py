#!/usr/bin/env python3
# Updated: 2025-07-16 - DB timeout fix - Commodities data v8 - Post deployment fix
import os
import sys
import json
import pandas as pd
import numpy as np
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import yfinance as yf
import logging
import time
import requests
from typing import Dict, List, Any
import xml.etree.ElementTree as ET
from io import StringIO

# Script metadata & logging setup
SCRIPT_NAME = "loadcommodities.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Environment & Secrets
SECRET_ARN = os.environ.get("DB_SECRET_ARN")
if not SECRET_ARN:
    logging.error("DB_SECRET_ARN environment variable not set")
    sys.exit(1)

# Get database credentials
try:
    sm_client = boto3.client("secretsmanager")
    secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
    creds = json.loads(secret_resp["SecretString"])
    
    DB_USER = creds["username"]
    DB_PASSWORD = creds["password"]
    DB_HOST = creds["host"]
    DB_PORT = int(creds.get("port", 5432))
    DB_NAME = creds["dbname"]
except Exception as e:
    logging.error(f"Failed to get database credentials: {e}")
    sys.exit(1)

# Commodity symbols and categories
COMMODITY_SYMBOLS = {
    # Energy
    'CL=F': 'Crude Oil',
    'NG=F': 'Natural Gas', 
    'BZ=F': 'Brent Crude',
    'RB=F': 'RBOB Gasoline',
    'HO=F': 'Heating Oil',
    
    # Precious Metals
    'GC=F': 'Gold',
    'SI=F': 'Silver',
    'PL=F': 'Platinum',
    'PA=F': 'Palladium',
    'HG=F': 'Copper',
    
    # Agriculture
    'ZC=F': 'Corn',
    'ZS=F': 'Soybeans',
    'ZW=F': 'Wheat',
    'KC=F': 'Coffee',
    'SB=F': 'Sugar',
    'CC=F': 'Cocoa',
    'CT=F': 'Cotton',
    
    # Livestock
    'LE=F': 'Live Cattle',
    'GF=F': 'Feeder Cattle',
    'HE=F': 'Lean Hogs',
    
    # Currencies
    'DX-Y.NYB': 'US Dollar Index',
    'EURUSD=X': 'EUR/USD',
    'GBPUSD=X': 'GBP/USD',
    'USDJPY=X': 'USD/JPY',
    'USDCAD=X': 'USD/CAD'
}

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        sslmode="require"
    )

def create_tables():
    """Create necessary tables for commodity data"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Create commodity_prices table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commodity_prices (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                name VARCHAR(100) NOT NULL,
                price DECIMAL(15,4),
                change_amount DECIMAL(15,4),
                change_percent DECIMAL(8,4),
                volume BIGINT,
                high_52w DECIMAL(15,4),
                low_52w DECIMAL(15,4),
                market_cap BIGINT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol)
            )
        """)
        
        # Create commodity_price_history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commodity_price_history (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                open DECIMAL(15,4),
                high DECIMAL(15,4),
                low DECIMAL(15,4),
                close DECIMAL(15,4),
                volume BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            )
        """)
        
        # Create commodity_categories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commodity_categories (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                category VARCHAR(50) NOT NULL,
                subcategory VARCHAR(50),
                unit VARCHAR(50),
                exchange VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol)
            )
        """)
        
        # Create COT (Commitment of Traders) table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cot_data (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                report_date DATE NOT NULL,
                commercial_long BIGINT,
                commercial_short BIGINT,
                commercial_net BIGINT,
                non_commercial_long BIGINT,
                non_commercial_short BIGINT,
                non_commercial_net BIGINT,
                non_reportable_long BIGINT,
                non_reportable_short BIGINT,
                non_reportable_net BIGINT,
                open_interest BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        """)
        
        # Create commodity seasonality table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commodity_seasonality (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                month INTEGER NOT NULL,
                avg_return DECIMAL(8,4),
                win_rate DECIMAL(5,2),
                volatility DECIMAL(8,4),
                years_data INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, month)
            )
        """)
        
        # Create commodity correlations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commodity_correlations (
                id SERIAL PRIMARY KEY,
                symbol1 VARCHAR(20) NOT NULL,
                symbol2 VARCHAR(20) NOT NULL,
                correlation_30d DECIMAL(8,4),
                correlation_90d DECIMAL(8,4),
                correlation_1y DECIMAL(8,4),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol1, symbol2)
            )
        """)
        
        # Create commodity supply demand table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commodity_supply_demand (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                report_date DATE NOT NULL,
                supply_level DECIMAL(15,2),
                demand_level DECIMAL(15,2),
                inventory_level DECIMAL(15,2),
                supply_change_weekly DECIMAL(8,4),
                demand_change_weekly DECIMAL(8,4),
                inventory_change_weekly DECIMAL(8,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        """)
        
        conn.commit()
        logging.info("✅ Database tables created successfully")
        
    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Error creating tables: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def fetch_commodity_data(symbol: str) -> Dict[str, Any]:
    """Fetch commodity data from Yahoo Finance"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Get current data
        info = ticker.info
        hist = ticker.history(period="1d")
        
        if hist.empty:
            logging.warning(f"No data found for {symbol}")
            return None
            
        latest = hist.iloc[-1]
        
        # Get 52-week high/low
        hist_52w = ticker.history(period="1y")
        high_52w = hist_52w['High'].max() if not hist_52w.empty else None
        low_52w = hist_52w['Low'].min() if not hist_52w.empty else None
        
        # Calculate change
        if len(hist) > 1:
            prev_close = hist.iloc[-2]['Close']
            change_amount = latest['Close'] - prev_close
            change_percent = (change_amount / prev_close) * 100
        else:
            change_amount = 0
            change_percent = 0
            
        return {
            'symbol': symbol,
            'name': COMMODITY_SYMBOLS.get(symbol, symbol),
            'price': float(latest['Close']),
            'change_amount': float(change_amount),
            'change_percent': float(change_percent),
            'volume': int(latest['Volume']) if not pd.isna(latest['Volume']) else 0,
            'high_52w': float(high_52w) if high_52w else None,
            'low_52w': float(low_52w) if low_52w else None,
            'market_cap': info.get('marketCap')
        }
        
    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {e}")
        return None

def fetch_historical_data(symbol: str, period: str = "1y") -> List[Dict[str, Any]]:
    """Fetch historical commodity data"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        
        if hist.empty:
            return []
            
        historical_data = []
        for date, row in hist.iterrows():
            historical_data.append({
                'symbol': symbol,
                'date': date.date(),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume']) if not pd.isna(row['Volume']) else 0
            })
            
        return historical_data
        
    except Exception as e:
        logging.error(f"Error fetching historical data for {symbol}: {e}")
        return []

def save_current_prices(commodity_data: List[Dict[str, Any]]):
    """Save current commodity prices to database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        for data in commodity_data:
            if not data:
                continue
                
            cursor.execute("""
                INSERT INTO commodity_prices 
                (symbol, name, price, change_amount, change_percent, volume, high_52w, low_52w, market_cap, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) 
                DO UPDATE SET
                    name = EXCLUDED.name,
                    price = EXCLUDED.price,
                    change_amount = EXCLUDED.change_amount,
                    change_percent = EXCLUDED.change_percent,
                    volume = EXCLUDED.volume,
                    high_52w = EXCLUDED.high_52w,
                    low_52w = EXCLUDED.low_52w,
                    market_cap = EXCLUDED.market_cap,
                    updated_at = EXCLUDED.updated_at
            """, (
                data['symbol'],
                data['name'],
                data['price'],
                data['change_amount'],
                data['change_percent'],
                data['volume'],
                data['high_52w'],
                data['low_52w'],
                data['market_cap'],
                datetime.now()
            ))
            
        conn.commit()
        logging.info(f"✅ Saved {len(commodity_data)} commodity prices")
        
    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Error saving prices: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def save_historical_data(historical_data: List[Dict[str, Any]]):
    """Save historical commodity data to database"""
    if not historical_data:
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        for data in historical_data:
            cursor.execute("""
                INSERT INTO commodity_price_history 
                (symbol, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) 
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume
            """, (
                data['symbol'],
                data['date'],
                data['open'],
                data['high'],
                data['low'],
                data['close'],
                data['volume']
            ))
            
        conn.commit()
        logging.info(f"✅ Saved {len(historical_data)} historical records")
        
    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Error saving historical data: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def populate_categories():
    """Populate commodity categories table"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    categories = {
        'CL=F': ('energy', 'crude_oil', 'per barrel', 'NYMEX'),
        'NG=F': ('energy', 'natural_gas', 'per MMBtu', 'NYMEX'),
        'BZ=F': ('energy', 'crude_oil', 'per barrel', 'ICE'),
        'RB=F': ('energy', 'gasoline', 'per gallon', 'NYMEX'),
        'HO=F': ('energy', 'heating_oil', 'per gallon', 'NYMEX'),
        'GC=F': ('metals', 'gold', 'per troy oz', 'COMEX'),
        'SI=F': ('metals', 'silver', 'per troy oz', 'COMEX'),
        'PL=F': ('metals', 'platinum', 'per troy oz', 'NYMEX'),
        'PA=F': ('metals', 'palladium', 'per troy oz', 'NYMEX'),
        'HG=F': ('metals', 'copper', 'per pound', 'COMEX'),
        'ZC=F': ('agriculture', 'grains', 'per bushel', 'CBOT'),
        'ZS=F': ('agriculture', 'grains', 'per bushel', 'CBOT'),
        'ZW=F': ('agriculture', 'grains', 'per bushel', 'CBOT'),
        'KC=F': ('agriculture', 'soft', 'per pound', 'ICE'),
        'SB=F': ('agriculture', 'soft', 'per pound', 'ICE'),
        'CC=F': ('agriculture', 'soft', 'per metric ton', 'ICE'),
        'CT=F': ('agriculture', 'soft', 'per pound', 'ICE'),
        'LE=F': ('livestock', 'cattle', 'per pound', 'CME'),
        'GF=F': ('livestock', 'cattle', 'per pound', 'CME'),
        'HE=F': ('livestock', 'hogs', 'per pound', 'CME'),
        'DX-Y.NYB': ('forex', 'index', 'index', 'ICE'),
        'EURUSD=X': ('forex', 'major', 'exchange rate', 'Forex'),
        'GBPUSD=X': ('forex', 'major', 'exchange rate', 'Forex'),
        'USDJPY=X': ('forex', 'major', 'exchange rate', 'Forex'),
        'USDCAD=X': ('forex', 'major', 'exchange rate', 'Forex')
    }
    
    try:
        for symbol, (category, subcategory, unit, exchange) in categories.items():
            cursor.execute("""
                INSERT INTO commodity_categories (symbol, category, subcategory, unit, exchange)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (symbol) 
                DO UPDATE SET
                    category = EXCLUDED.category,
                    subcategory = EXCLUDED.subcategory,
                    unit = EXCLUDED.unit,
                    exchange = EXCLUDED.exchange
            """, (symbol, category, subcategory, unit, exchange))
            
        conn.commit()
        logging.info("✅ Populated commodity categories")
        
    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Error populating categories: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def fetch_cot_data(symbol: str) -> List[Dict[str, Any]]:
    """Fetch COT data from CFTC for a specific commodity"""
    try:
        # Map commodity symbols to CFTC commodity codes
        cftc_codes = {
            'CL=F': '067651',  # Crude Oil
            'NG=F': '023651',  # Natural Gas
            'GC=F': '088691',  # Gold
            'SI=F': '084691',  # Silver
            'HG=F': '085692',  # Copper
            'ZC=F': '002602',  # Corn
            'ZS=F': '005602',  # Soybeans
            'ZW=F': '001602',  # Wheat
            'LE=F': '057642',  # Live Cattle
            'HE=F': '054642',  # Lean Hogs
        }
        
        if symbol not in cftc_codes:
            logging.warning(f"No CFTC code found for {symbol}")
            return []
            
        cftc_code = cftc_codes[symbol]
        
        # CFTC API URL for COT data
        url = f"https://publicreporting.cftc.gov/resource/jun7-fc8e.json?commodity_code={cftc_code}&$limit=52"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        if not data:
            logging.warning(f"No COT data returned for {symbol}")
            return []
            
        cot_records = []
        for record in data:
            try:
                # Parse the record
                report_date = datetime.strptime(record['report_date_as_yyyy_mm_dd'], '%Y-%m-%d').date()
                
                cot_records.append({
                    'symbol': symbol,
                    'report_date': report_date,
                    'commercial_long': int(record.get('comm_positions_long_all', 0)),
                    'commercial_short': int(record.get('comm_positions_short_all', 0)),
                    'commercial_net': int(record.get('comm_positions_long_all', 0)) - int(record.get('comm_positions_short_all', 0)),
                    'non_commercial_long': int(record.get('noncomm_positions_long_all', 0)),
                    'non_commercial_short': int(record.get('noncomm_positions_short_all', 0)),
                    'non_commercial_net': int(record.get('noncomm_positions_long_all', 0)) - int(record.get('noncomm_positions_short_all', 0)),
                    'non_reportable_long': int(record.get('nonrept_positions_long_all', 0)),
                    'non_reportable_short': int(record.get('nonrept_positions_short_all', 0)),
                    'non_reportable_net': int(record.get('nonrept_positions_long_all', 0)) - int(record.get('nonrept_positions_short_all', 0)),
                    'open_interest': int(record.get('open_interest_all', 0))
                })
                
            except (ValueError, KeyError) as e:
                logging.error(f"Error parsing COT record for {symbol}: {e}")
                continue
                
        logging.info(f"✅ Fetched {len(cot_records)} COT records for {symbol}")
        return cot_records
        
    except requests.RequestException as e:
        logging.error(f"Error fetching COT data for {symbol}: {e}")
        return []
    except Exception as e:
        logging.error(f"Unexpected error fetching COT data for {symbol}: {e}")
        return []

def save_cot_data(cot_records: List[Dict[str, Any]]):
    """Save COT data to database"""
    if not cot_records:
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        for record in cot_records:
            cursor.execute("""
                INSERT INTO cot_data 
                (symbol, report_date, commercial_long, commercial_short, commercial_net,
                 non_commercial_long, non_commercial_short, non_commercial_net,
                 non_reportable_long, non_reportable_short, non_reportable_net, open_interest)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, report_date) 
                DO UPDATE SET
                    commercial_long = EXCLUDED.commercial_long,
                    commercial_short = EXCLUDED.commercial_short,
                    commercial_net = EXCLUDED.commercial_net,
                    non_commercial_long = EXCLUDED.non_commercial_long,
                    non_commercial_short = EXCLUDED.non_commercial_short,
                    non_commercial_net = EXCLUDED.non_commercial_net,
                    non_reportable_long = EXCLUDED.non_reportable_long,
                    non_reportable_short = EXCLUDED.non_reportable_short,
                    non_reportable_net = EXCLUDED.non_reportable_net,
                    open_interest = EXCLUDED.open_interest
            """, (
                record['symbol'],
                record['report_date'],
                record['commercial_long'],
                record['commercial_short'],
                record['commercial_net'],
                record['non_commercial_long'],
                record['non_commercial_short'],
                record['non_commercial_net'],
                record['non_reportable_long'],
                record['non_reportable_short'],
                record['non_reportable_net'],
                record['open_interest']
            ))
            
        conn.commit()
        logging.info(f"✅ Saved {len(cot_records)} COT records")
        
    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Error saving COT data: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def calculate_seasonality(symbol: str, historical_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Calculate seasonal patterns for a commodity"""
    if not historical_data:
        return []
        
    try:
        # Group data by month
        monthly_data = {}
        for record in historical_data:
            month = record['date'].month
            if month not in monthly_data:
                monthly_data[month] = []
            
            # Calculate daily return
            if record['open'] > 0:
                daily_return = (record['close'] - record['open']) / record['open']
                monthly_data[month].append(daily_return)
        
        seasonality_data = []
        for month in range(1, 13):
            if month in monthly_data and len(monthly_data[month]) >= 5:  # Need at least 5 data points
                returns = monthly_data[month]
                avg_return = sum(returns) / len(returns)
                win_rate = len([r for r in returns if r > 0]) / len(returns) * 100
                volatility = np.std(returns) if len(returns) > 1 else 0
                
                seasonality_data.append({
                    'symbol': symbol,
                    'month': month,
                    'avg_return': avg_return,
                    'win_rate': win_rate,
                    'volatility': volatility,
                    'years_data': len(returns)
                })
        
        return seasonality_data
        
    except Exception as e:
        logging.error(f"Error calculating seasonality for {symbol}: {e}")
        return []

def save_seasonality_data(seasonality_data: List[Dict[str, Any]]):
    """Save seasonality data to database"""
    if not seasonality_data:
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        for record in seasonality_data:
            cursor.execute("""
                INSERT INTO commodity_seasonality 
                (symbol, month, avg_return, win_rate, volatility, years_data)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, month) 
                DO UPDATE SET
                    avg_return = EXCLUDED.avg_return,
                    win_rate = EXCLUDED.win_rate,
                    volatility = EXCLUDED.volatility,
                    years_data = EXCLUDED.years_data
            """, (
                record['symbol'],
                record['month'],
                record['avg_return'],
                record['win_rate'],
                record['volatility'],
                record['years_data']
            ))
            
        conn.commit()
        logging.info(f"✅ Saved seasonality data for {len(seasonality_data)} months")
        
    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Error saving seasonality data: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def main():
    """Main execution function"""
    try:
        start_time = time.time()
        logging.info(f"🚀 Starting {SCRIPT_NAME}")
        
        # Create tables
        create_tables()
        
        # Populate categories
        populate_categories()
        
        # Fetch current prices
        logging.info("📊 Fetching current commodity prices...")
        current_data = []
        
        for symbol in COMMODITY_SYMBOLS.keys():
            logging.info(f"Fetching data for {symbol}...")
            data = fetch_commodity_data(symbol)
            if data:
                current_data.append(data)
            time.sleep(0.1)  # Rate limiting
            
        # Save current prices
        if current_data:
            save_current_prices(current_data)
            
        # Fetch and save historical data for key commodities
        key_commodities = ['GC=F', 'SI=F', 'CL=F', 'NG=F', 'ZC=F', 'ZS=F', 'HG=F', 'LE=F', 'HE=F']
        logging.info("📈 Fetching historical data for key commodities...")
        
        for symbol in key_commodities:
            logging.info(f"Fetching historical data for {symbol}...")
            historical_data = fetch_historical_data(symbol, period="2y")  # Need more data for seasonality
            if historical_data:
                save_historical_data(historical_data)
                
                # Calculate and save seasonality data
                seasonality_data = calculate_seasonality(symbol, historical_data)
                if seasonality_data:
                    save_seasonality_data(seasonality_data)
                    
            time.sleep(0.5)  # Rate limiting
            
        # Fetch COT data for supported commodities
        cot_commodities = ['CL=F', 'NG=F', 'GC=F', 'SI=F', 'HG=F', 'ZC=F', 'ZS=F', 'ZW=F', 'LE=F', 'HE=F']
        logging.info("📊 Fetching COT data for supported commodities...")
        
        for symbol in cot_commodities:
            logging.info(f"Fetching COT data for {symbol}...")
            cot_data = fetch_cot_data(symbol)
            if cot_data:
                save_cot_data(cot_data)
            time.sleep(1.0)  # Rate limiting for CFTC API
            
        elapsed_time = time.time() - start_time
        logging.info(f"✅ {SCRIPT_NAME} completed successfully in {elapsed_time:.2f} seconds")
        
    except Exception as e:
        logging.error(f"❌ {SCRIPT_NAME} failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()