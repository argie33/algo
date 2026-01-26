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
from yfinance_helper import retry_with_backoff

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
        # Convert ticker format for yfinance (e.g., BRK.B → BRK-B)
        yf_symbol = symbol.replace('.', '-').replace('$', '-').upper()
        self.ticker = yf.Ticker(yf_symbol)
    
    def get_market_data(self, period: str = "1y") -> Optional[Dict]:
        """Get comprehensive market data for the symbol"""
        try:
            # Get historical data with retry logic
            @retry_with_backoff(max_retries=3, verbose=False)
            def fetch_history():
                return self.ticker.history(period=period)

            hist = fetch_history()
            if hist is None or hist.empty:
                logging.warning(f"No historical data for {self.symbol}")
                return None

            # Get basic info
            info = self.ticker.info
            
            # Calculate latest metrics
            latest_date = hist.index[-1]
            latest_price = hist['Close'].iloc[-1]
            latest_volume = hist['Volume'].iloc[-1] if 'Volume' in hist.columns else None  # No fake 0 default
            
            # Calculate returns - return None if insufficient data (no fake 0 defaults)
            returns_1d = (hist['Close'].iloc[-1] / hist['Close'].iloc[-2] - 1) if len(hist) >= 2 else None
            returns_5d = (hist['Close'].iloc[-1] / hist['Close'].iloc[-6] - 1) if len(hist) >= 6 else None
            returns_1m = (hist['Close'].iloc[-1] / hist['Close'].iloc[-21] - 1) if len(hist) >= 21 else None
            returns_3m = (hist['Close'].iloc[-1] / hist['Close'].iloc[-63] - 1) if len(hist) >= 63 else None
            returns_6m = (hist['Close'].iloc[-1] / hist['Close'].iloc[-126] - 1) if len(hist) >= 126 else None
            returns_1y = (hist['Close'].iloc[-1] / hist['Close'].iloc[0] - 1) if len(hist) >= 250 else None
            
            # Calculate volatility - return None if insufficient data (no fake 0 defaults)
            daily_returns = hist['Close'].pct_change().dropna()
            volatility_30d = daily_returns.tail(30).std() * np.sqrt(252) if len(daily_returns) >= 30 else None
            volatility_90d = daily_returns.tail(90).std() * np.sqrt(252) if len(daily_returns) >= 90 else None
            volatility_1y = daily_returns.std() * np.sqrt(252) if len(daily_returns) >= 30 else None
            
            # Calculate moving averages
            sma_20 = hist['Close'].rolling(20).mean().iloc[-1] if len(hist) >= 20 else latest_price
            sma_50 = hist['Close'].rolling(50).mean().iloc[-1] if len(hist) >= 50 else latest_price
            sma_200 = hist['Close'].rolling(200).mean().iloc[-1] if len(hist) >= 200 else latest_price
            
            # Calculate high/low metrics
            high_52w = hist['High'].tail(252).max() if len(hist) >= 252 else hist['High'].max()
            low_52w = hist['Low'].tail(252).min() if len(hist) >= 252 else hist['Low'].min()
            
            # Market cap and other info
            market_cap = info.get('marketCap')  # Return None if not available (no fake 0 default)
            # No fake 0 default for avg_volume - return None if insufficient data
            avg_volume_30d = hist['Volume'].tail(30).mean() if 'Volume' in hist.columns and len(hist) >= 30 else None
            
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
        # Create table with current schema matching collected data
        create_sql = """
        CREATE TABLE IF NOT EXISTS market_data (
            symbol VARCHAR(20) NOT NULL,
            name VARCHAR(255),
            date DATE NOT NULL,
            price NUMERIC,
            volume BIGINT,
            market_cap BIGINT,

            -- Returns
            return_1d NUMERIC,
            return_5d NUMERIC,
            return_1m NUMERIC,
            return_3m NUMERIC,
            return_6m NUMERIC,
            return_1y NUMERIC,

            -- Volatility
            volatility_30d NUMERIC,
            volatility_90d NUMERIC,
            volatility_1y NUMERIC,

            -- Moving averages
            sma_20 NUMERIC,
            sma_50 NUMERIC,
            sma_200 NUMERIC,
            price_vs_sma_20 NUMERIC,
            price_vs_sma_50 NUMERIC,
            price_vs_sma_200 NUMERIC,

            -- High/Low metrics
            high_52w NUMERIC,
            low_52w NUMERIC,
            distance_from_high NUMERIC,
            distance_from_low NUMERIC,

            -- Volume and risk
            avg_volume_30d BIGINT,
            volume_ratio NUMERIC,
            beta NUMERIC,

            -- Classification
            asset_class VARCHAR(50),
            region VARCHAR(50),

            -- Metadata
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (symbol, date)
        );
        """
        cur.execute(create_sql)
        conn.commit()
        logging.info("market_data table created with correct schema")
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

        # Add delay between batches to avoid rate limiting
        if i > 0:
            delay = 5  # 5 seconds between batches
            logging.info(f"⏳ Waiting {delay}s before next batch (rate limit avoidance)...")
            time.sleep(delay)

        logging.info(f"Processing market data batch {batch_num}/{total_batches}: {len(batch)} symbols")
        log_mem(f"Market batch {batch_num} start")
        
        # Process sequentially to avoid yfinance rate limiting (no parallel requests)
        market_data = []
        for idx, (symbol, name) in enumerate(batch):
            # Add delay between individual symbol requests to avoid rate limiting
            if idx > 0:
                time.sleep(2)  # 2 second delay between each symbol

            try:
                data = process_market_symbol(symbol, name)
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
    """Calculate distribution days using STRICT IBD methodology

    REAL IBD Distribution Day Definition (25-day lookback window):
    1. Index closes DOWN 0.2% or more (not just any down day)
    2. Volume > previous day's volume
    3. Only count distribution days in the last 25 TRADING DAYS
    4. Remove distribution day if price rises 5%+ from that day's close
    5. Running count resets on follow-through days (up 1-2% on heavy volume)

    References:
    - Only relevant for last 25 trading days
    - Can be removed if market rises 5%+ from the distribution day close
    - 4+ distribution days = weakness signal
    - 6-7+ distribution days = potential rollover
    """
    try:
        # Convert ticker format for yfinance (e.g., BRK.B → BRK-B)
        yf_symbol = symbol.replace('.', '-').replace('$', '-').upper()
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period=period)

        if hist.empty or len(hist) < 20:
            logging.warning(f"Insufficient data for {symbol}")
            return None

        # Calculate metrics
        hist['Change'] = hist['Close'].pct_change()
        hist['Prev_Volume'] = hist['Volume'].shift(1)
        hist['Volume_Higher'] = hist['Volume'] > hist['Prev_Volume']
        hist['Volume_Ratio'] = hist['Volume'] / hist['Prev_Volume']

        # Identify distribution days - STRICT IBD METHOD
        # Must meet ALL criteria:
        # 1. Down 0.2% or more (not just any down day)
        # 2. Volume > previous day
        dist_days = []

        for idx in range(1, len(hist)):
            row = hist.iloc[idx]
            prev_row = hist.iloc[idx - 1]

            # Use None as default for safe_float (no fake 0 defaults)
            row_change = safe_float(row['Change'], None)
            row_volume = safe_float(row['Volume'], None)
            prev_volume = safe_float(prev_row['Volume'], None)
            row_close = safe_float(row['Close'], None)

            # Skip if required data missing
            if row_change is None or row_volume is None or prev_volume is None or row_close is None:
                continue

            # STRICT IBD: Down 0.2% or MORE (not just any negative)
            is_distribution_down = row_change <= -0.002  # -0.2% or worse
            higher_volume = row_volume > prev_volume

            if is_distribution_down and higher_volume:
                # Check if this distribution day is still valid (price didn't rise 5%+ from it)
                # Look at all days AFTER this distribution day
                max_price_after = row_close
                for check_idx in range(idx + 1, len(hist)):
                    check_row = hist.iloc[check_idx]
                    check_close = safe_float(check_row['Close'], None)
                    if check_close is not None:
                        max_price_after = max(max_price_after, check_close)

                # If price rose 5%+ from distribution day close, it's removed
                price_recovery = (max_price_after - row_close) / row_close if row_close != 0 else 0

                if price_recovery < 0.05:  # Less than 5% recovery = distribution day still valid
                    dist_days.append({
                        'date': row.name.date(),
                        'close_price': row_close,
                        'change_pct': safe_float(row_change * 100),
                        'volume': int(row['Volume']) if row['Volume'] is not None and row['Volume'] > 0 else None,
                        'volume_ratio': safe_float(row['Volume_Ratio']),
                        'is_valid': price_recovery < 0.05  # Track if it meets the 5% rule
                    })

        # Find most recent follow-through day (up 1%+ on heavy volume)
        # This resets the distribution count
        most_recent_followthrough = None
        volume_sma = hist['Volume'].rolling(50).mean()

        for idx in range(len(hist) - 1, -1, -1):
            row = hist.iloc[idx]
            change = safe_float(row['Change'], None)
            volume = safe_float(row['Volume'], None)
            sma_vol = safe_float(volume_sma.iloc[idx], None)

            # Follow-through: up 1%+ on volume > 50-day SMA
            if change is not None and volume is not None and sma_vol is not None and change > 0.01 and volume > sma_vol:
                most_recent_followthrough = row.name.date()
                break

        # Get last 25 trading days from the data
        recent_hist = hist.tail(25)
        last_25_trading_dates = set(recent_hist.index.date)

        # Calculate 25-day count (correct IBD methodology)
        # Count all valid distribution days within the past 25 TRADING DAYS
        # Do NOT reset on follow-through - follow-through is a separate signal
        today = date.today()
        count_in_25days = 0

        for day_info in dist_days:
            day_info['days_ago'] = (today - day_info['date']).days

            # IMPORTANT: Only count distribution days within last 25 TRADING DAYS
            # IBD methodology: Show count of valid distribution days in rolling 25-day window
            if day_info['date'] in last_25_trading_dates:
                # Within 25-day window = count it
                count_in_25days += 1
                day_info['running_count'] = count_in_25days
            else:
                # Outside 25-day window = not counted
                day_info['running_count'] = 0

        # Sort to descending (newest first) for database insertion and API responses
        dist_days.sort(key=lambda x: x['date'], reverse=True)

        logging.info(f"Found {len(dist_days)} total distribution days for {symbol}")
        logging.info(f"  Within 25-day window: {count_in_25days} days")
        logging.info(f"  Last follow-through: {most_recent_followthrough or 'None'}")
        logging.info(f"  Note: Count shows valid distribution days in 25-day window (separate from follow-through signal)")

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

    # Load market data for indices and ETFs
    logging.info("\n📊 Step 2: Loading market data for indices and ETFs...")
    market_start = time.time()

    # Combine all symbols to load
    all_market_symbols = {**MARKET_INDICES, **SECTOR_ETFS, **STYLE_ETFS}
    logging.info(f"   Loading {len(all_market_symbols)} symbols: {list(all_market_symbols.keys())[:10]}...")

    market_processed, market_inserted = load_market_data_batch(all_market_symbols, conn, cur, batch_size=10)
    market_time = time.time() - market_start
    logging.info(f"   Market data: {market_processed} processed, {market_inserted} inserted ({market_time:.1f}s)")

    # Load distribution days (fast)
    logging.info("\n📊 Step 3: Calculating distribution days...")
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

    logging.info("\n✅ Market Data:")
    logging.info(f"  Symbols processed: {market_processed}")
    logging.info(f"  Records inserted: {market_inserted}")
    logging.info(f"  Processing time: {market_time:.1f}s")

    # Verify market data table
    cur.execute("SELECT COUNT(*) FROM market_data")
    result = cur.fetchone()
    total_market = result.get('count') if isinstance(result, dict) else result[0]
    logging.info(f"  Total records in database: {total_market}")

    logging.info("\n✅ Distribution Days:")
    logging.info(f"  Records inserted: {dist_days_inserted}")
    logging.info(f"  Processing time: {dist_time:.1f}s")

    # Verify distribution days table
    cur.execute("SELECT COUNT(*) FROM distribution_days")
    result = cur.fetchone()
    total_dist_days = result.get('count') if isinstance(result, dict) else result[0]
    logging.info(f"  Total records in database: {total_dist_days}")

    logging.info(f"\n⏱️  Total execution time: {market_time + dist_time:.1f}s (market: {market_time:.1f}s + distribution: {dist_time:.1f}s)")
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