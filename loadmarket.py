#!/usr/bin/env python3
"""
Market Data Loader Script - Database diagnostic phase - v11 - SSL fix deployment with market data

This script loads comprehensive market data including:
- Major market indices (S&P 500, NASDAQ, Dow Jones, etc.)
- Sector ETFs and performance tracking
- Market breadth indicators
- Economic indicators and market sentiment
- International market indices

Data Sources:
- Primary: yfinance for index and ETF data
- Secondary: FRED API for economic indicators
- Calculated: Market breadth and momentum indicators

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

# Economic data imports
try:
    import yfinance as yf
    import requests
    EXTERNAL_DATA_AVAILABLE = True
except ImportError:
    EXTERNAL_DATA_AVAILABLE = False
    logging.warning("External data libraries not available")

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
    """Create market data table"""
    logging.info("Creating market_data table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS market_data (
        symbol VARCHAR(20),
        name VARCHAR(255),
        date DATE,
        price DECIMAL(12,4),
        volume BIGINT,
        market_cap BIGINT,
        
        -- Returns
        return_1d DECIMAL(8,6),
        return_5d DECIMAL(8,6),
        return_1m DECIMAL(8,6),
        return_3m DECIMAL(8,6),
        return_6m DECIMAL(8,6),
        return_1y DECIMAL(8,6),
        
        -- Volatility
        volatility_30d DECIMAL(8,6),
        volatility_90d DECIMAL(8,6),
        volatility_1y DECIMAL(8,6),
        
        -- Moving Averages
        sma_20 DECIMAL(12,4),
        sma_50 DECIMAL(12,4),
        sma_200 DECIMAL(12,4),
        price_vs_sma_20 DECIMAL(8,6),
        price_vs_sma_50 DECIMAL(8,6),
        price_vs_sma_200 DECIMAL(8,6),
        
        -- High/Low Metrics
        high_52w DECIMAL(12,4),
        low_52w DECIMAL(12,4),
        distance_from_high DECIMAL(8,6),
        distance_from_low DECIMAL(8,6),
        
        -- Volume and Risk
        avg_volume_30d BIGINT,
        volume_ratio DECIMAL(8,4),
        beta DECIMAL(8,4),
        
        -- Classification
        asset_class VARCHAR(50),
        region VARCHAR(50),
        
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """
    
    cur.execute(create_sql)
    
    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_market_symbol ON market_data(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_market_date ON market_data(date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_market_asset_class ON market_data(asset_class);",
        "CREATE INDEX IF NOT EXISTS idx_market_region ON market_data(region);",
        "CREATE INDEX IF NOT EXISTS idx_market_return_1d ON market_data(return_1d DESC);",
        "CREATE INDEX IF NOT EXISTS idx_market_return_1m ON market_data(return_1m DESC);",
        "CREATE INDEX IF NOT EXISTS idx_market_volatility ON market_data(volatility_30d DESC);",
        "CREATE INDEX IF NOT EXISTS idx_market_volume_ratio ON market_data(volume_ratio DESC);"
    ]
    
    for index_sql in indexes:
        cur.execute(index_sql)
    
    conn.commit()
    logging.info("Market data table created successfully")

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

if __name__ == "__main__":
    log_mem("startup")
    
    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    ,
            sslmode="require"
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Create table
    create_market_data_table(cur, conn)
    
    # Combine all market symbols
    all_market_symbols = {**MARKET_INDICES, **SECTOR_ETFS, **STYLE_ETFS}
    
    logging.info(f"Loading market data for {len(all_market_symbols)} symbols")
    
    # Load market data
    start_time = time.time()
    processed, inserted = load_market_data_batch(all_market_symbols, conn, cur)
    end_time = time.time()
    
    # Final statistics
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM market_data")
    total_symbols = cur.fetchone()[0]
    
    logging.info("=" * 60)
    logging.info("MARKET DATA LOADING COMPLETE")
    logging.info("=" * 60)
    logging.info(f"Symbols processed: {processed}")
    logging.info(f"Symbols with market data: {inserted}")
    logging.info(f"Total symbols in market_data table: {total_symbols}")
    logging.info(f"Processing time: {(end_time - start_time):.1f} seconds")
    log_mem("completion")
    
    # Sample results by asset class
    cur.execute("""
        SELECT asset_class, COUNT(*) as count,
               AVG(return_1d) as avg_1d_return,
               AVG(return_1m) as avg_1m_return,
               AVG(volatility_30d) as avg_volatility
        FROM market_data
        WHERE date = (SELECT MAX(date) FROM market_data)
        GROUP BY asset_class
        ORDER BY count DESC
    """)
    
    logging.info("\nMarket Data by Asset Class:")
    for row in cur.fetchall():
        logging.info(f"  {row['asset_class']}: {row['count']} symbols, "
                    f"1D Return={row['avg_1d_return']:.2%}, "
                    f"1M Return={row['avg_1m_return']:.2%}, "
                    f"Volatility={row['avg_volatility']:.2%}")
    
    # Top performers
    cur.execute("""
        SELECT symbol, name, return_1d, return_1m, volatility_30d
        FROM market_data
        WHERE date = (SELECT MAX(date) FROM market_data)
        AND asset_class IN ('sector_etf', 'broad_market_etf')
        ORDER BY return_1m DESC
        LIMIT 5
    """)
    
    logging.info("\nTop 5 Performing ETFs (1 Month):")
    for row in cur.fetchall():
        logging.info(f"  {row['symbol']} ({row['name'][:30]}): "
                    f"1M={row['return_1m']:.2%}, Vol={row['volatility_30d']:.2%}")
    
    cur.close()
    conn.close()
    logging.info("Database connection closed")