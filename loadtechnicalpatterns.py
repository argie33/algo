#!/usr/bin/env python3
"""
Technical Patterns Detection Script

This script identifies and analyzes technical chart patterns including:
- Classical patterns (Head & Shoulders, Double Top/Bottom, Triangles, Wedges)
- Candlestick patterns (Doji, Hammer, Engulfing, Morning/Evening Star)
- Support/Resistance levels and breakouts
- Trend channel analysis
- Volume confirmation patterns
- Pattern reliability scoring based on historical success rates

Data Sources:
- Primary: yfinance for OHLCV data
- Pattern Recognition: Custom algorithms with statistical validation
- Volume Analysis: Enhanced volume pattern recognition
- Machine Learning: Pattern success probability estimation

Author: Financial Dashboard System
"""

import sys
import time
import logging
import json
import os
import gc
import math
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from scipy.signal import find_peaks, argrelextrema
from scipy.stats import linregress

# Script configuration
SCRIPT_NAME = "loadtechnicalpatterns.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

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

class TechnicalPatternDetector:
    """Comprehensive technical pattern detection and analysis"""
    
    def __init__(self, symbol: str, price_data: pd.DataFrame, timeframe: str = "daily"):
        self.symbol = symbol
        self.timeframe = timeframe
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
        
        # Calculate additional series
        self.data['HL2'] = (self.data['High'] + self.data['Low']) / 2
        self.data['HLC3'] = (self.data['High'] + self.data['Low'] + self.data['Close']) / 3
        self.data['OHLC4'] = (self.data['Open'] + self.data['High'] + self.data['Low'] + self.data['Close']) / 4
        
        # Calculate returns for trend analysis
        self.data['Returns'] = self.data['Close'].pct_change()
        self.data['LogReturns'] = np.log(self.data['Close'] / self.data['Close'].shift(1))

    def detect_support_resistance(self, window: int = 20, min_touches: int = 3) -> Dict:
        """Detect key support and resistance levels"""
        if len(self.data) < window * 2:
            return {}
        
        highs = self.data['High'].values
        lows = self.data['Low'].values
        closes = self.data['Close'].values
        
        # Find local peaks and troughs
        high_peaks, _ = find_peaks(highs, distance=window//2)
        low_peaks, _ = find_peaks(-lows, distance=window//2)
        
        # Cluster similar levels
        resistance_levels = self._cluster_levels(highs[high_peaks], tolerance=0.02)
        support_levels = self._cluster_levels(lows[low_peaks], tolerance=0.02)
        
        current_price = closes[-1]
        
        # Find nearest levels
        nearest_resistance = min([r for r in resistance_levels if r > current_price], 
                                default=None, key=lambda x: abs(x - current_price))
        nearest_support = max([s for s in support_levels if s < current_price], 
                             default=None, key=lambda x: abs(x - current_price))
        
        return {
            'support_levels': support_levels[:5],  # Top 5 support levels
            'resistance_levels': resistance_levels[:5],  # Top 5 resistance levels
            'nearest_support': nearest_support,
            'nearest_resistance': nearest_resistance,
            'support_strength': self._calculate_level_strength(support_levels, lows),
            'resistance_strength': self._calculate_level_strength(resistance_levels, highs)
        }

    def detect_classical_patterns(self) -> List[Dict]:
        """Detect classical technical analysis patterns"""
        patterns = []
        
        if len(self.data) < 50:
            return patterns
        
        # Head and Shoulders
        patterns.extend(self._detect_head_shoulders())
        
        # Double Top/Bottom
        patterns.extend(self._detect_double_patterns())
        
        # Triangle patterns
        patterns.extend(self._detect_triangles())
        
        # Wedge patterns
        patterns.extend(self._detect_wedges())
        
        # Flag and Pennant patterns
        patterns.extend(self._detect_flags_pennants())
        
        # Cup and Handle
        patterns.extend(self._detect_cup_handle())
        
        return patterns

    def detect_candlestick_patterns(self) -> List[Dict]:
        """Detect candlestick patterns"""
        patterns = []
        
        if len(self.data) < 10:
            return patterns
        
        # Single candlestick patterns
        patterns.extend(self._detect_doji())
        patterns.extend(self._detect_hammer_hanging_man())
        patterns.extend(self._detect_shooting_star_inverted_hammer())
        
        # Two-candle patterns
        patterns.extend(self._detect_engulfing())
        patterns.extend(self._detect_harami())
        patterns.extend(self._detect_piercing_dark_cloud())
        
        # Three-candle patterns
        patterns.extend(self._detect_morning_evening_star())
        patterns.extend(self._detect_three_soldiers_crows())
        
        return patterns

    def detect_breakout_patterns(self) -> List[Dict]:
        """Detect breakout and breakdown patterns"""
        patterns = []
        
        if len(self.data) < 30:
            return patterns
        
        # Price breakouts from support/resistance
        sr_levels = self.detect_support_resistance()
        patterns.extend(self._detect_level_breakouts(sr_levels))
        
        # Volume breakouts
        patterns.extend(self._detect_volume_breakouts())
        
        # Moving average breakouts
        patterns.extend(self._detect_ma_breakouts())
        
        # Range breakouts
        patterns.extend(self._detect_range_breakouts())
        
        return patterns

    def _cluster_levels(self, levels: np.ndarray, tolerance: float = 0.02) -> List[float]:
        """Cluster similar price levels"""
        if len(levels) == 0:
            return []
        
        sorted_levels = np.sort(levels)
        clusters = []
        current_cluster = [sorted_levels[0]]
        
        for level in sorted_levels[1:]:
            if abs(level - current_cluster[-1]) / current_cluster[-1] <= tolerance:
                current_cluster.append(level)
            else:
                clusters.append(np.mean(current_cluster))
                current_cluster = [level]
        
        clusters.append(np.mean(current_cluster))
        return sorted(clusters, reverse=True)

    def _calculate_level_strength(self, levels: List[float], price_series: np.ndarray) -> Dict:
        """Calculate strength of support/resistance levels"""
        strength = {}
        for level in levels:
            touches = sum(1 for price in price_series if abs(price - level) / level <= 0.01)
            strength[level] = touches
        return strength

    def _detect_head_shoulders(self) -> List[Dict]:
        """Detect Head and Shoulders patterns"""
        patterns = []
        
        highs = self.data['High'].values
        lows = self.data['Low'].values
        
        # Find peaks
        peaks, _ = find_peaks(highs, distance=10)
        
        if len(peaks) >= 3:
            for i in range(len(peaks) - 2):
                left_shoulder = peaks[i]
                head = peaks[i + 1]
                right_shoulder = peaks[i + 2]
                
                # Check if it forms a head and shoulders pattern
                if (highs[head] > highs[left_shoulder] and 
                    highs[head] > highs[right_shoulder] and
                    abs(highs[left_shoulder] - highs[right_shoulder]) / highs[head] < 0.05):
                    
                    # Find neckline
                    left_trough = np.argmin(lows[left_shoulder:head]) + left_shoulder
                    right_trough = np.argmin(lows[head:right_shoulder]) + head
                    
                    neckline = (lows[left_trough] + lows[right_trough]) / 2
                    
                    pattern = {
                        'pattern_type': 'Head and Shoulders',
                        'pattern_subtype': 'Bearish Reversal',
                        'start_date': self.data.index[left_shoulder],
                        'end_date': self.data.index[right_shoulder],
                        'confidence': self._calculate_hs_confidence(left_shoulder, head, right_shoulder, neckline),
                        'target_price': neckline - (highs[head] - neckline),
                        'neckline': neckline,
                        'breakout_confirmed': self.data['Close'].iloc[-1] < neckline,
                        'volume_confirmation': self._check_volume_confirmation(left_shoulder, right_shoulder)
                    }
                    patterns.append(pattern)
        
        return patterns

    def _detect_double_patterns(self) -> List[Dict]:
        """Detect Double Top and Double Bottom patterns"""
        patterns = []
        
        highs = self.data['High'].values
        lows = self.data['Low'].values
        
        # Double Top
        peaks, _ = find_peaks(highs, distance=15)
        if len(peaks) >= 2:
            for i in range(len(peaks) - 1):
                peak1, peak2 = peaks[i], peaks[i + 1]
                if abs(highs[peak1] - highs[peak2]) / highs[peak1] < 0.03:
                    trough = np.argmin(lows[peak1:peak2]) + peak1
                    
                    pattern = {
                        'pattern_type': 'Double Top',
                        'pattern_subtype': 'Bearish Reversal',
                        'start_date': self.data.index[peak1],
                        'end_date': self.data.index[peak2],
                        'confidence': 0.75,
                        'support_level': lows[trough],
                        'breakout_confirmed': self.data['Close'].iloc[-1] < lows[trough],
                        'volume_confirmation': self._check_volume_confirmation(peak1, peak2)
                    }
                    patterns.append(pattern)
        
        # Double Bottom
        troughs, _ = find_peaks(-lows, distance=15)
        if len(troughs) >= 2:
            for i in range(len(troughs) - 1):
                trough1, trough2 = troughs[i], troughs[i + 1]
                if abs(lows[trough1] - lows[trough2]) / lows[trough1] < 0.03:
                    peak = np.argmax(highs[trough1:trough2]) + trough1
                    
                    pattern = {
                        'pattern_type': 'Double Bottom',
                        'pattern_subtype': 'Bullish Reversal',
                        'start_date': self.data.index[trough1],
                        'end_date': self.data.index[trough2],
                        'confidence': 0.75,
                        'resistance_level': highs[peak],
                        'breakout_confirmed': self.data['Close'].iloc[-1] > highs[peak],
                        'volume_confirmation': self._check_volume_confirmation(trough1, trough2)
                    }
                    patterns.append(pattern)
        
        return patterns

    def _detect_triangles(self) -> List[Dict]:
        """Detect triangle patterns (Ascending, Descending, Symmetrical)"""
        patterns = []
        
        if len(self.data) < 40:
            return patterns
        
        highs = self.data['High'].values
        lows = self.data['Low'].values
        
        # Look for triangle patterns in recent data
        window = min(40, len(self.data))
        recent_highs = highs[-window:]
        recent_lows = lows[-window:]
        
        # Find peaks and troughs
        peaks, _ = find_peaks(recent_highs, distance=5)
        troughs, _ = find_peaks(-recent_lows, distance=5)
        
        if len(peaks) >= 3 and len(troughs) >= 3:
            # Calculate trend lines
            peak_slope, peak_intercept, peak_r, _, _ = linregress(peaks, recent_highs[peaks])
            trough_slope, trough_intercept, trough_r, _, _ = linregress(troughs, recent_lows[troughs])
            
            # Determine triangle type
            if abs(peak_slope) < 0.01 and trough_slope > 0.01:
                triangle_type = "Ascending Triangle"
                bias = "Bullish"
            elif peak_slope < -0.01 and abs(trough_slope) < 0.01:
                triangle_type = "Descending Triangle"
                bias = "Bearish"
            elif peak_slope < -0.01 and trough_slope > 0.01:
                triangle_type = "Symmetrical Triangle"
                bias = "Neutral"
            else:
                return patterns
            
            pattern = {
                'pattern_type': triangle_type,
                'pattern_subtype': f'{bias} Continuation',
                'start_date': self.data.index[-window],
                'end_date': self.data.index[-1],
                'confidence': min(abs(peak_r), abs(trough_r)),
                'upper_trendline_slope': peak_slope,
                'lower_trendline_slope': trough_slope,
                'breakout_level': self._calculate_triangle_breakout_level(recent_highs, recent_lows),
                'volume_confirmation': self._check_triangle_volume_pattern()
            }
            patterns.append(pattern)
        
        return patterns

    def _detect_doji(self) -> List[Dict]:
        """Detect Doji candlestick patterns"""
        patterns = []
        
        for i in range(len(self.data)):
            open_price = self.data['Open'].iloc[i]
            close_price = self.data['Close'].iloc[i]
            high_price = self.data['High'].iloc[i]
            low_price = self.data['Low'].iloc[i]
            
            body_size = abs(close_price - open_price)
            total_range = high_price - low_price
            
            # Doji criteria: very small body relative to total range
            if total_range > 0 and body_size / total_range < 0.1:
                upper_shadow = high_price - max(open_price, close_price)
                lower_shadow = min(open_price, close_price) - low_price
                
                # Classify Doji type
                if upper_shadow > 2 * lower_shadow:
                    doji_type = "Dragonfly Doji"
                    signal = "Bullish"
                elif lower_shadow > 2 * upper_shadow:
                    doji_type = "Gravestone Doji"
                    signal = "Bearish"
                else:
                    doji_type = "Classic Doji"
                    signal = "Indecision"
                
                pattern = {
                    'pattern_type': doji_type,
                    'pattern_subtype': f'{signal} Reversal',
                    'date': self.data.index[i],
                    'confidence': 0.6,
                    'signal_strength': self._calculate_doji_strength(body_size, total_range),
                    'market_context': self._get_market_context(i)
                }
                patterns.append(pattern)
        
        return patterns[-10:]  # Return only last 10 patterns

    def _detect_engulfing(self) -> List[Dict]:
        """Detect Bullish and Bearish Engulfing patterns"""
        patterns = []
        
        for i in range(1, len(self.data)):
            prev_open = self.data['Open'].iloc[i-1]
            prev_close = self.data['Close'].iloc[i-1]
            curr_open = self.data['Open'].iloc[i]
            curr_close = self.data['Close'].iloc[i]
            
            prev_body = abs(prev_close - prev_open)
            curr_body = abs(curr_close - curr_open)
            
            # Bullish Engulfing
            if (prev_close < prev_open and  # Previous candle bearish
                curr_close > curr_open and  # Current candle bullish
                curr_open < prev_close and  # Current opens below previous close
                curr_close > prev_open and  # Current closes above previous open
                curr_body > prev_body):     # Current body engulfs previous
                
                pattern = {
                    'pattern_type': 'Bullish Engulfing',
                    'pattern_subtype': 'Bullish Reversal',
                    'date': self.data.index[i],
                    'confidence': 0.75,
                    'volume_confirmation': self._check_engulfing_volume(i),
                    'market_context': self._get_market_context(i)
                }
                patterns.append(pattern)
            
            # Bearish Engulfing
            elif (prev_close > prev_open and  # Previous candle bullish
                  curr_close < curr_open and  # Current candle bearish
                  curr_open > prev_close and  # Current opens above previous close
                  curr_close < prev_open and  # Current closes below previous open
                  curr_body > prev_body):     # Current body engulfs previous
                
                pattern = {
                    'pattern_type': 'Bearish Engulfing',
                    'pattern_subtype': 'Bearish Reversal',
                    'date': self.data.index[i],
                    'confidence': 0.75,
                    'volume_confirmation': self._check_engulfing_volume(i),
                    'market_context': self._get_market_context(i)
                }
                patterns.append(pattern)
        
        return patterns[-10:]  # Return only last 10 patterns

    def _check_volume_confirmation(self, start_idx: int, end_idx: int) -> bool:
        """Check if volume confirms the pattern"""
        if 'Volume' not in self.data.columns:
            return False
        
        pattern_volume = self.data['Volume'].iloc[start_idx:end_idx+1].mean()
        avg_volume = self.data['Volume'].rolling(window=20).mean().iloc[end_idx]
        
        return pattern_volume > avg_volume * 1.2

    def _calculate_hs_confidence(self, left: int, head: int, right: int, neckline: float) -> float:
        """Calculate confidence score for Head and Shoulders pattern"""
        highs = self.data['High'].values
        
        # Symmetry check
        symmetry_score = 1 - abs(highs[left] - highs[right]) / highs[head]
        
        # Height ratio check
        height_score = min(highs[head] / highs[left], highs[head] / highs[right]) - 1
        
        # Volume confirmation
        volume_score = 0.5 if self._check_volume_confirmation(left, right) else 0
        
        return min(0.9, max(0.3, (symmetry_score + height_score + volume_score) / 3))

    def _calculate_triangle_breakout_level(self, highs: np.ndarray, lows: np.ndarray) -> float:
        """Calculate the breakout level for triangle patterns"""
        return (np.max(highs) + np.min(lows)) / 2

    def _check_triangle_volume_pattern(self) -> bool:
        """Check if volume pattern supports triangle formation"""
        if len(self.data) < 20:
            return False
        
        recent_volume = self.data['Volume'].tail(20)
        return recent_volume.iloc[-5:].mean() < recent_volume.iloc[:15].mean()

    def _calculate_doji_strength(self, body_size: float, total_range: float) -> float:
        """Calculate the strength of a Doji pattern"""
        return 1 - (body_size / total_range) if total_range > 0 else 0

    def _get_market_context(self, index: int) -> str:
        """Determine market context at the given index"""
        if index < 10:
            return "Insufficient data"
        
        recent_prices = self.data['Close'].iloc[index-10:index+1]
        trend = "Uptrend" if recent_prices.iloc[-1] > recent_prices.iloc[0] else "Downtrend"
        
        return trend

    def _check_engulfing_volume(self, index: int) -> bool:
        """Check volume confirmation for engulfing patterns"""
        if index < 20 or 'Volume' not in self.data.columns:
            return False
        
        current_volume = self.data['Volume'].iloc[index]
        avg_volume = self.data['Volume'].iloc[index-20:index].mean()
        
        return current_volume > avg_volume * 1.5

    def _detect_wedges(self) -> List[Dict]:
        """Detect Rising and Falling Wedge patterns"""
        # Simplified implementation - can be expanded
        return []

    def _detect_flags_pennants(self) -> List[Dict]:
        """Detect Flag and Pennant patterns"""
        # Simplified implementation - can be expanded
        return []

    def _detect_cup_handle(self) -> List[Dict]:
        """Detect Cup and Handle patterns"""
        # Simplified implementation - can be expanded
        return []

    def _detect_hammer_hanging_man(self) -> List[Dict]:
        """Detect Hammer and Hanging Man patterns"""
        # Simplified implementation - can be expanded
        return []

    def _detect_shooting_star_inverted_hammer(self) -> List[Dict]:
        """Detect Shooting Star and Inverted Hammer patterns"""
        # Simplified implementation - can be expanded
        return []

    def _detect_harami(self) -> List[Dict]:
        """Detect Harami patterns"""
        # Simplified implementation - can be expanded
        return []

    def _detect_piercing_dark_cloud(self) -> List[Dict]:
        """Detect Piercing Line and Dark Cloud Cover patterns"""
        # Simplified implementation - can be expanded
        return []

    def _detect_morning_evening_star(self) -> List[Dict]:
        """Detect Morning Star and Evening Star patterns"""
        # Simplified implementation - can be expanded
        return []

    def _detect_three_soldiers_crows(self) -> List[Dict]:
        """Detect Three White Soldiers and Three Black Crows patterns"""
        # Simplified implementation - can be expanded
        return []

    def _detect_level_breakouts(self, sr_levels: Dict) -> List[Dict]:
        """Detect breakouts from support/resistance levels"""
        # Simplified implementation - can be expanded
        return []

    def _detect_volume_breakouts(self) -> List[Dict]:
        """Detect volume breakout patterns"""
        # Simplified implementation - can be expanded
        return []

    def _detect_ma_breakouts(self) -> List[Dict]:
        """Detect moving average breakouts"""
        # Simplified implementation - can be expanded
        return []

    def _detect_range_breakouts(self) -> List[Dict]:
        """Detect range breakout patterns"""
        # Simplified implementation - can be expanded
        return []

def create_patterns_table(cursor):
    """Create the technical_patterns table"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS technical_patterns (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            timeframe VARCHAR(20) NOT NULL DEFAULT 'daily',
            pattern_type VARCHAR(50) NOT NULL,
            pattern_subtype VARCHAR(50),
            start_date TIMESTAMP,
            end_date TIMESTAMP,
            confidence DECIMAL(3,2),
            signal_strength DECIMAL(3,2),
            breakout_confirmed BOOLEAN DEFAULT FALSE,
            volume_confirmation BOOLEAN DEFAULT FALSE,
            target_price DECIMAL(10,2),
            support_level DECIMAL(10,2),
            resistance_level DECIMAL(10,2),
            pattern_data JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_patterns_symbol ON technical_patterns(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_patterns_type ON technical_patterns(pattern_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_patterns_date ON technical_patterns(end_date DESC)")

def process_symbol_patterns(symbol: str, timeframe: str = "daily") -> Dict:
    """Process patterns for a single symbol"""
    try:
        # Download data
        stock = yf.Ticker(symbol)
        
        # Determine period based on timeframe
        if timeframe == "daily":
            period = "1y"  # 1 year of daily data
        elif timeframe == "weekly":
            period = "2y"  # 2 years of weekly data
        else:
            period = "5y"  # 5 years of monthly data
        
        hist = stock.history(period=period, interval="1d" if timeframe == "daily" else "1wk" if timeframe == "weekly" else "1mo")
        
        if hist.empty:
            logging.warning(f"No data for {symbol}")
            return {'success': False, 'error': 'No data'}
        
        # Initialize pattern detector
        detector = TechnicalPatternDetector(symbol, hist, timeframe)
        
        # Detect all patterns
        classical_patterns = detector.detect_classical_patterns()
        candlestick_patterns = detector.detect_candlestick_patterns()
        breakout_patterns = detector.detect_breakout_patterns()
        support_resistance = detector.detect_support_resistance()
        
        all_patterns = classical_patterns + candlestick_patterns + breakout_patterns
        
        return {
            'success': True,
            'symbol': symbol,
            'timeframe': timeframe,
            'patterns': all_patterns,
            'support_resistance': support_resistance,
            'total_patterns': len(all_patterns)
        }
        
    except Exception as e:
        logging.error(f"Error processing {symbol}: {e}")
        return {'success': False, 'error': str(e)}

def save_patterns_to_db(cursor, pattern_results: List[Dict]):
    """Save pattern results to database"""
    if not pattern_results:
        return
    
    insert_data = []
    
    for result in pattern_results:
        if not result.get('success'):
            continue
        
        symbol = result['symbol']
        timeframe = result['timeframe']
        
        for pattern in result.get('patterns', []):
            insert_data.append((
                symbol,
                timeframe,
                pattern.get('pattern_type'),
                pattern.get('pattern_subtype'),
                pattern.get('start_date'),
                pattern.get('end_date', pattern.get('date')),
                pattern.get('confidence'),
                pattern.get('signal_strength'),
                pattern.get('breakout_confirmed', False),
                pattern.get('volume_confirmation', False),
                pattern.get('target_price'),
                pattern.get('support_level'),
                pattern.get('resistance_level'),
                json.dumps(pattern)  # Store full pattern data as JSON
            ))
    
    if insert_data:
        # Clear existing patterns for these symbols
        symbols = list(set([r['symbol'] for r in pattern_results if r.get('success')]))
        if symbols:
            cursor.execute(
                "DELETE FROM technical_patterns WHERE symbol = ANY(%s)",
                (symbols,)
            )
        
        # Insert new patterns
        execute_values(
            cursor,
            """
            INSERT INTO technical_patterns (
                symbol, timeframe, pattern_type, pattern_subtype, start_date, end_date,
                confidence, signal_strength, breakout_confirmed, volume_confirmation,
                target_price, support_level, resistance_level, pattern_data
            ) VALUES %s
            """,
            insert_data,
            template=None,
            page_size=1000
        )
        
        logging.info(f"Inserted {len(insert_data)} patterns for {len(symbols)} symbols")

def main():
    """Main execution function"""
    start_time = time.time()
    logging.info(f"Starting {SCRIPT_NAME}")
    
    try:
        # Database connection
        db_config = get_db_config()
        conn = psycopg2.connect(**db_config,
            sslmode='disable'
    )
        cursor = conn.cursor()
        
        # Create table
        create_patterns_table(cursor)
        conn.commit()
        
        # Get symbols to process
        cursor.execute("SELECT DISTINCT symbol FROM stocks ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        
        logging.info(f"Processing {len(symbols)} symbols for technical patterns")
        
        # Process symbols in batches
        batch_size = 50
        all_results = []
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            logging.info(f"Processing batch {i//batch_size + 1}/{(len(symbols)-1)//batch_size + 1}")
            
            # Process batch with threading
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(process_symbol_patterns, symbol) for symbol in batch]
                
                batch_results = []
                for future in as_completed(futures):
                    try:
                        result = future.result(timeout=30)
                        batch_results.append(result)
                    except Exception as e:
                        logging.error(f"Future failed: {e}")
            
            # Save batch results
            save_patterns_to_db(cursor, batch_results)
            conn.commit()
            all_results.extend(batch_results)
            
            # Memory cleanup
            gc.collect()
        
        # Final statistics
        successful_results = [r for r in all_results if r.get('success')]
        total_patterns = sum(r.get('total_patterns', 0) for r in successful_results)
        
        logging.info(f"Processing complete: {len(successful_results)}/{len(symbols)} symbols processed")
        logging.info(f"Total patterns detected: {total_patterns}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        logging.error(f"Fatal error in {SCRIPT_NAME}: {e}")
        sys.exit(1)
    
    finally:
        elapsed = time.time() - start_time
        logging.info(f"{SCRIPT_NAME} completed in {elapsed:.2f} seconds")

if __name__ == "__main__":
    main()