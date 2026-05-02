#!/usr/bin/env python3
# Updated: 2025-07-15 - Trigger deployment for commodities data
import os
import sys
import json
import signal
import pandas as pd
import numpy as np
import boto3
import psycopg2
from db_helper import DatabaseHelper
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import yfinance as yf
import logging
import time
import requests
from typing import Dict, List, Any
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path

# COT data library
try:
    from cot_reports.cot_reports import cot_hist
    COT_LIBRARY_AVAILABLE = True
except ImportError:
    COT_LIBRARY_AVAILABLE = False
    logging.warning("cot_reports library not installed. Run: pip install cot-reports")

def get_ticker_info_with_timeout(ticker, timeout_sec=15):
    """Safely get ticker.info (no timeout on Windows)."""
    try:
        info = ticker.info
        return info
    except Exception as e:
        logging.warning(f"Error fetching ticker.info: {str(e)[:50]}")
        return {}

# Script metadata & logging setup
SCRIPT_NAME = "loadcommodities.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Environment & Secrets - support both AWS Secrets Manager and environment variables
from dotenv import load_dotenv
load_dotenv(env_file) if (env_file := Path(__file__).parent / '.env.local').exists() else None

SECRET_ARN = os.environ.get("DB_SECRET_ARN")
DB_HOST = None
DB_PORT = None
DB_USER = None
DB_PASSWORD = None
DB_NAME = None

if SECRET_ARN:
    # Try AWS Secrets Manager first
    try:
        sm_client = boto3.client("secretsmanager")
        secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
        creds = json.loads(secret_resp["SecretString"])

        DB_USER = creds["username"]
        DB_PASSWORD = creds["password"]
        DB_HOST = creds["host"]
        DB_PORT = int(creds.get("port", 5432))
        DB_NAME = creds["dbname"]
        logging.info("Using AWS Secrets Manager for database config")
    except Exception as e:
        logging.warning(f"Failed to get database credentials from AWS Secrets Manager: {e}")
        SECRET_ARN = None

# Fall back to environment variables if AWS Secrets Manager failed or not configured
if not SECRET_ARN or DB_HOST is None:
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_USER = os.environ.get("DB_USER", "stocks")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_PORT = int(os.environ.get("DB_PORT", 5432))
    DB_NAME = os.environ.get("DB_NAME", "stocks")
    logging.info("Using environment variables for database config")

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
        database=DB_NAME
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
        logging.info(" Database tables created successfully")
        
    except Exception as e:
        conn.rollback()
        logging.error(f" Error creating tables: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def fetch_commodity_data(symbol: str) -> Dict[str, Any]:
    """Fetch commodity data from Yahoo Finance"""
    try:
        # Convert ticker format for yfinance (e.g., BRK.B → BRK-B)

        yf_symbol = symbol.replace(".", "-").replace("$", "-").upper()

        ticker = yf.Ticker(yf_symbol)

        # Get current data
        info = get_ticker_info_with_timeout(ticker, timeout_sec=15)
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
        # Convert ticker format for yfinance (e.g., BRK.B → BRK-B)

        yf_symbol = symbol.replace(".", "-").replace("$", "-").upper()

        ticker = yf.Ticker(yf_symbol)
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
        logging.info(f" Saved {len(commodity_data)} commodity prices")
        
    except Exception as e:
        conn.rollback()
        logging.error(f" Error saving prices: {e}")
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
        logging.info(f" Saved {len(historical_data)} historical records")
        
    except Exception as e:
        conn.rollback()
        logging.error(f" Error saving historical data: {e}")
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
        logging.info(" Populated commodity categories")
        
    except Exception as e:
        conn.rollback()
        logging.error(f" Error populating categories: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def fetch_cot_data(symbol: str) -> List[Dict[str, Any]]:
    """Fetch COT data from CFTC using official cot_reports library (best practice)"""
    if not COT_LIBRARY_AVAILABLE:
        logging.debug(f"cot_reports library not available for {symbol}")
        return []

    try:
        # Map Yahoo Finance symbols to CFTC contract names used by cot_reports
        cftc_contracts = {
            'CL=F': 'Crude Oil WTI',
            'NG=F': 'Natural Gas',
            'GC=F': 'Gold',
            'SI=F': 'Silver',
            'HG=F': 'Copper',
            'ZC=F': 'Corn',
            'ZS=F': 'Soybeans',
            'ZW=F': 'Wheat',
            'LE=F': 'Live Cattle',
            'HE=F': 'Lean Hogs',
        }

        if symbol not in cftc_contracts:
            logging.debug(f"No CFTC contract mapping for {symbol}")
            return []

        contract_name = cftc_contracts[symbol]

        try:
            # Use cot_hist from cot_reports library
            # This fetches the full history of COT data for the contract
            cot_df = cot_hist(contract_name)

            if cot_df is None or cot_df.empty:
                logging.debug(f"No COT data returned for {contract_name}")
                return []

            cot_records = []

            # Parse dataframe to our format
            for idx, row in cot_df.iterrows():
                try:
                    # Extract date - could be index or column
                    report_date = None

                    # Try getting from index first
                    if hasattr(idx, 'date'):
                        report_date = idx.date()
                    else:
                        try:
                            report_date = pd.to_datetime(idx).date()
                        except:
                            pass

                    # If not in index, try columns
                    if not report_date:
                        for date_col in ['Date', 'date', 'Report Date', 'report_date']:
                            if date_col in row.index and pd.notna(row[date_col]):
                                try:
                                    report_date = pd.to_datetime(row[date_col]).date()
                                    break
                                except:
                                    pass

                    if not report_date:
                        continue

                    # Extract position columns
                    def safe_val(col_names, default=0):
                        for col in col_names:
                            if col in row.index and pd.notna(row[col]):
                                try:
                                    val = row[col]
                                    return int(float(val)) if val else 0
                                except:
                                    pass
                        return default

                    # Field names from cot_reports library output
                    comm_long = safe_val(['COM_Long', 'Comm Long', 'Commercial Long'], 0)
                    comm_short = safe_val(['COM_Short', 'Comm Short', 'Commercial Short'], 0)
                    noncomm_long = safe_val(['NONCOM_Long', 'NonComm Long', 'Non-Commercial Long'], 0)
                    noncomm_short = safe_val(['NONCOM_Short', 'NonComm Short', 'Non-Commercial Short'], 0)
                    open_int = safe_val(['Open_Interest', 'Open Interest'], 0)

                    # Only add if we have position data
                    if comm_long or comm_short or noncomm_long or noncomm_short:
                        cot_records.append({
                            'symbol': symbol,
                            'report_date': report_date,
                            'commercial_long': comm_long,
                            'commercial_short': comm_short,
                            'commercial_net': comm_long - comm_short,
                            'non_commercial_long': noncomm_long,
                            'non_commercial_short': noncomm_short,
                            'non_commercial_net': noncomm_long - noncomm_short,
                            'non_reportable_long': 0,
                            'non_reportable_short': 0,
                            'non_reportable_net': 0,
                            'open_interest': open_int
                        })

                except Exception as e:
                    logging.debug(f"Error parsing COT row for {symbol}: {e}")
                    continue

            if cot_records:
                logging.info(f" ✅ Fetched {len(cot_records)} COT records for {symbol}")
            return cot_records

        except Exception as e:
            logging.debug(f"cot_hist error for {symbol}: {e}")
            return []

    except Exception as e:
        logging.debug(f"Error fetching COT data for {symbol}: {e}")
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
        logging.info(f" Saved {len(cot_records)} COT records")
        
    except Exception as e:
        conn.rollback()
        logging.error(f" Error saving COT data: {e}")
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
                avg_return = float(sum(returns) / len(returns))
                win_rate = float(len([r for r in returns if r > 0]) / len(returns) * 100)
                volatility = float(np.std(returns)) if len(returns) > 1 else 0.0

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
        logging.info(f" Saved seasonality data for {len(seasonality_data)} months")

    except Exception as e:
        conn.rollback()
        logging.error(f" Error saving seasonality data: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def calculate_correlations(symbols: List[str]) -> List[Dict[str, Any]]:
    """Calculate correlations between commodity pairs"""
    try:
        price_data = {}

        # Fetch historical data for each symbol
        for symbol in symbols:
            yf_symbol = symbol.replace(".", "-").replace("$", "-").upper()
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period="1y")

            if not hist.empty:
                price_data[symbol] = hist['Close'].values
            time.sleep(0.2)

        if len(price_data) < 2:
            return []

        # Calculate correlations for all pairs
        correlations = []
        symbols_list = list(price_data.keys())

        for i in range(len(symbols_list)):
            for j in range(i + 1, len(symbols_list)):
                sym1 = symbols_list[i]
                sym2 = symbols_list[j]

                # Get matching length data
                data1 = price_data[sym1]
                data2 = price_data[sym2]
                min_len = min(len(data1), len(data2))

                if min_len > 1:
                    try:
                        # Calculate returns - ensure same length
                        d1 = data1[-min_len:]
                        d2 = data2[-min_len:]

                        returns1 = np.diff(d1) / d1[:-1]
                        returns2 = np.diff(d2) / d2[:-1]

                        # Verify equal length before correlation
                        if len(returns1) == len(returns2) and len(returns1) > 0:
                            corr = float(np.corrcoef(returns1, returns2)[0, 1])

                            if not np.isnan(corr):
                                correlations.append({
                                    'symbol1': sym1,
                                    'symbol2': sym2,
                                    'correlation_90d': corr,
                                    'correlation_30d': corr,
                                    'correlation_1y': corr
                                })
                    except (ValueError, IndexError) as e:
                        logging.debug(f"Skipping correlation for {sym1}-{sym2}: {e}")
                        continue

        return correlations

    except Exception as e:
        logging.error(f"Error calculating correlations: {e}")
        return []

def save_correlation_data(correlation_data: List[Dict[str, Any]]):
    """Save correlation data to database"""
    if not correlation_data:
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        for record in correlation_data:
            cursor.execute("""
                INSERT INTO commodity_correlations
                (symbol1, symbol2, correlation_30d, correlation_90d, correlation_1y)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (symbol1, symbol2)
                DO UPDATE SET
                    correlation_30d = EXCLUDED.correlation_30d,
                    correlation_90d = EXCLUDED.correlation_90d,
                    correlation_1y = EXCLUDED.correlation_1y
            """, (
                record['symbol1'],
                record['symbol2'],
                record['correlation_30d'],
                record['correlation_90d'],
                record['correlation_1y']
            ))

        conn.commit()
        logging.info(f" Saved {len(correlation_data)} correlation pairs")

    except Exception as e:
        conn.rollback()
        logging.error(f" Error saving correlation data: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def populate_current_prices_from_history():
    """Populate current prices from latest historical data"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get latest price for each symbol from history
        cursor.execute("""
            WITH latest_prices AS (
                SELECT
                    symbol,
                    close as price,
                    high as high_52w,
                    low as low_52w,
                    date,
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
                FROM commodity_price_history
            ),
            prev_prices AS (
                SELECT
                    symbol,
                    close,
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
                FROM commodity_price_history
            )
            SELECT
                lp.symbol,
                lp.price,
                COALESCE(lp.price - pp.close, 0) as change_amount,
                CASE WHEN pp.close > 0 THEN (lp.price - pp.close) / pp.close * 100 ELSE 0 END as change_percent,
                0 as volume,
                lp.high_52w,
                lp.low_52w
            FROM latest_prices lp
            LEFT JOIN (
                SELECT symbol, close FROM prev_prices WHERE rn = 2
            ) pp ON lp.symbol = pp.symbol
            WHERE lp.rn = 1
        """)

        results = cursor.fetchall()
        count = 0

        for row in results:
            symbol = row[0]
            price = row[1]
            change_amount = row[2]
            change_percent = row[3]
            volume = row[4]
            high_52w = row[5]
            low_52w = row[6]

            # Get commodity name from mapping
            name = COMMODITY_SYMBOLS.get(symbol, symbol)

            cursor.execute("""
                INSERT INTO commodity_prices
                (symbol, name, price, change_amount, change_percent, volume, high_52w, low_52w, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    price = EXCLUDED.price,
                    change_amount = EXCLUDED.change_amount,
                    change_percent = EXCLUDED.change_percent,
                    volume = EXCLUDED.volume,
                    high_52w = EXCLUDED.high_52w,
                    low_52w = EXCLUDED.low_52w,
                    updated_at = EXCLUDED.updated_at
            """, (symbol, name, price, change_amount, change_percent, volume, high_52w, low_52w, datetime.now()))
            count += 1

        conn.commit()
        logging.info(f" Populated current prices for {count} commodities from historical data")

    except Exception as e:
        conn.rollback()
        logging.error(f" Error populating current prices: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def main():
    """Main execution function"""
    try:
        start_time = time.time()
        logging.info(f" Starting {SCRIPT_NAME}")

        # Create tables
        create_tables()

        # Populate categories
        populate_categories()

        # Fetch and save historical data for ALL commodities
        all_commodities = list(COMMODITY_SYMBOLS.keys())
        logging.info(f" Fetching historical data for {len(all_commodities)} commodities...")

        for symbol in all_commodities:
            logging.info(f"Fetching historical data for {symbol}...")
            historical_data = fetch_historical_data(symbol, period="2y")
            if historical_data:
                save_historical_data(historical_data)

                # Calculate and save seasonality data (only for primary commodities)
                if symbol in ['GC=F', 'SI=F', 'CL=F', 'NG=F', 'ZC=F', 'ZS=F', 'HG=F', 'LE=F', 'HE=F', 'BZ=F', 'RB=F']:
                    seasonality_data = calculate_seasonality(symbol, historical_data)
                    if seasonality_data:
                        save_seasonality_data(seasonality_data)

            time.sleep(0.5)  # Rate limiting

        # Populate current prices from historical data (Windows-compatible)
        logging.info(" Populating current prices from historical data...")
        populate_current_prices_from_history()

        # Fetch and save COT data for supported commodities
        cot_commodities = ['CL=F', 'NG=F', 'GC=F', 'SI=F', 'HG=F', 'ZC=F', 'ZS=F', 'ZW=F', 'LE=F', 'HE=F']
        logging.info(f" Fetching COT data for {len(cot_commodities)} commodities...")
        for symbol in cot_commodities:
            logging.info(f"Fetching COT data for {symbol}...")
            cot_data = fetch_cot_data(symbol)
            if cot_data:
                save_cot_data(cot_data)
            time.sleep(0.5)  # Rate limiting

        # Calculate correlations between ALL commodities
        logging.info(f" Calculating commodity correlations for {len(all_commodities)} commodities...")
        correlations = calculate_correlations(all_commodities)
        if correlations:
            save_correlation_data(correlations)

        elapsed_time = time.time() - start_time
        logging.info(f" {SCRIPT_NAME} completed successfully in {elapsed_time:.2f} seconds")

    except Exception as e:
        logging.error(f" {SCRIPT_NAME} failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()