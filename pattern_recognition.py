#!/usr/bin/env python3
"""
Technical Pattern Recognition System
AI-powered detection of classic chart patterns
Based on Lo, Mamaysky & Wang (2000) research
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, NamedTuple
import yfinance as yf
from dataclasses import dataclass
from abc import ABC, abstractmethod
from scipy import signal
from scipy.stats import linregress
import warnings
warnings.filterwarnings('ignore')

@dataclass
class PatternResult:
    pattern_type: str
    confidence: float  # 0-1 scale
    start_date: datetime
    end_date: datetime
    key_points: List[Tuple[datetime, float]]  # Important price points
    target_price: Optional[float]  # Expected price target
    stop_loss: Optional[float]  # Suggested stop loss
    probability: float  # Historical success probability
    description: str
    raw_data: Dict

class BasePattern(ABC):
    """Base class for pattern recognition"""
    
    def __init__(self, min_confidence: float = 0.6):
        self.min_confidence = min_confidence
        self.pattern_name = self.__class__.__name__.replace('Pattern', '')
    
    @abstractmethod
    def detect(self, data: pd.DataFrame) -> List[PatternResult]:
        pass
    
    def _calculate_support_resistance(self, data: pd.DataFrame, window: int = 20) -> Tuple[List, List]:
        """Calculate support and resistance levels"""
        highs = data['High'].rolling(window=window, center=True).max()
        lows = data['Low'].rolling(window=window, center=True).min()
        
        # Find local maxima and minima
        resistance_levels = []
        support_levels = []
        
        for i in range(window, len(data) - window):
            if data['High'].iloc[i] == highs.iloc[i]:
                resistance_levels.append((data.index[i], data['High'].iloc[i]))
            if data['Low'].iloc[i] == lows.iloc[i]:
                support_levels.append((data.index[i], data['Low'].iloc[i]))
        
        return support_levels, resistance_levels
    
    def _find_peaks_and_troughs(self, prices: np.array, prominence: float = 0.02) -> Tuple[np.array, np.array]:
        """Find significant peaks and troughs in price data"""
        # Find peaks (local maxima)
        peaks, _ = signal.find_peaks(prices, prominence=prominence * np.mean(prices))
        
        # Find troughs (local minima)
        troughs, _ = signal.find_peaks(-prices, prominence=prominence * np.mean(prices))
        
        return peaks, troughs

class HeadAndShouldersPattern(BasePattern):
    """
    Head and Shoulders Pattern Detection
    Classic reversal pattern with three peaks
    """
    
    def detect(self, data: pd.DataFrame) -> List[PatternResult]:
        patterns = []
        
        if len(data) < 50:  # Need sufficient data
            return patterns
        
        prices = data['Close'].values
        peaks, troughs = self._find_peaks_and_troughs(prices)
        
        if len(peaks) < 3 or len(troughs) < 2:
            return patterns
        
        # Look for head and shoulders formations
        for i in range(len(peaks) - 2):
            left_shoulder = peaks[i]
            head = peaks[i + 1]
            right_shoulder = peaks[i + 2]
            
            # Get corresponding troughs
            left_trough = None
            right_trough = None
            
            for trough in troughs:
                if left_shoulder < trough < head and left_trough is None:
                    left_trough = trough
                elif head < trough < right_shoulder and right_trough is None:
                    right_trough = trough
            
            if left_trough is None or right_trough is None:
                continue
            
            # Validate head and shoulders criteria
            if self._validate_head_and_shoulders(data, left_shoulder, head, right_shoulder, left_trough, right_trough):
                pattern = self._create_head_and_shoulders_result(
                    data, left_shoulder, head, right_shoulder, left_trough, right_trough
                )
                patterns.append(pattern)
        
        return patterns
    
    def _validate_head_and_shoulders(self, data: pd.DataFrame, ls: int, h: int, rs: int, lt: int, rt: int) -> bool:
        """Validate head and shoulders pattern criteria"""
        prices = data['Close'].values
        
        # Head should be higher than both shoulders
        if not (prices[h] > prices[ls] and prices[h] > prices[rs]):
            return False
        
        # Shoulders should be roughly equal height (within 5%)
        shoulder_diff = abs(prices[ls] - prices[rs]) / prices[ls]
        if shoulder_diff > 0.05:
            return False
        
        # Neckline should be roughly horizontal
        neckline_slope = abs(prices[lt] - prices[rt]) / prices[lt]
        if neckline_slope > 0.03:
            return False
        
        # Volume should decrease towards right shoulder (if available)
        if 'Volume' in data.columns:
            vol_ls = data['Volume'].iloc[ls]
            vol_h = data['Volume'].iloc[h]
            vol_rs = data['Volume'].iloc[rs]
            
            if not (vol_h > vol_rs and vol_ls > vol_rs):
                return False
        
        return True
    
    def _create_head_and_shoulders_result(self, data: pd.DataFrame, ls: int, h: int, rs: int, lt: int, rt: int) -> PatternResult:
        """Create pattern result for head and shoulders"""
        prices = data['Close'].values
        dates = data.index
        
        # Calculate neckline level
        neckline = (prices[lt] + prices[rt]) / 2
        
        # Calculate target price (head to neckline distance projected down)
        head_to_neckline = prices[h] - neckline
        target_price = neckline - head_to_neckline
        
        # Stop loss above right shoulder
        stop_loss = prices[rs] * 1.02
        
        # Calculate confidence based on pattern quality
        confidence = self._calculate_hs_confidence(data, ls, h, rs, lt, rt)
        
        key_points = [
            (dates[ls], prices[ls]),  # Left shoulder
            (dates[h], prices[h]),    # Head
            (dates[rs], prices[rs]),  # Right shoulder
            (dates[lt], prices[lt]),  # Left trough
            (dates[rt], prices[rt])   # Right trough
        ]
        
        return PatternResult(
            pattern_type='Head and Shoulders',
            confidence=confidence,
            start_date=dates[ls],
            end_date=dates[rs],
            key_points=key_points,
            target_price=target_price,
            stop_loss=stop_loss,
            probability=0.65,  # Historical success rate
            description=f"Bearish reversal pattern with head at ${prices[h]:.2f} and neckline at ${neckline:.2f}",
            raw_data={
                'neckline': neckline,
                'head_height': head_to_neckline,
                'pattern_indices': [ls, h, rs, lt, rt]
            }
        )
    
    def _calculate_hs_confidence(self, data: pd.DataFrame, ls: int, h: int, rs: int, lt: int, rt: int) -> float:
        """Calculate confidence score for head and shoulders pattern"""
        prices = data['Close'].values
        confidence = 0.5  # Base confidence
        
        # Symmetry bonus
        left_duration = h - ls
        right_duration = rs - h
        symmetry = 1 - abs(left_duration - right_duration) / max(left_duration, right_duration)
        confidence += symmetry * 0.2
        
        # Volume confirmation bonus
        if 'Volume' in data.columns:
            vol_confirmation = self._check_volume_confirmation(data, ls, h, rs)
            confidence += vol_confirmation * 0.2
        
        # Pattern clarity bonus
        pattern_clarity = self._calculate_pattern_clarity(prices, [ls, h, rs, lt, rt])
        confidence += pattern_clarity * 0.1
        
        return min(1.0, confidence)
    
    def _check_volume_confirmation(self, data: pd.DataFrame, ls: int, h: int, rs: int) -> float:
        """Check volume confirmation for pattern"""
        volumes = data['Volume'].values
        
        # Volume should be highest at head, lowest at right shoulder
        if volumes[h] > volumes[ls] and volumes[h] > volumes[rs] and volumes[rs] < volumes[ls]:
            return 1.0
        elif volumes[h] > volumes[rs]:
            return 0.5
        else:
            return 0.0
    
    def _calculate_pattern_clarity(self, prices: np.array, indices: List[int]) -> float:
        """Calculate how clear/distinct the pattern is"""
        # Measure how well the pattern stands out from noise
        pattern_points = prices[indices]
        pattern_range = np.max(pattern_points) - np.min(pattern_points)
        
        # Calculate noise in surrounding area
        start_idx = max(0, indices[0] - 10)
        end_idx = min(len(prices), indices[-1] + 10)
        surrounding_volatility = np.std(prices[start_idx:end_idx])
        
        if surrounding_volatility == 0:
            return 1.0
        
        clarity = min(1.0, pattern_range / (surrounding_volatility * 4))
        return clarity

class DoubleTopPattern(BasePattern):
    """Double Top Pattern Detection"""
    
    def detect(self, data: pd.DataFrame) -> List[PatternResult]:
        patterns = []
        
        if len(data) < 30:
            return patterns
        
        prices = data['Close'].values
        peaks, troughs = self._find_peaks_and_troughs(prices)
        
        if len(peaks) < 2 or len(troughs) < 1:
            return patterns
        
        # Look for double top formations
        for i in range(len(peaks) - 1):
            first_top = peaks[i]
            second_top = peaks[i + 1]
            
            # Find trough between tops
            valley = None
            for trough in troughs:
                if first_top < trough < second_top:
                    valley = trough
                    break
            
            if valley is None:
                continue
            
            if self._validate_double_top(data, first_top, second_top, valley):
                pattern = self._create_double_top_result(data, first_top, second_top, valley)
                patterns.append(pattern)
        
        return patterns
    
    def _validate_double_top(self, data: pd.DataFrame, ft: int, st: int, v: int) -> bool:
        """Validate double top pattern"""
        prices = data['Close'].values
        
        # Tops should be roughly equal (within 2%)
        top_diff = abs(prices[ft] - prices[st]) / prices[ft]
        if top_diff > 0.02:
            return False
        
        # Valley should be significantly lower than tops (at least 3%)
        valley_depth = min(prices[ft], prices[st]) - prices[v]
        valley_percentage = valley_depth / prices[v]
        if valley_percentage < 0.03:
            return False
        
        # Sufficient time between tops
        time_diff = st - ft
        if time_diff < 10:  # At least 10 periods apart
            return False
        
        return True
    
    def _create_double_top_result(self, data: pd.DataFrame, ft: int, st: int, v: int) -> PatternResult:
        """Create double top pattern result"""
        prices = data['Close'].values
        dates = data.index
        
        # Support level at valley
        support_level = prices[v]
        
        # Target price below support
        top_level = (prices[ft] + prices[st]) / 2
        pattern_height = top_level - support_level
        target_price = support_level - pattern_height
        
        # Stop loss above second top
        stop_loss = prices[st] * 1.02
        
        confidence = self._calculate_double_top_confidence(data, ft, st, v)
        
        key_points = [
            (dates[ft], prices[ft]),  # First top
            (dates[v], prices[v]),    # Valley
            (dates[st], prices[st])   # Second top
        ]
        
        return PatternResult(
            pattern_type='Double Top',
            confidence=confidence,
            start_date=dates[ft],
            end_date=dates[st],
            key_points=key_points,
            target_price=target_price,
            stop_loss=stop_loss,
            probability=0.60,
            description=f"Bearish reversal pattern with resistance at ${top_level:.2f}",
            raw_data={
                'support_level': support_level,
                'resistance_level': top_level,
                'pattern_height': pattern_height
            }
        )
    
    def _calculate_double_top_confidence(self, data: pd.DataFrame, ft: int, st: int, v: int) -> float:
        """Calculate confidence for double top pattern"""
        prices = data['Close'].values
        
        # Base confidence
        confidence = 0.6
        
        # Symmetry of tops
        top_symmetry = 1 - abs(prices[ft] - prices[st]) / max(prices[ft], prices[st])
        confidence += top_symmetry * 0.2
        
        # Depth of valley
        valley_depth = (min(prices[ft], prices[st]) - prices[v]) / prices[v]
        depth_score = min(1.0, valley_depth / 0.05)  # Normalize to 5% depth
        confidence += depth_score * 0.2
        
        return min(1.0, confidence)

class TrianglePattern(BasePattern):
    """Triangle Pattern Detection (Ascending, Descending, Symmetrical)"""
    
    def detect(self, data: pd.DataFrame) -> List[PatternResult]:
        patterns = []
        
        if len(data) < 40:
            return patterns
        
        # Look for triangle patterns in recent data
        recent_data = data.tail(40)
        
        triangle_result = self._detect_triangle(recent_data)
        if triangle_result:
            patterns.append(triangle_result)
        
        return patterns
    
    def _detect_triangle(self, data: pd.DataFrame) -> Optional[PatternResult]:
        """Detect triangle pattern in data"""
        highs = data['High'].values
        lows = data['Low'].values
        dates = data.index
        
        # Find trend lines for highs and lows
        high_trend = self._fit_trend_line(highs)
        low_trend = self._fit_trend_line(lows)
        
        if not high_trend or not low_trend:
            return None
        
        # Determine triangle type
        triangle_type = self._classify_triangle(high_trend, low_trend)
        
        if triangle_type == 'none':
            return None
        
        # Calculate convergence point
        convergence_point = self._calculate_convergence(high_trend, low_trend, len(data))
        
        # Create pattern result
        confidence = self._calculate_triangle_confidence(data, high_trend, low_trend)
        
        if confidence < self.min_confidence:
            return None
        
        # Calculate targets based on triangle type
        target_price, stop_loss = self._calculate_triangle_targets(
            data, triangle_type, high_trend, low_trend
        )
        
        key_points = [
            (dates[0], highs[0]),
            (dates[-1], highs[-1]),
            (dates[0], lows[0]),
            (dates[-1], lows[-1])
        ]
        
        return PatternResult(
            pattern_type=f'{triangle_type.title()} Triangle',
            confidence=confidence,
            start_date=dates[0],
            end_date=dates[-1],
            key_points=key_points,
            target_price=target_price,
            stop_loss=stop_loss,
            probability=0.55,  # Moderate reliability
            description=f"{triangle_type.title()} triangle pattern with convergence expected",
            raw_data={
                'triangle_type': triangle_type,
                'high_slope': high_trend['slope'],
                'low_slope': low_trend['slope'],
                'convergence_point': convergence_point
            }
        )
    
    def _fit_trend_line(self, prices: np.array) -> Optional[Dict]:
        """Fit trend line to price data"""
        x = np.arange(len(prices))
        
        try:
            slope, intercept, r_value, p_value, std_err = linregress(x, prices)
            
            # Only accept trend lines with reasonable correlation
            if abs(r_value) > 0.3:
                return {
                    'slope': slope,
                    'intercept': intercept,
                    'r_value': r_value,
                    'p_value': p_value
                }
        except:
            pass
        
        return None
    
    def _classify_triangle(self, high_trend: Dict, low_trend: Dict) -> str:
        """Classify triangle type based on trend lines"""
        high_slope = high_trend['slope']
        low_slope = low_trend['slope']
        
        slope_threshold = 0.01
        
        # Ascending triangle: flat resistance, rising support
        if abs(high_slope) < slope_threshold and low_slope > slope_threshold:
            return 'ascending'
        
        # Descending triangle: declining resistance, flat support
        elif high_slope < -slope_threshold and abs(low_slope) < slope_threshold:
            return 'descending'
        
        # Symmetrical triangle: converging lines
        elif high_slope < -slope_threshold and low_slope > slope_threshold:
            return 'symmetrical'
        
        return 'none'
    
    def _calculate_convergence(self, high_trend: Dict, low_trend: Dict, data_length: int) -> int:
        """Calculate where trend lines converge"""
        # Solve for intersection point
        # high_trend: y = m1*x + b1
        # low_trend: y = m2*x + b2
        # Intersection: m1*x + b1 = m2*x + b2
        
        slope_diff = high_trend['slope'] - low_trend['slope']
        if abs(slope_diff) < 1e-6:  # Parallel lines
            return data_length * 2  # Far future
        
        x_intersect = (low_trend['intercept'] - high_trend['intercept']) / slope_diff
        return int(x_intersect)
    
    def _calculate_triangle_confidence(self, data: pd.DataFrame, high_trend: Dict, low_trend: Dict) -> float:
        """Calculate confidence in triangle pattern"""
        confidence = 0.5
        
        # R-value bonus (how well lines fit)
        r_bonus = (abs(high_trend['r_value']) + abs(low_trend['r_value'])) * 0.25
        confidence += r_bonus
        
        # Volume pattern (should decrease towards apex)
        if 'Volume' in data.columns:
            vol_trend = self._check_volume_trend(data)
            confidence += vol_trend * 0.2
        
        # Touch points (more touches = higher confidence)
        touch_bonus = self._count_touch_points(data, high_trend, low_trend) * 0.05
        confidence += min(0.2, touch_bonus)
        
        return min(1.0, confidence)
    
    def _check_volume_trend(self, data: pd.DataFrame) -> float:
        """Check if volume decreases towards triangle apex"""
        volumes = data['Volume'].values
        
        # Fit trend line to volume
        x = np.arange(len(volumes))
        try:
            slope, _, r_value, _, _ = linregress(x, volumes)
            
            # Volume should decrease (negative slope)
            if slope < 0 and abs(r_value) > 0.3:
                return 1.0
            elif slope < 0:
                return 0.5
        except:
            pass
        
        return 0.0
    
    def _count_touch_points(self, data: pd.DataFrame, high_trend: Dict, low_trend: Dict) -> int:
        """Count how many times price touches trend lines"""
        highs = data['High'].values
        lows = data['Low'].values
        
        touch_count = 0
        tolerance = 0.01  # 1% tolerance
        
        for i, (high, low) in enumerate(zip(highs, lows)):
            # Calculate expected trend line values
            expected_high = high_trend['slope'] * i + high_trend['intercept']
            expected_low = low_trend['slope'] * i + low_trend['intercept']
            
            # Check for touches
            if abs(high - expected_high) / expected_high < tolerance:
                touch_count += 1
            if abs(low - expected_low) / expected_low < tolerance:
                touch_count += 1
        
        return touch_count
    
    def _calculate_triangle_targets(self, data: pd.DataFrame, triangle_type: str, 
                                  high_trend: Dict, low_trend: Dict) -> Tuple[float, float]:
        """Calculate price targets for triangle breakout"""
        current_price = data['Close'].iloc[-1]
        
        # Calculate triangle height at start
        start_high = high_trend['intercept']
        start_low = low_trend['intercept']
        triangle_height = start_high - start_low
        
        # Target based on triangle type
        if triangle_type == 'ascending':
            # Bullish bias - target above resistance
            resistance = high_trend['intercept']  # Flat line
            target_price = resistance + triangle_height
            stop_loss = start_low * 0.98
            
        elif triangle_type == 'descending':
            # Bearish bias - target below support
            support = low_trend['intercept']  # Flat line
            target_price = support - triangle_height
            stop_loss = start_high * 1.02
            
        else:  # symmetrical
            # Neutral - target in breakout direction
            mid_point = (start_high + start_low) / 2
            target_price = mid_point + triangle_height * 0.5  # Conservative target
            stop_loss = mid_point - triangle_height * 0.3
        
        return target_price, stop_loss

class TechnicalPatternRecognizer:
    """
    Main Technical Pattern Recognition System
    Coordinates multiple pattern detectors
    """
    
    def __init__(self, confidence_threshold: float = 0.6):
        self.confidence_threshold = confidence_threshold
        self.patterns = [
            HeadAndShouldersPattern(confidence_threshold),
            DoubleTopPattern(confidence_threshold),
            TrianglePattern(confidence_threshold)
        ]
    
    def detect_patterns(self, symbol: str, period: str = "1y") -> Dict:
        """Detect patterns for a given symbol"""
        try:
            # Fetch price data
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period)
            
            if data.empty:
                return {
                    'symbol': symbol,
                    'patterns_found': [],
                    'error': 'No data available',
                    'analysis_date': datetime.now()
                }
            
            # Run all pattern detectors
            all_patterns = []
            for pattern_detector in self.patterns:
                patterns = pattern_detector.detect(data)
                all_patterns.extend(patterns)
            
            # Filter by confidence and sort
            significant_patterns = [
                p for p in all_patterns 
                if p.confidence >= self.confidence_threshold
            ]
            
            significant_patterns.sort(key=lambda x: x.confidence, reverse=True)
            
            # Calculate overall pattern score
            pattern_score = self._calculate_overall_score(significant_patterns)
            
            return {
                'symbol': symbol,
                'patterns_found': len(significant_patterns),
                'pattern_score': pattern_score,
                'patterns': [self._pattern_to_dict(p) for p in significant_patterns],
                'analysis_date': datetime.now(),
                'data_period': period,
                'current_price': data['Close'].iloc[-1]
            }
            
        except Exception as e:
            return {
                'symbol': symbol,
                'patterns_found': 0,
                'pattern_score': 0.0,
                'patterns': [],
                'error': str(e),
                'analysis_date': datetime.now()
            }
    
    def _calculate_overall_score(self, patterns: List[PatternResult]) -> float:
        """Calculate overall technical pattern score"""
        if not patterns:
            return 0.0
        
        # Weight patterns by confidence and recency
        total_score = 0.0
        total_weight = 0.0
        
        for pattern in patterns:
            # Recent patterns get higher weight
            days_ago = (datetime.now() - pattern.end_date).days
            recency_weight = max(0.1, 1.0 - days_ago / 365.0)
            
            weight = pattern.confidence * recency_weight
            total_score += pattern.probability * weight
            total_weight += weight
        
        return total_score / total_weight if total_weight > 0 else 0.0
    
    def _pattern_to_dict(self, pattern: PatternResult) -> Dict:
        """Convert pattern result to dictionary"""
        return {
            'type': pattern.pattern_type,
            'confidence': pattern.confidence,
            'start_date': pattern.start_date.isoformat(),
            'end_date': pattern.end_date.isoformat(),
            'target_price': pattern.target_price,
            'stop_loss': pattern.stop_loss,
            'probability': pattern.probability,
            'description': pattern.description,
            'key_points': [
                {'date': date.isoformat(), 'price': price}
                for date, price in pattern.key_points
            ]
        }
    
    def analyze_multiple_symbols(self, symbols: List[str]) -> Dict:
        """Analyze patterns for multiple symbols"""
        results = {}
        
        for symbol in symbols:
            print(f"Analyzing patterns for {symbol}...")
            results[symbol] = self.detect_patterns(symbol)
            time.sleep(0.1)  # Rate limiting
        
        # Calculate summary statistics
        total_patterns = sum(r['patterns_found'] for r in results.values())
        avg_score = np.mean([r.get('pattern_score', 0) for r in results.values()])
        
        return {
            'individual_results': results,
            'summary': {
                'symbols_analyzed': len(symbols),
                'total_patterns_found': total_patterns,
                'average_pattern_score': avg_score,
                'analysis_timestamp': datetime.now().isoformat()
            }
        }

def main():
    """Example usage of pattern recognition system"""
    print("Technical Pattern Recognition System")
    print("=" * 40)
    
    recognizer = TechnicalPatternRecognizer(confidence_threshold=0.6)
    
    # Test symbols
    test_symbols = ['AAPL', 'MSFT', 'TSLA']
    
    for symbol in test_symbols:
        print(f"\nAnalyzing {symbol}:")
        print("-" * 20)
        
        result = recognizer.detect_patterns(symbol)
        
        print(f"Patterns Found: {result['patterns_found']}")
        print(f"Pattern Score: {result.get('pattern_score', 0):.2f}")
        
        if result['patterns']:
            print("\nDetected Patterns:")
            for pattern in result['patterns']:
                print(f"  - {pattern['type']}: {pattern['confidence']:.1%} confidence")
                print(f"    Target: ${pattern['target_price']:.2f}, Stop: ${pattern['stop_loss']:.2f}")
                print(f"    {pattern['description']}")

if __name__ == "__main__":
    main()