#!/usr/bin/env python3
"""
Technical Indicators Loader Script

This script loads comprehensive technical analysis indicators including:
- Moving averages (SMA, EMA, VWAP)
- Momentum indicators (RSI, MACD, Stochastic)
- Volatility indicators (Bollinger Bands, ATR)
- Volume indicators (OBV, Volume Profile)
- Trend indicators (ADX, Parabolic SAR)

Data Sources:
- Primary: yfinance for OHLCV data
- Calculated: Technical indicators using TA-Lib and custom algorithms
- Enhanced: Multi-timeframe analysis and signal generation

Author: Financial Dashboard System
"""

import sys
import time
import logging
import json
import os
import gc
import resource
import math
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

# Technical analysis imports
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    logging.warning("TA-Lib not available - using custom implementations")

# Script configuration
SCRIPT_NAME = "loadtechnicals.py"
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

class TechnicalIndicatorCalculator:
    """Calculate comprehensive technical indicators"""
    
    def __init__(self, symbol: str, price_data: pd.DataFrame):
        self.symbol = symbol
        self.data = price_data.copy()
        
        # Ensure required columns exist
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in required_cols:
            if col not in self.data.columns:
                logging.error(f"Missing required column {col} for {symbol}")
                self.data = pd.DataFrame()
                return
        
        # Sort by date and ensure numeric types
        self.data = self.data.sort_index()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            self.data[col] = pd.to_numeric(self.data[col], errors='coerce')
    
    def calculate_moving_averages(self) -> Dict:
        """Calculate various moving averages"""
        if self.data.empty:
            return {}
        
        close = self.data['Close']
        volume = self.data['Volume']
        high = self.data['High']
        low = self.data['Low']
        
        indicators = {}
        
        # Simple Moving Averages
        for period in [5, 10, 20, 50, 100, 200]:
            if len(close) >= period:
                sma = close.rolling(window=period).mean()
                indicators[f'sma_{period}'] = safe_float(sma.iloc[-1])
                
                # Price relative to SMA
                if indicators[f'sma_{period}']:
                    indicators[f'price_vs_sma_{period}'] = (close.iloc[-1] - indicators[f'sma_{period}']) / indicators[f'sma_{period}']
        
        # Exponential Moving Averages
        for period in [12, 26, 50]:
            if len(close) >= period:
                ema = close.ewm(span=period).mean()
                indicators[f'ema_{period}'] = safe_float(ema.iloc[-1])
        
        # Volume Weighted Average Price (VWAP)
        if len(close) >= 20:
            typical_price = (high + low + close) / 3
            cumulative_tp_volume = (typical_price * volume).cumsum()
            cumulative_volume = volume.cumsum()
            vwap = cumulative_tp_volume / cumulative_volume
            indicators['vwap'] = safe_float(vwap.iloc[-1])
            
            if indicators['vwap']:
                indicators['price_vs_vwap'] = (close.iloc[-1] - indicators['vwap']) / indicators['vwap']
        
        return indicators
    
    def calculate_momentum_indicators(self) -> Dict:
        """Calculate momentum indicators"""
        if self.data.empty:
            return {}
        
        close = self.data['Close']
        high = self.data['High']
        low = self.data['Low']
        
        indicators = {}
        
        # RSI (Relative Strength Index)
        if len(close) >= 15:
            if TALIB_AVAILABLE:
                rsi = talib.RSI(close.values, timeperiod=14)
                indicators['rsi_14'] = safe_float(rsi[-1])
            else:
                # Custom RSI calculation
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                indicators['rsi_14'] = safe_float(rsi.iloc[-1])
        
        # MACD (Moving Average Convergence Divergence)
        if len(close) >= 35:
            if TALIB_AVAILABLE:
                macd, macd_signal, macd_hist = talib.MACD(close.values)
                indicators['macd'] = safe_float(macd[-1])
                indicators['macd_signal'] = safe_float(macd_signal[-1])
                indicators['macd_histogram'] = safe_float(macd_hist[-1])
            else:
                # Custom MACD calculation
                ema_12 = close.ewm(span=12).mean()
                ema_26 = close.ewm(span=26).mean()
                macd_line = ema_12 - ema_26
                signal_line = macd_line.ewm(span=9).mean()
                histogram = macd_line - signal_line
                
                indicators['macd'] = safe_float(macd_line.iloc[-1])
                indicators['macd_signal'] = safe_float(signal_line.iloc[-1])
                indicators['macd_histogram'] = safe_float(histogram.iloc[-1])
        
        # Stochastic Oscillator
        if len(close) >= 14:
            if TALIB_AVAILABLE:
                slowk, slowd = talib.STOCH(high.values, low.values, close.values)
                indicators['stoch_k'] = safe_float(slowk[-1])
                indicators['stoch_d'] = safe_float(slowd[-1])
            else:
                # Custom Stochastic calculation
                lowest_low = low.rolling(window=14).min()
                highest_high = high.rolling(window=14).max()
                k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))
                d_percent = k_percent.rolling(window=3).mean()
                
                indicators['stoch_k'] = safe_float(k_percent.iloc[-1])
                indicators['stoch_d'] = safe_float(d_percent.iloc[-1])
        
        # Williams %R
        if len(close) >= 14:
            if TALIB_AVAILABLE:
                willr = talib.WILLR(high.values, low.values, close.values, timeperiod=14)
                indicators['williams_r'] = safe_float(willr[-1])
            else:
                # Custom Williams %R calculation
                highest_high = high.rolling(window=14).max()
                lowest_low = low.rolling(window=14).min()
                williams_r = -100 * ((highest_high - close) / (highest_high - lowest_low))
                indicators['williams_r'] = safe_float(williams_r.iloc[-1])
        
        return indicators
    
    def calculate_volatility_indicators(self) -> Dict:
        """Calculate volatility indicators"""
        if self.data.empty:
            return {}
        
        close = self.data['Close']
        high = self.data['High']
        low = self.data['Low']
        
        indicators = {}
        
        # Bollinger Bands
        if len(close) >= 20:
            if TALIB_AVAILABLE:
                bb_upper, bb_middle, bb_lower = talib.BBANDS(close.values, timeperiod=20)
                indicators['bb_upper'] = safe_float(bb_upper[-1])
                indicators['bb_middle'] = safe_float(bb_middle[-1])
                indicators['bb_lower'] = safe_float(bb_lower[-1])
            else:
                # Custom Bollinger Bands calculation
                sma_20 = close.rolling(window=20).mean()
                std_20 = close.rolling(window=20).std()
                bb_upper = sma_20 + (std_20 * 2)
                bb_lower = sma_20 - (std_20 * 2)
                
                indicators['bb_upper'] = safe_float(bb_upper.iloc[-1])
                indicators['bb_middle'] = safe_float(sma_20.iloc[-1])
                indicators['bb_lower'] = safe_float(bb_lower.iloc[-1])
            
            # Bollinger Band position and width
            if all(indicators.get(k) for k in ['bb_upper', 'bb_lower']):
                bb_position = (close.iloc[-1] - indicators['bb_lower']) / (indicators['bb_upper'] - indicators['bb_lower'])
                bb_width = (indicators['bb_upper'] - indicators['bb_lower']) / indicators['bb_middle']
                indicators['bb_position'] = safe_float(bb_position)
                indicators['bb_width'] = safe_float(bb_width)
        
        # Average True Range (ATR)
        if len(close) >= 14:
            if TALIB_AVAILABLE:
                atr = talib.ATR(high.values, low.values, close.values, timeperiod=14)
                indicators['atr_14'] = safe_float(atr[-1])
            else:
                # Custom ATR calculation
                tr1 = high - low
                tr2 = abs(high - close.shift())
                tr3 = abs(low - close.shift())
                true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                atr = true_range.rolling(window=14).mean()
                indicators['atr_14'] = safe_float(atr.iloc[-1])
            
            # ATR percentage
            if indicators['atr_14']:
                indicators['atr_percent'] = indicators['atr_14'] / close.iloc[-1]
        
        # Historical Volatility (20-day)
        if len(close) >= 21:
            returns = close.pct_change().dropna()
            if len(returns) >= 20:
                volatility = returns.rolling(window=20).std() * math.sqrt(252)  # Annualized
                indicators['historical_volatility_20d'] = safe_float(volatility.iloc[-1])
        
        return indicators
    
    def calculate_volume_indicators(self) -> Dict:
        """Calculate volume indicators"""
        if self.data.empty:
            return {}
        
        close = self.data['Close']
        volume = self.data['Volume']
        high = self.data['High']
        low = self.data['Low']
        
        indicators = {}
        
        # On-Balance Volume (OBV)
        if len(close) >= 2:
            if TALIB_AVAILABLE:
                obv = talib.OBV(close.values, volume.values)
                indicators['obv'] = safe_float(obv[-1])
            else:
                # Custom OBV calculation
                obv = volume.copy()
                for i in range(1, len(close)):
                    if close.iloc[i] > close.iloc[i-1]:
                        obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
                    elif close.iloc[i] < close.iloc[i-1]:
                        obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
                    else:
                        obv.iloc[i] = obv.iloc[i-1]
                indicators['obv'] = safe_float(obv.iloc[-1])
        
        # Volume Moving Average
        if len(volume) >= 20:
            volume_ma = volume.rolling(window=20).mean()
            indicators['volume_ma_20'] = safe_float(volume_ma.iloc[-1])
            
            # Current volume vs average
            if indicators['volume_ma_20']:
                indicators['volume_ratio'] = volume.iloc[-1] / indicators['volume_ma_20']
        
        # Money Flow Index (MFI)
        if len(close) >= 14:
            if TALIB_AVAILABLE:
                mfi = talib.MFI(high.values, low.values, close.values, volume.values, timeperiod=14)
                indicators['mfi_14'] = safe_float(mfi[-1])
            else:
                # Custom MFI calculation
                typical_price = (high + low + close) / 3
                money_flow = typical_price * volume
                
                positive_flow = money_flow.where(typical_price > typical_price.shift(), 0).rolling(14).sum()
                negative_flow = money_flow.where(typical_price < typical_price.shift(), 0).rolling(14).sum()
                
                money_ratio = positive_flow / negative_flow
                mfi = 100 - (100 / (1 + money_ratio))
                indicators['mfi_14'] = safe_float(mfi.iloc[-1])
        
        return indicators
    
    def calculate_trend_indicators(self) -> Dict:
        """Calculate trend indicators"""
        if self.data.empty:
            return {}
        
        close = self.data['Close']
        high = self.data['High']
        low = self.data['Low']
        
        indicators = {}
        
        # Average Directional Index (ADX)
        if len(close) >= 28:
            if TALIB_AVAILABLE:
                adx = talib.ADX(high.values, low.values, close.values, timeperiod=14)
                indicators['adx_14'] = safe_float(adx[-1])
                
                plus_di = talib.PLUS_DI(high.values, low.values, close.values, timeperiod=14)
                minus_di = talib.MINUS_DI(high.values, low.values, close.values, timeperiod=14)
                indicators['plus_di'] = safe_float(plus_di[-1])
                indicators['minus_di'] = safe_float(minus_di[-1])
        
        # Parabolic SAR
        if len(close) >= 10:
            if TALIB_AVAILABLE:
                sar = talib.SAR(high.values, low.values)
                indicators['parabolic_sar'] = safe_float(sar[-1])
                
                # SAR signal
                indicators['sar_signal'] = 1 if close.iloc[-1] > indicators['parabolic_sar'] else -1
        
        # Commodity Channel Index (CCI)
        if len(close) >= 20:
            if TALIB_AVAILABLE:
                cci = talib.CCI(high.values, low.values, close.values, timeperiod=20)
                indicators['cci_20'] = safe_float(cci[-1])
            else:
                # Custom CCI calculation
                typical_price = (high + low + close) / 3
                sma = typical_price.rolling(window=20).mean()
                mean_deviation = typical_price.rolling(window=20).apply(lambda x: np.mean(np.abs(x - x.mean())))
                cci = (typical_price - sma) / (0.015 * mean_deviation)
                indicators['cci_20'] = safe_float(cci.iloc[-1])
        
        return indicators
    
    def get_latest_technical_indicators(self) -> Dict:
        """Get all technical indicators for the latest date"""
        if self.data.empty:
            return None
        
        result = {
            'symbol': self.symbol,
            'date': self.data.index[-1].date() if hasattr(self.data.index[-1], 'date') else date.today(),
            'price': safe_float(self.data['Close'].iloc[-1]),
            'volume': safe_float(self.data['Volume'].iloc[-1])
        }
        
        # Calculate all indicator categories
        result.update(self.calculate_moving_averages())
        result.update(self.calculate_momentum_indicators())
        result.update(self.calculate_volatility_indicators())
        result.update(self.calculate_volume_indicators())
        result.update(self.calculate_trend_indicators())
        
        return result

def get_price_data(symbol: str, period: str = "1y") -> Optional[pd.DataFrame]:
    """Get price data for technical analysis"""
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period)
        
        if data.empty:
            logging.warning(f"No price data found for {symbol}")
            return None
        
        # Ensure we have enough data for calculations
        if len(data) < 30:
            logging.warning(f"Insufficient data for {symbol}: only {len(data)} days")
            return None
        
        return data
        
    except Exception as e:
        logging.error(f"Error fetching price data for {symbol}: {e}")
        return None

def process_symbol_technicals(symbol: str) -> Optional[Dict]:
    """Process technical indicators for a symbol"""
    try:
        # Get price data
        price_data = get_price_data(symbol)
        if price_data is None:
            return None
        
        # Calculate technical indicators
        calculator = TechnicalIndicatorCalculator(symbol, price_data)
        indicators = calculator.get_latest_technical_indicators()
        
        if indicators is None:
            logging.warning(f"Failed to calculate indicators for {symbol}")
            return None
        
        return indicators
        
    except Exception as e:
        logging.error(f"Error processing technicals for {symbol}: {e}")
        return None

def create_technical_indicators_table(cur, conn):
    """Create technical indicators table"""
    logging.info("Creating technical_indicators table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS technical_indicators (
        symbol VARCHAR(20),
        date DATE,
        price DECIMAL(12,4),
        volume BIGINT,
        
        -- Moving Averages
        sma_5 DECIMAL(12,4),
        sma_10 DECIMAL(12,4),
        sma_20 DECIMAL(12,4),
        sma_50 DECIMAL(12,4),
        sma_100 DECIMAL(12,4),
        sma_200 DECIMAL(12,4),
        ema_12 DECIMAL(12,4),
        ema_26 DECIMAL(12,4),
        ema_50 DECIMAL(12,4),
        vwap DECIMAL(12,4),
        
        -- Price vs Moving Averages
        price_vs_sma_20 DECIMAL(8,4),
        price_vs_sma_50 DECIMAL(8,4),
        price_vs_sma_200 DECIMAL(8,4),
        price_vs_vwap DECIMAL(8,4),
        
        -- Momentum Indicators
        rsi_14 DECIMAL(6,2),
        macd DECIMAL(12,4),
        macd_signal DECIMAL(12,4),
        macd_histogram DECIMAL(12,4),
        stoch_k DECIMAL(6,2),
        stoch_d DECIMAL(6,2),
        williams_r DECIMAL(6,2),
        
        -- Volatility Indicators
        bb_upper DECIMAL(12,4),
        bb_middle DECIMAL(12,4),
        bb_lower DECIMAL(12,4),
        bb_position DECIMAL(6,4),
        bb_width DECIMAL(6,4),
        atr_14 DECIMAL(12,4),
        atr_percent DECIMAL(6,4),
        historical_volatility_20d DECIMAL(6,4),
        
        -- Volume Indicators
        obv BIGINT,
        volume_ma_20 BIGINT,
        volume_ratio DECIMAL(6,2),
        mfi_14 DECIMAL(6,2),
        
        -- Trend Indicators
        adx_14 DECIMAL(6,2),
        plus_di DECIMAL(6,2),
        minus_di DECIMAL(6,2),
        parabolic_sar DECIMAL(12,4),
        sar_signal INTEGER,
        cci_20 DECIMAL(8,2),
        
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """
    
    cur.execute(create_sql)
    
    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_technical_symbol ON technical_indicators(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_technical_date ON technical_indicators(date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_technical_rsi ON technical_indicators(rsi_14);",
        "CREATE INDEX IF NOT EXISTS idx_technical_macd ON technical_indicators(macd_histogram);",
        "CREATE INDEX IF NOT EXISTS idx_technical_bb_position ON technical_indicators(bb_position);",
        "CREATE INDEX IF NOT EXISTS idx_technical_volume_ratio ON technical_indicators(volume_ratio DESC);",
        "CREATE INDEX IF NOT EXISTS idx_technical_adx ON technical_indicators(adx_14 DESC);",
        "CREATE INDEX IF NOT EXISTS idx_technical_sma_position ON technical_indicators(price_vs_sma_20);"
    ]
    
    for index_sql in indexes:
        cur.execute(index_sql)
    
    conn.commit()
    logging.info("Technical indicators table created successfully")

def load_technicals_batch(symbols: List[str], conn, cur, batch_size: int = 5) -> Tuple[int, int]:
    """Load technical indicators in batches"""
    total_processed = 0
    total_inserted = 0
    failed_symbols = []
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size
        
        logging.info(f"Processing technicals batch {batch_num}/{total_batches}: {len(batch)} symbols")
        log_mem(f"Technicals batch {batch_num} start")
        
        # Process sequentially to avoid API limits
        technical_data = []
        for symbol in batch:
            try:
                data = process_symbol_technicals(symbol)
                if data:
                    technical_data.append(data)
                else:
                    failed_symbols.append(symbol)
                total_processed += 1
                
                # Delay between symbols
                time.sleep(0.5)
                
            except Exception as e:
                failed_symbols.append(symbol)
                logging.error(f"Exception processing technicals for {symbol}: {e}")
                total_processed += 1
        
        # Insert to database
        if technical_data:
            try:
                insert_data = []
                for item in technical_data:
                    insert_data.append((
                        item['symbol'], item['date'], item.get('price'), item.get('volume'),
                        
                        # Moving averages
                        item.get('sma_5'), item.get('sma_10'), item.get('sma_20'),
                        item.get('sma_50'), item.get('sma_100'), item.get('sma_200'),
                        item.get('ema_12'), item.get('ema_26'), item.get('ema_50'),
                        item.get('vwap'),
                        
                        # Price vs MAs
                        item.get('price_vs_sma_20'), item.get('price_vs_sma_50'),
                        item.get('price_vs_sma_200'), item.get('price_vs_vwap'),
                        
                        # Momentum
                        item.get('rsi_14'), item.get('macd'), item.get('macd_signal'),
                        item.get('macd_histogram'), item.get('stoch_k'), item.get('stoch_d'),
                        item.get('williams_r'),
                        
                        # Volatility
                        item.get('bb_upper'), item.get('bb_middle'), item.get('bb_lower'),
                        item.get('bb_position'), item.get('bb_width'), item.get('atr_14'),
                        item.get('atr_percent'), item.get('historical_volatility_20d'),
                        
                        # Volume
                        item.get('obv'), item.get('volume_ma_20'), item.get('volume_ratio'),
                        item.get('mfi_14'),
                        
                        # Trend
                        item.get('adx_14'), item.get('plus_di'), item.get('minus_di'),
                        item.get('parabolic_sar'), item.get('sar_signal'), item.get('cci_20')
                    ))
                
                insert_query = """
                    INSERT INTO technical_indicators (
                        symbol, date, price, volume,
                        sma_5, sma_10, sma_20, sma_50, sma_100, sma_200,
                        ema_12, ema_26, ema_50, vwap,
                        price_vs_sma_20, price_vs_sma_50, price_vs_sma_200, price_vs_vwap,
                        rsi_14, macd, macd_signal, macd_histogram, stoch_k, stoch_d, williams_r,
                        bb_upper, bb_middle, bb_lower, bb_position, bb_width, atr_14,
                        atr_percent, historical_volatility_20d,
                        obv, volume_ma_20, volume_ratio, mfi_14,
                        adx_14, plus_di, minus_di, parabolic_sar, sar_signal, cci_20
                    ) VALUES %s
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        price = EXCLUDED.price,
                        volume = EXCLUDED.volume,
                        rsi_14 = EXCLUDED.rsi_14,
                        macd_histogram = EXCLUDED.macd_histogram,
                        bb_position = EXCLUDED.bb_position,
                        volume_ratio = EXCLUDED.volume_ratio,
                        adx_14 = EXCLUDED.adx_14,
                        updated_at = CURRENT_TIMESTAMP
                """
                
                execute_values(cur, insert_query, insert_data)
                conn.commit()
                total_inserted += len(technical_data)
                logging.info(f"Technicals batch {batch_num} inserted {len(technical_data)} symbols successfully")
                
            except Exception as e:
                logging.error(f"Database insert error for technicals batch {batch_num}: {e}")
                conn.rollback()
        
        # Cleanup
        del technical_data
        gc.collect()
        log_mem(f"Technicals batch {batch_num} end")
        time.sleep(2)
    
    if failed_symbols:
        logging.warning(f"Failed to process technical indicators for {len(failed_symbols)} symbols: {failed_symbols[:5]}...")
    
    return total_processed, total_inserted

if __name__ == "__main__":
    log_mem("startup")
    
    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Create table
    create_technical_indicators_table(cur, conn)
    
    # Get symbols to process
    cur.execute("""
        SELECT symbol FROM stock_symbols_enhanced 
        WHERE is_active = TRUE 
        AND market_cap > 500000000  -- Only stocks with >$500M market cap
        ORDER BY market_cap DESC 
        LIMIT 150
    """)
    symbols = [row['symbol'] for row in cur.fetchall()]
    
    if not symbols:
        logging.warning("No symbols found in stock_symbols_enhanced table. Run loadsymbols.py first.")
        sys.exit(1)
    
    logging.info(f"Loading technical indicators for {len(symbols)} symbols")
    
    # Load technical indicators
    start_time = time.time()
    processed, inserted = load_technicals_batch(symbols, conn, cur)
    end_time = time.time()
    
    # Final statistics
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM technical_indicators")
    total_symbols = cur.fetchone()[0]
    
    logging.info("=" * 60)
    logging.info("TECHNICAL INDICATORS LOADING COMPLETE")
    logging.info("=" * 60)
    logging.info(f"Symbols processed: {processed}")
    logging.info(f"Symbols with technical data: {inserted}")
    logging.info(f"Total symbols in technical_indicators table: {total_symbols}")
    logging.info(f"Processing time: {(end_time - start_time):.1f} seconds")
    log_mem("completion")
    
    # Sample results
    cur.execute("""
        SELECT t.symbol, se.company_name,
               t.price, t.rsi_14, t.macd_histogram, t.bb_position,
               t.volume_ratio, t.adx_14, t.price_vs_sma_20
        FROM technical_indicators t
        JOIN stock_symbols_enhanced se ON t.symbol = se.symbol
        WHERE t.rsi_14 IS NOT NULL
        AND t.date = (SELECT MAX(date) FROM technical_indicators WHERE symbol = t.symbol)
        ORDER BY t.adx_14 DESC NULLS LAST
        LIMIT 10
    """)
    
    logging.info("\nTop 10 Stocks by Trend Strength (ADX):")
    for row in cur.fetchall():
        logging.info(f"  {row['symbol']} ({row['company_name'][:25]}): "
                    f"ADX={row['adx_14']:.1f}, RSI={row['rsi_14']:.1f}, "
                    f"MACD Hist={row['macd_histogram']:.3f}, BB Pos={row['bb_position']:.2f}, "
                    f"Vol Ratio={row['volume_ratio']:.1f}, SMA20={row['price_vs_sma_20']:.1%}")
    
    cur.close()
    conn.close()
    logging.info("Database connection closed")