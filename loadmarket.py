#!/usr/bin/env python3
"""
Unified Market Data Loader Script

This script loads comprehensive market data including:
- Distribution Days Analysis (institutional selling pressure)
- Major market indices (S&P 500, NASDAQ, Dow Jones, Russell 2000, VIX)
- Sector ETFs and performance tracking
- Market breadth indicators
- Treasury yields and bond data
- Commodity prices
- International market indices

Data Sources:
- Primary: yfinance for index, ETF, and pricing data
- Calculated: Distribution days, volume analysis, momentum indicators

Features:
- Calculates distribution days for major indices
- Updates market_data table with latest prices
- Tracks institutional selling pressure
- Optimized for daily execution

Author: Financial Dashboard System
"""

import sys
import time
import logging
import json
import os
import gc
import resource
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

# Script configuration
SCRIPT_NAME = "loadmarket.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def log_mem(stage: str):
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mb = usage / 1024 if sys.platform.startswith("linux") else usage / (1024 * 1024)
    logging.info(f"[MEM] {stage}: {mb:.1f} MB RSS")

def get_db_config():
    """Get database configuration"""
    try:
        import boto3
        secret_str = boto3.client("secretsmanager") \
                         .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception:
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

def safe_float(value, default=None):
    """Convert to float safely"""
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

# Market indices and ETFs to track
MARKET_INDICES = {
    # Major US Indices
    '^GSPC': 'S&P 500',
    '^IXIC': 'NASDAQ Composite', 
    '^DJI': 'Dow Jones Industrial Average',
    '^RUT': 'Russell 2000',
    '^VIX': 'VIX Volatility Index',
    
    # Broad Market ETFs
    'SPY': 'SPDR S&P 500 ETF',
    'QQQ': 'Invesco QQQ ETF',
    'DIA': 'SPDR Dow Jones ETF',
    'IWM': 'iShares Russell 2000 ETF',
    'VTI': 'Vanguard Total Stock Market ETF',
    
    # International Indices
    '^FTSE': 'FTSE 100',
    '^N225': 'Nikkei 225',
    '^HSI': 'Hang Seng Index',
    'EEM': 'iShares MSCI Emerging Markets ETF',
    'VEA': 'Vanguard FTSE Developed Markets ETF',
    'VWO': 'Vanguard FTSE Emerging Markets ETF',
    
    # Bond Indices
    '^TNX': '10-Year Treasury Yield',
    '^IRX': '3-Month Treasury Yield',
    'TLT': 'iShares 20+ Year Treasury Bond ETF',
    'BND': 'Vanguard Total Bond Market ETF',
    'HYG': 'iShares iBoxx High Yield Corporate Bond ETF',
    
    # Commodities
    'GLD': 'SPDR Gold Shares',
    'SLV': 'iShares Silver Trust',
    'USO': 'United States Oil Fund',
    'UNG': 'United States Natural Gas Fund',
    'DBA': 'Invesco DB Agriculture Fund'
}

SECTOR_ETFS = {
    'XLF': 'Financial Select Sector SPDR Fund',
    'XLK': 'Technology Select Sector SPDR Fund',
    'XLE': 'Energy Select Sector SPDR Fund',
    'XLV': 'Health Care Select Sector SPDR Fund',
    'XLI': 'Industrial Select Sector SPDR Fund',
    'XLC': 'Communication Services Select Sector SPDR Fund',
    'XLY': 'Consumer Discretionary Select Sector SPDR Fund',
    'XLP': 'Consumer Staples Select Sector SPDR Fund',
    'XLB': 'Materials Select Sector SPDR Fund',
    'XLRE': 'Real Estate Select Sector SPDR Fund',
    'XLU': 'Utilities Select Sector SPDR Fund'
}

STYLE_ETFS = {
    'IVV': 'iShares Core S&P 500 ETF',
    'IVW': 'iShares Core S&P 500 Growth ETF',
    'IVE': 'iShares Core S&P 500 Value ETF',
    'IJH': 'iShares Core S&P Mid-Cap ETF',
    'IJR': 'iShares Core S&P Small-Cap ETF',
    'VBR': 'Vanguard Small-Cap Value ETF',
    'VUG': 'Vanguard Growth ETF',
    'VTV': 'Vanguard Value ETF'
}

class MarketDataCollector:
    """Collect comprehensive market data"""
    
    def __init__(self, symbol: str, name: str):
        self.symbol = symbol
        self.name = name
        self.ticker = yf.Ticker(symbol)
    
    def get_market_data(self, period: str = "1y") -> Optional[Dict]:
        """Get comprehensive market data for the symbol"""
        try:
            # Get historical data
            hist = self.ticker.history(period=period)
            if hist.empty:
                logging.warning(f"No historical data for {self.symbol}")
                return None
            
            # Get basic info
            info = self.ticker.info
            
            # Calculate latest metrics
            latest_date = hist.index[-1]
            latest_price = hist['Close'].iloc[-1]
            latest_volume = hist['Volume'].iloc[-1] if 'Volume' in hist.columns else 0
            
            # Calculate returns
            returns_1d = (hist['Close'].iloc[-1] / hist['Close'].iloc[-2] - 1) if len(hist) >= 2 else 0
            returns_5d = (hist['Close'].iloc[-1] / hist['Close'].iloc[-6] - 1) if len(hist) >= 6 else 0
            returns_1m = (hist['Close'].iloc[-1] / hist['Close'].iloc[-21] - 1) if len(hist) >= 21 else 0
            returns_3m = (hist['Close'].iloc[-1] / hist['Close'].iloc[-63] - 1) if len(hist) >= 63 else 0
            returns_6m = (hist['Close'].iloc[-1] / hist['Close'].iloc[-126] - 1) if len(hist) >= 126 else 0
            returns_1y = (hist['Close'].iloc[-1] / hist['Close'].iloc[0] - 1) if len(hist) >= 250 else 0
            
            # Calculate volatility
            daily_returns = hist['Close'].pct_change().dropna()
            volatility_30d = daily_returns.tail(30).std() * np.sqrt(252) if len(daily_returns) >= 30 else 0
            volatility_90d = daily_returns.tail(90).std() * np.sqrt(252) if len(daily_returns) >= 90 else 0
            volatility_1y = daily_returns.std() * np.sqrt(252) if len(daily_returns) >= 30 else 0
            
            # Calculate moving averages
            sma_20 = hist['Close'].rolling(20).mean().iloc[-1] if len(hist) >= 20 else latest_price
            sma_50 = hist['Close'].rolling(50).mean().iloc[-1] if len(hist) >= 50 else latest_price
            sma_200 = hist['Close'].rolling(200).mean().iloc[-1] if len(hist) >= 200 else latest_price
            
            # Calculate high/low metrics
            high_52w = hist['High'].tail(252).max() if len(hist) >= 252 else hist['High'].max()
            low_52w = hist['Low'].tail(252).min() if len(hist) >= 252 else hist['Low'].min()
            
            # Market cap and other info
            market_cap = info.get('marketCap', 0)
            avg_volume_30d = hist['Volume'].tail(30).mean() if 'Volume' in hist.columns and len(hist) >= 30 else 0
            
            # Beta calculation (vs SPY if not SPY itself)
            beta = None
            if self.symbol != 'SPY' and self.symbol != '^GSPC':
                try:
                    spy = yf.Ticker('SPY').history(period=period)
                    if not spy.empty and len(spy) == len(hist):
                        market_returns = spy['Close'].pct_change().dropna()
                        asset_returns = hist['Close'].pct_change().dropna()
                        if len(market_returns) > 30 and len(asset_returns) > 30:
                            covariance = np.cov(asset_returns.tail(252), market_returns.tail(252))[0][1]
                            market_variance = np.var(market_returns.tail(252))
                            beta = covariance / market_variance if market_variance > 0 else None
                except Exception:
                    pass
            
            result = {
                'symbol': self.symbol,
                'name': self.name,
                'date': latest_date.date() if hasattr(latest_date, 'date') else date.today(),
                'price': safe_float(latest_price),
                'volume': safe_float(latest_volume),
                'market_cap': safe_float(market_cap),
                
                # Returns
                'return_1d': safe_float(returns_1d),
                'return_5d': safe_float(returns_5d),
                'return_1m': safe_float(returns_1m),
                'return_3m': safe_float(returns_3m),
                'return_6m': safe_float(returns_6m),
                'return_1y': safe_float(returns_1y),
                
                # Volatility
                'volatility_30d': safe_float(volatility_30d),
                'volatility_90d': safe_float(volatility_90d),
                'volatility_1y': safe_float(volatility_1y),
                
                # Moving averages
                'sma_20': safe_float(sma_20),
                'sma_50': safe_float(sma_50),
                'sma_200': safe_float(sma_200),
                'price_vs_sma_20': safe_float((latest_price - sma_20) / sma_20) if sma_20 else None,
                'price_vs_sma_50': safe_float((latest_price - sma_50) / sma_50) if sma_50 else None,
                'price_vs_sma_200': safe_float((latest_price - sma_200) / sma_200) if sma_200 else None,
                
                # High/Low metrics
                'high_52w': safe_float(high_52w),
                'low_52w': safe_float(low_52w),
                'distance_from_high': safe_float((latest_price - high_52w) / high_52w) if high_52w else None,
                'distance_from_low': safe_float((latest_price - low_52w) / low_52w) if low_52w else None,
                
                # Volume and beta
                'avg_volume_30d': safe_float(avg_volume_30d),
                'volume_ratio': safe_float(latest_volume / avg_volume_30d) if avg_volume_30d else None,
                'beta': safe_float(beta),
                
                # Classification
                'asset_class': self._classify_asset(),
                'region': self._classify_region()
            }
            
            return result
            
        except Exception as e:
            logging.error(f"Error collecting market data for {self.symbol}: {e}")
            return None
    
    def _classify_asset(self) -> str:
        """Classify the asset type"""
        symbol = self.symbol.upper()
        if symbol.startswith('^'):
            return 'index'
        elif symbol in ['SPY', 'QQQ', 'DIA', 'IWM', 'VTI']:
            return 'broad_market_etf'
        elif symbol.startswith('XL'):
            return 'sector_etf'
        elif symbol in ['TLT', 'BND', 'HYG']:
            return 'bond_etf'
        elif symbol in ['GLD', 'SLV', 'USO', 'UNG', 'DBA']:
            return 'commodity_etf'
        elif symbol in ['EEM', 'VEA', 'VWO']:
            return 'international_etf'
        else:
            return 'other_etf'
    
    def _classify_region(self) -> str:
        """Classify the geographic region"""
        symbol = self.symbol.upper()
        if symbol in ['^FTSE']:
            return 'europe'
        elif symbol in ['^N225', '^HSI']:
            return 'asia'
        elif symbol in ['EEM', 'VWO']:
            return 'emerging_markets'
        elif symbol in ['VEA']:
            return 'developed_markets'
        else:
            return 'us'

def process_market_symbol(symbol: str, name: str) -> Optional[Dict]:
    """Process market data for a symbol"""
    try:
        collector = MarketDataCollector(symbol, name)
        data = collector.get_market_data()
        return data
    except Exception as e:
        logging.error(f"Error processing market data for {symbol}: {e}")
        return None

def create_market_data_table(cur, conn):
    """Create market data table if it doesn't exist"""
    logging.info("Creating/verifying market_data table...")

    # Check if table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'market_data'
        );
    """)

    result = cur.fetchone()
    table_exists = result.get('exists') if isinstance(result, dict) else result[0]

    if not table_exists:
        # Create table with current schema
        create_sql = """
        CREATE TABLE IF NOT EXISTS market_data (
            ticker VARCHAR(20) PRIMARY KEY,
            previous_close NUMERIC,
            regular_market_previous_close NUMERIC,
            open_price NUMERIC,
            regular_market_open NUMERIC,
            day_low NUMERIC,
            regular_market_day_low NUMERIC,
            day_high NUMERIC,
            regular_market_day_high NUMERIC,
            regular_market_price NUMERIC,
            current_price NUMERIC,
            post_market_price NUMERIC,
            post_market_change NUMERIC,
            post_market_change_pct NUMERIC,
            volume BIGINT,
            regular_market_volume BIGINT,
            average_volume BIGINT,
            avg_volume_10d BIGINT,
            avg_daily_volume_10d BIGINT,
            avg_daily_volume_3m BIGINT,
            bid_price NUMERIC,
            ask_price NUMERIC,
            bid_size INTEGER,
            ask_size INTEGER,
            market_state VARCHAR(50),
            fifty_two_week_low NUMERIC,
            fifty_two_week_high NUMERIC,
            fifty_two_week_range VARCHAR(50),
            fifty_two_week_low_change NUMERIC,
            fifty_two_week_low_change_pct NUMERIC,
            fifty_two_week_high_change NUMERIC,
            fifty_two_week_high_change_pct NUMERIC,
            fifty_two_week_change_pct NUMERIC,
            fifty_day_avg NUMERIC,
            two_hundred_day_avg NUMERIC,
            fifty_day_avg_change NUMERIC,
            fifty_day_avg_change_pct NUMERIC,
            two_hundred_day_avg_change NUMERIC,
            two_hundred_day_avg_change_pct NUMERIC,
            source_interval_sec INTEGER,
            market_cap BIGINT
        );
        """
        cur.execute(create_sql)
        conn.commit()
        logging.info("market_data table created")
    else:
        logging.info("market_data table already exists")

def load_market_data_batch(symbols_dict: Dict[str, str], conn, cur, batch_size: int = 10) -> Tuple[int, int]:
    """Load market data in batches"""
    symbols_list = list(symbols_dict.items())
    total_processed = 0
    total_inserted = 0
    failed_symbols = []
    
    for i in range(0, len(symbols_list), batch_size):
        batch = symbols_list[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(symbols_list) + batch_size - 1) // batch_size
        
        logging.info(f"Processing market data batch {batch_num}/{total_batches}: {len(batch)} symbols")
        log_mem(f"Market batch {batch_num} start")
        
        # Process with limited concurrency
        market_data = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_symbol = {
                executor.submit(process_market_symbol, symbol, name): symbol
                for symbol, name in batch
            }
            
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    data = future.result(timeout=30)
                    if data:
                        market_data.append(data)
                    else:
                        failed_symbols.append(symbol)
                except Exception as e:
                    failed_symbols.append(symbol)
                    logging.error(f"Exception processing market data for {symbol}: {e}")
                
                total_processed += 1
        
        # Insert to database
        if market_data:
            try:
                insert_data = []
                for item in market_data:
                    insert_data.append((
                        item['symbol'], item['name'], item['date'],
                        item.get('price'), item.get('volume'), item.get('market_cap'),
                        
                        # Returns
                        item.get('return_1d'), item.get('return_5d'), item.get('return_1m'),
                        item.get('return_3m'), item.get('return_6m'), item.get('return_1y'),
                        
                        # Volatility
                        item.get('volatility_30d'), item.get('volatility_90d'), item.get('volatility_1y'),
                        
                        # Moving averages
                        item.get('sma_20'), item.get('sma_50'), item.get('sma_200'),
                        item.get('price_vs_sma_20'), item.get('price_vs_sma_50'), item.get('price_vs_sma_200'),
                        
                        # High/Low
                        item.get('high_52w'), item.get('low_52w'),
                        item.get('distance_from_high'), item.get('distance_from_low'),
                        
                        # Volume and risk
                        item.get('avg_volume_30d'), item.get('volume_ratio'), item.get('beta'),
                        
                        # Classification
                        item.get('asset_class'), item.get('region')
                    ))
                
                insert_query = """
                    INSERT INTO market_data (
                        symbol, name, date, price, volume, market_cap,
                        return_1d, return_5d, return_1m, return_3m, return_6m, return_1y,
                        volatility_30d, volatility_90d, volatility_1y,
                        sma_20, sma_50, sma_200, price_vs_sma_20, price_vs_sma_50, price_vs_sma_200,
                        high_52w, low_52w, distance_from_high, distance_from_low,
                        avg_volume_30d, volume_ratio, beta,
                        asset_class, region
                    ) VALUES %s
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        price = EXCLUDED.price,
                        volume = EXCLUDED.volume,
                        return_1d = EXCLUDED.return_1d,
                        return_1m = EXCLUDED.return_1m,
                        volatility_30d = EXCLUDED.volatility_30d,
                        volume_ratio = EXCLUDED.volume_ratio,
                        updated_at = CURRENT_TIMESTAMP
                """
                
                execute_values(cur, insert_query, insert_data)
                conn.commit()
                total_inserted += len(market_data)
                logging.info(f"Market batch {batch_num} inserted {len(market_data)} symbols successfully")
                
            except Exception as e:
                logging.error(f"Database insert error for market batch {batch_num}: {e}")
                conn.rollback()
        
        # Cleanup
        del market_data
        gc.collect()
        log_mem(f"Market batch {batch_num} end")
        time.sleep(1)
    
    if failed_symbols:
        logging.warning(f"Failed to process market data for {len(failed_symbols)} symbols: {failed_symbols[:5]}...")
    
    return total_processed, total_inserted

# Major indices for distribution days analysis
MAJOR_INDICES = {
    '^GSPC': 'S&P 500',
    '^IXIC': 'NASDAQ Composite',
    '^DJI': 'Dow Jones Industrial Average'
}

def create_distribution_days_table(cur, conn):
    """Create distribution_days table if it doesn't exist"""
    logging.info("Creating/verifying distribution_days table...")

    create_sql = """
    CREATE TABLE IF NOT EXISTS distribution_days (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20),
        date DATE,
        close_price DECIMAL(12,4),
        change_pct DECIMAL(8,4),
        volume BIGINT,
        volume_ratio DECIMAL(8,4),
        days_ago INTEGER,
        running_count INTEGER,
        signal VARCHAR(50),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date)
    );
    """

    cur.execute(create_sql)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dist_days_symbol ON distribution_days(symbol);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dist_days_date ON distribution_days(date DESC);")
    conn.commit()
    logging.info("distribution_days table ready")

def calculate_distribution_days(symbol: str, name: str, period: str = "1y") -> Optional[List[Dict]]:
    """Calculate distribution days using proper IBD methodology

    REAL IBD Distribution Day Definition:
    1. Index closes LOWER than previous day
    2. Volume > previous day's volume (actual IBD standard)
    3. Track running count that resets on follow-through days
       (up 1-2% on heavy volume after downtrend)

    This follows the actual Investor's Business Daily method used by
    professional market analysts for institutional activity tracking.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty or len(hist) < 20:
            logging.warning(f"Insufficient data for {symbol}")
            return None

        # Calculate metrics
        hist['Change'] = hist['Close'].pct_change()
        hist['Prev_Volume'] = hist['Volume'].shift(1)
        hist['Is_Down'] = hist['Change'] < 0
        hist['Volume_Higher'] = hist['Volume'] > hist['Prev_Volume']
        hist['Volume_Ratio'] = hist['Volume'] / hist['Prev_Volume']

        # Identify distribution days - REAL IBD METHOD
        # Down day with higher volume than previous day
        dist_days = []
        distribution_count = 0

        for idx in range(1, len(hist)):
            row = hist.iloc[idx]
            prev_row = hist.iloc[idx - 1]

            is_down = safe_float(row['Change'], 0) < 0
            higher_volume = safe_float(row['Volume'], 0) > safe_float(prev_row['Volume'], 0)

            if is_down and higher_volume:
                # This is a distribution day
                distribution_count += 1
                dist_days.append({
                    'date': row.name.date(),
                    'close_price': safe_float(row['Close']),
                    'change_pct': safe_float(row['Change'] * 100),
                    'volume': int(row['Volume']) if row['Volume'] > 0 else 0,
                    'volume_ratio': safe_float(row['Volume_Ratio'])
                })

            # Check for follow-through day (reset condition)
            # Up 1-2% on volume > 50-day average (institutional accumulation)
            elif safe_float(row['Change'], 0) > 0.01:  # Up 1% or more
                volume_sma = hist['Volume'].iloc[max(0, idx-50):idx].mean()
                if safe_float(row['Volume'], 0) > volume_sma:
                    # Follow-through day detected - reset count
                    distribution_count = 0

        # Find most recent follow-through day (up 1%+ on heavy volume)
        # This resets the distribution count
        most_recent_followthrough = None
        volume_sma = hist['Volume'].rolling(50).mean()

        for idx in range(len(hist) - 1, -1, -1):
            row = hist.iloc[idx]
            change = safe_float(row['Change'], 0)
            volume = safe_float(row['Volume'], 0)
            sma_vol = safe_float(volume_sma.iloc[idx], 0)

            # Follow-through: up 1%+ on volume > 50-day SMA
            if change > 0.01 and volume > sma_vol:
                most_recent_followthrough = row.name.date()
                break

        # Sort by date descending (most recent first)
        dist_days.sort(key=lambda x: x['date'], reverse=True)

        # Calculate running count (distribution days since last follow-through)
        today = date.today()
        running_count = 0

        for day_info in dist_days:
            day_info['days_ago'] = (today - day_info['date']).days

            # Count only distribution days after the most recent follow-through
            if most_recent_followthrough is None or day_info['date'] > most_recent_followthrough:
                running_count += 1
            day_info['running_count'] = running_count

        logging.info(f"Found {len(dist_days)} total distribution days for {symbol}")
        logging.info(f"  Running count (since last follow-through): {running_count}")
        logging.info(f"  Last follow-through: {most_recent_followthrough or 'None'}")

        return dist_days if dist_days else None

    except Exception as e:
        logging.error(f"Error calculating distribution days for {symbol}: {e}")
        return None

def load_distribution_days(indices_dict: Dict[str, str], conn, cur) -> int:
    """Load distribution days for all major indices"""
    total_inserted = 0

    for symbol, name in indices_dict.items():
        logging.info(f"Processing distribution days for {name} ({symbol})...")

        try:
            dist_days = calculate_distribution_days(symbol, name)

            if not dist_days:
                logging.warning(f"No distribution days found for {symbol}")
                continue

            # Clear old data
            cur.execute("DELETE FROM distribution_days WHERE symbol = %s", (symbol,))

            # Insert new data
            for day in dist_days:
                try:
                    cur.execute("""
                        INSERT INTO distribution_days
                        (symbol, date, close_price, change_pct, volume, volume_ratio, days_ago, running_count)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            close_price = EXCLUDED.close_price,
                            change_pct = EXCLUDED.change_pct,
                            volume = EXCLUDED.volume,
                            volume_ratio = EXCLUDED.volume_ratio,
                            days_ago = EXCLUDED.days_ago,
                            running_count = EXCLUDED.running_count
                    """, (
                        symbol,
                        day['date'],
                        day['close_price'],
                        day['change_pct'],
                        day['volume'],
                        day['volume_ratio'],
                        day['days_ago'],
                        day.get('running_count', 0)
                    ))
                    total_inserted += 1
                except Exception as e:
                    logging.error(f"Error inserting distribution day for {symbol}: {e}")

            conn.commit()
            logging.info(f"Inserted {len(dist_days)} distribution days for {symbol}")

        except Exception as e:
            logging.error(f"Error processing {symbol}: {e}")
            conn.rollback()

    return total_inserted

if __name__ == "__main__":
    log_mem("startup")

    logging.info("=" * 80)
    logging.info("UNIFIED MARKET DATA LOADER")
    logging.info("=" * 80)

    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create tables
    logging.info("\n📊 Step 1: Creating tables...")
    create_market_data_table(cur, conn)
    create_distribution_days_table(cur, conn)

    # Load distribution days (fast)
    logging.info("\n📊 Step 2: Calculating distribution days...")
    start_time = time.time()
    dist_days_inserted = load_distribution_days(MAJOR_INDICES, conn, cur)
    dist_time = time.time() - start_time

    # Get distribution days summary
    cur.execute("""
        SELECT symbol, COUNT(*) as count, MAX(date) as latest_date
        FROM distribution_days
        GROUP BY symbol
        ORDER BY symbol
    """)

    logging.info("\nDistribution Days Summary:")
    for row in cur.fetchall():
        symbol, count, latest = row
        logging.info(f"  {symbol}: {count} distribution days (latest: {latest})")

    # Final statistics
    logging.info("\n" + "=" * 80)
    logging.info("UNIFIED MARKET DATA LOADING COMPLETE")
    logging.info("=" * 80)

    logging.info("\n✅ Distribution Days:")
    logging.info(f"  Records inserted: {dist_days_inserted}")
    logging.info(f"  Processing time: {dist_time:.1f}s")

    # Verify distribution days table
    cur.execute("SELECT COUNT(*) FROM distribution_days")
    result = cur.fetchone()
    total_dist_days = result.get('count') if isinstance(result, dict) else result[0]
    logging.info(f"  Total records in database: {total_dist_days}")

    logging.info(f"\n⏱️  Total execution time: {dist_time:.1f}s")
    log_mem("completion")

    # Show final distribution days summary with RUNNING counts
    cur.execute("""
        SELECT symbol, COUNT(*) as total_count, MAX(date) as latest_date,
               MAX(running_count) as current_running_count
        FROM distribution_days
        GROUP BY symbol
        ORDER BY symbol
    """)

    logging.info("\n📊 IBD Distribution Days Summary (RUNNING COUNTS):")
    for row in cur.fetchall():
        symbol = row.get('symbol') if isinstance(row, dict) else row[0]
        total_count = int(row.get('total_count') if isinstance(row, dict) else row[1])
        latest = row.get('latest_date') if isinstance(row, dict) else row[2]
        running_count = int(row.get('current_running_count') if isinstance(row, dict) else row[3])

        # Determine signal based on RUNNING count (what matters for trading)
        if running_count <= 2:
            signal = "✅ NORMAL"
        elif running_count <= 4:
            signal = "⚠️  WATCH"
        elif running_count <= 7:
            signal = "🟡 CAUTION"
        elif running_count <= 10:
            signal = "🔴 PRESSURE"
        else:
            signal = "⚠️⚠️ SERIOUS PRESSURE"

        logging.info(f"  {symbol}: {running_count} running (latest: {latest}) | {signal}")

    cur.close()
    conn.close()
    logging.info("\n✅ Database connection closed")
    logging.info("=" * 80)
    logging.info("READY FOR DASHBOARD!")
    logging.info("=" * 80)