#!/usr/bin/env python3
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, argrelextrema
from scipy.stats import linregress
from sklearn.preprocessing import StandardScaler
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

@dataclass
class Pattern:
    name: str
    start_idx: int
    end_idx: int
    confidence: float
    stage: str  # 'early', 'forming', 'complete'
    breakout_level: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None

class AdvancedPatternRecognition:
    def __init__(self, lookback_period: int = 100):
        self.lookback_period = lookback_period
        self.min_pattern_bars = 5
        self.patterns_found = []
        
    def find_all_patterns(self, df: pd.DataFrame) -> List[Pattern]:
        """Main method to find all patterns including early formations"""
        self.df = df.copy()
        self.patterns_found = []
        
        # Find pivot points first
        self.find_pivots()
        
        # Classic patterns
        self.find_head_and_shoulders()
        self.find_inverse_head_and_shoulders()
        self.find_double_tops_bottoms()
        self.find_triple_tops_bottoms()
        self.find_triangles()
        self.find_wedges()
        self.find_flags_pennants()
        self.find_cup_and_handle()
        self.find_rounding_patterns()
        
        # Advanced patterns
        self.find_harmonic_patterns()
        self.find_elliott_waves()
        self.find_wyckoff_patterns()
        
        # Early detection
        self.detect_emerging_patterns()
        
        return self.patterns_found
    
    def find_pivots(self):
        """Find pivot highs and lows using multiple methods"""
        # Method 1: Local extrema
        high_pivots = argrelextrema(self.df['high'].values, np.greater, order=5)[0]
        low_pivots = argrelextrema(self.df['low'].values, np.less, order=5)[0]
        
        # Method 2: Fractals (5-bar pattern)
        fractals_high = []
        fractals_low = []
        for i in range(2, len(self.df) - 2):
            if (self.df['high'].iloc[i] > self.df['high'].iloc[i-1] and 
                self.df['high'].iloc[i] > self.df['high'].iloc[i-2] and
                self.df['high'].iloc[i] > self.df['high'].iloc[i+1] and 
                self.df['high'].iloc[i] > self.df['high'].iloc[i+2]):
                fractals_high.append(i)
                
            if (self.df['low'].iloc[i] < self.df['low'].iloc[i-1] and 
                self.df['low'].iloc[i] < self.df['low'].iloc[i-2] and
                self.df['low'].iloc[i] < self.df['low'].iloc[i+1] and 
                self.df['low'].iloc[i] < self.df['low'].iloc[i+2]):
                fractals_low.append(i)
        
        # Combine methods
        self.high_pivots = sorted(list(set(high_pivots) | set(fractals_high)))
        self.low_pivots = sorted(list(set(low_pivots) | set(fractals_low)))
        
    def find_head_and_shoulders(self):
        """Find H&S and inverse H&S patterns including early stage"""
        if len(self.high_pivots) < 5:
            return
            
        for i in range(len(self.high_pivots) - 4):
            # Get 5 consecutive high pivots
            pivots = self.high_pivots[i:i+5]
            left_shoulder = self.df['high'].iloc[pivots[0]]
            left_valley = self.df['low'].iloc[pivots[1]]
            head = self.df['high'].iloc[pivots[2]]
            right_valley = self.df['low'].iloc[pivots[3]]
            right_shoulder = self.df['high'].iloc[pivots[4]]
            
            # Check H&S criteria
            if (head > left_shoulder and head > right_shoulder and
                abs(left_shoulder - right_shoulder) / left_shoulder < 0.03 and
                abs(left_valley - right_valley) / left_valley < 0.05):
                
                # Calculate neckline
                neckline = (left_valley + right_valley) / 2
                
                # Determine pattern stage
                current_idx = len(self.df) - 1
                if current_idx - pivots[4] < 5:
                    stage = 'complete'
                elif current_idx - pivots[3] < 5:
                    stage = 'forming'
                else:
                    stage = 'early'
                
                # Calculate confidence based on symmetry and volume
                symmetry_score = 1 - abs(left_shoulder - right_shoulder) / left_shoulder
                volume_score = self.calculate_volume_confirmation(pivots[0], pivots[4])
                confidence = (symmetry_score + volume_score) / 2
                
                pattern = Pattern(
                    name='Head and Shoulders',
                    start_idx=pivots[0],
                    end_idx=pivots[4],
                    confidence=confidence,
                    stage=stage,
                    breakout_level=neckline,
                    target_price=neckline - (head - neckline),
                    stop_loss=right_shoulder
                )
                self.patterns_found.append(pattern)
    
    def find_triangles(self):
        """Find ascending, descending, and symmetrical triangles"""
        if len(self.high_pivots) < 3 or len(self.low_pivots) < 3:
            return
            
        # Look for converging trendlines
        for window in range(20, self.lookback_period, 5):
            end_idx = len(self.df) - 1
            start_idx = max(0, end_idx - window)
            
            # Get pivots in window
            window_highs = [p for p in self.high_pivots if start_idx <= p <= end_idx]
            window_lows = [p for p in self.low_pivots if start_idx <= p <= end_idx]
            
            if len(window_highs) >= 2 and len(window_lows) >= 2:
                # Fit trendlines
                high_slope, high_intercept = self.fit_trendline(window_highs, 'high')
                low_slope, low_intercept = self.fit_trendline(window_lows, 'low')
                
                # Check for triangle patterns
                if abs(high_slope) < 0.001 and low_slope > 0.001:
                    # Ascending triangle
                    self.add_triangle_pattern('Ascending Triangle', start_idx, end_idx, 
                                            high_slope, low_slope, high_intercept)
                elif high_slope < -0.001 and abs(low_slope) < 0.001:
                    # Descending triangle
                    self.add_triangle_pattern('Descending Triangle', start_idx, end_idx,
                                            high_slope, low_slope, low_intercept)
                elif high_slope < -0.001 and low_slope > 0.001:
                    # Symmetrical triangle
                    self.add_triangle_pattern('Symmetrical Triangle', start_idx, end_idx,
                                            high_slope, low_slope, None)
    
    def find_harmonic_patterns(self):
        """Find Gartley, Butterfly, Bat, and Crab patterns"""
        if len(self.high_pivots) < 5 or len(self.low_pivots) < 5:
            return
            
        # Combine and sort all pivots
        all_pivots = [(p, 'high') for p in self.high_pivots] + [(p, 'low') for p in self.low_pivots]
        all_pivots.sort(key=lambda x: x[0])
        
        if len(all_pivots) < 5:
            return
            
        for i in range(len(all_pivots) - 4):
            pivots = all_pivots[i:i+5]
            
            # Get XABCD points
            X = self.df['high' if pivots[0][1] == 'high' else 'low'].iloc[pivots[0][0]]
            A = self.df['high' if pivots[1][1] == 'high' else 'low'].iloc[pivots[1][0]]
            B = self.df['high' if pivots[2][1] == 'high' else 'low'].iloc[pivots[2][0]]
            C = self.df['high' if pivots[3][1] == 'high' else 'low'].iloc[pivots[3][0]]
            D = self.df['high' if pivots[4][1] == 'high' else 'low'].iloc[pivots[4][0]]
            
            # Calculate Fibonacci ratios
            XA = abs(A - X)
            AB = abs(B - A)
            BC = abs(C - B)
            CD = abs(D - C)
            
            if XA == 0 or AB == 0 or BC == 0:
                continue
                
            AB_XA = AB / XA
            BC_AB = BC / AB
            CD_BC = CD / BC
            
            # Check for Gartley pattern
            if (0.618 - 0.05 <= AB_XA <= 0.618 + 0.05 and
                0.382 - 0.05 <= BC_AB <= 0.886 + 0.05):
                
                pattern = Pattern(
                    name='Gartley Pattern',
                    start_idx=pivots[0][0],
                    end_idx=pivots[4][0],
                    confidence=0.8,
                    stage='complete' if pivots[4][0] >= len(self.df) - 5 else 'forming',
                    target_price=D + (0.618 * XA if pivots[0][1] == 'low' else -0.618 * XA)
                )
                self.patterns_found.append(pattern)
    
    def detect_emerging_patterns(self):
        """Detect patterns in early formation stages using ML-like approach"""
        window = 20
        
        for i in range(window, len(self.df)):
            segment = self.df.iloc[i-window:i]
            
            # Extract features
            features = self.extract_pattern_features(segment)
            
            # Check for early pattern formations
            if self.is_early_head_shoulders(features):
                pattern = Pattern(
                    name='Head and Shoulders (Emerging)',
                    start_idx=i-window,
                    end_idx=i,
                    confidence=0.6,
                    stage='early'
                )
                self.patterns_found.append(pattern)
            
            if self.is_early_triangle(features):
                pattern = Pattern(
                    name='Triangle (Emerging)',
                    start_idx=i-window,
                    end_idx=i,
                    confidence=0.65,
                    stage='early'
                )
                self.patterns_found.append(pattern)
    
    def extract_pattern_features(self, segment: pd.DataFrame) -> Dict:
        """Extract features for pattern detection"""
        features = {}
        
        # Price features
        features['price_range'] = segment['high'].max() - segment['low'].min()
        features['price_volatility'] = segment['close'].std()
        features['price_trend'] = linregress(range(len(segment)), segment['close'])[0]
        
        # Volume features
        if 'volume' in segment.columns:
            features['volume_trend'] = linregress(range(len(segment)), segment['volume'])[0]
            features['volume_spike'] = segment['volume'].max() / segment['volume'].mean()
        
        # Pattern-specific features
        highs = find_peaks(segment['high'].values, distance=3)[0]
        lows = find_peaks(-segment['low'].values, distance=3)[0]
        
        features['num_peaks'] = len(highs)
        features['num_troughs'] = len(lows)
        
        if len(highs) >= 2:
            features['high_trend'] = linregress(highs, segment['high'].iloc[highs])[0]
        
        if len(lows) >= 2:
            features['low_trend'] = linregress(lows, segment['low'].iloc[lows])[0]
        
        return features
    
    def calculate_volume_confirmation(self, start_idx: int, end_idx: int) -> float:
        """Calculate volume confirmation score for pattern"""
        if 'volume' not in self.df.columns:
            return 0.5
            
        pattern_volume = self.df['volume'].iloc[start_idx:end_idx+1]
        avg_volume = self.df['volume'].iloc[max(0, start_idx-50):start_idx].mean()
        
        if avg_volume == 0:
            return 0.5
            
        volume_ratio = pattern_volume.mean() / avg_volume
        return min(1.0, volume_ratio / 2)  # Normalize to 0-1
    
    def fit_trendline(self, pivot_indices: List[int], price_type: str) -> Tuple[float, float]:
        """Fit trendline to pivot points"""
        if len(pivot_indices) < 2:
            return 0, 0
            
        x = np.array(pivot_indices)
        y = np.array([self.df[price_type].iloc[i] for i in pivot_indices])
        
        slope, intercept, _, _, _ = linregress(x, y)
        return slope, intercept
    
    def add_triangle_pattern(self, name: str, start: int, end: int, 
                           high_slope: float, low_slope: float, breakout: Optional[float]):
        """Add triangle pattern to results"""
        confidence = 0.7
        if abs(high_slope) < 0.0005 or abs(low_slope) < 0.0005:
            confidence += 0.1  # Horizontal line increases confidence
            
        pattern = Pattern(
            name=name,
            start_idx=start,
            end_idx=end,
            confidence=confidence,
            stage='forming' if end >= len(self.df) - 10 else 'complete',
            breakout_level=breakout
        )
        self.patterns_found.append(pattern)
    
    def is_early_head_shoulders(self, features: Dict) -> bool:
        """Check if features indicate early H&S formation"""
        return (features.get('num_peaks', 0) >= 2 and
                features.get('num_troughs', 0) >= 1 and
                features.get('high_trend', 0) < -0.001 and
                features.get('volume_spike', 1) > 1.5)
    
    def is_early_triangle(self, features: Dict) -> bool:
        """Check if features indicate early triangle formation"""
        return (features.get('num_peaks', 0) >= 2 and
                features.get('num_troughs', 0) >= 2 and
                abs(features.get('price_trend', 0)) < 0.001 and
                features.get('price_volatility', 1) < features.get('price_range', 1) * 0.3)
    
    def find_double_tops_bottoms(self):
        """Find double top and double bottom patterns"""
        # Implementation for double tops/bottoms
        pass
    
    def find_triple_tops_bottoms(self):
        """Find triple top and triple bottom patterns"""
        # Implementation for triple tops/bottoms
        pass
    
    def find_wedges(self):
        """Find rising and falling wedge patterns"""
        # Implementation for wedges
        pass
    
    def find_flags_pennants(self):
        """Find flag and pennant patterns"""
        # Implementation for flags and pennants
        pass
    
    def find_cup_and_handle(self):
        """Find cup and handle patterns"""
        # Implementation for cup and handle
        pass
    
    def find_rounding_patterns(self):
        """Find rounding top and bottom patterns"""
        # Implementation for rounding patterns
        pass
    
    def find_elliott_waves(self):
        """Find Elliott Wave patterns"""
        # Implementation for Elliott waves
        pass
    
    def find_wyckoff_patterns(self):
        """Find Wyckoff accumulation and distribution patterns"""
        # Implementation for Wyckoff patterns
        pass
    
    def find_inverse_head_and_shoulders(self):
        """Find inverse head and shoulders patterns"""
        # Implementation similar to H&S but with inverted logic
        pass


def analyze_patterns(df: pd.DataFrame, symbol: str = '') -> Dict:
    """Main function to analyze patterns in price data"""
    recognizer = AdvancedPatternRecognition()
    patterns = recognizer.find_all_patterns(df)
    
    # Sort by confidence and recency
    patterns.sort(key=lambda p: (p.confidence, -p.end_idx), reverse=True)
    
    # Create summary
    summary = {
        'symbol': symbol,
        'total_patterns': len(patterns),
        'high_confidence': len([p for p in patterns if p.confidence >= 0.8]),
        'emerging': len([p for p in patterns if p.stage == 'early']),
        'patterns': []
    }
    
    for pattern in patterns[:10]:  # Top 10 patterns
        summary['patterns'].append({
            'name': pattern.name,
            'confidence': round(pattern.confidence, 2),
            'stage': pattern.stage,
            'start_date': df.index[pattern.start_idx] if hasattr(df.index, '__getitem__') else pattern.start_idx,
            'end_date': df.index[pattern.end_idx] if hasattr(df.index, '__getitem__') else pattern.end_idx,
            'breakout_level': pattern.breakout_level,
            'target_price': pattern.target_price,
            'stop_loss': pattern.stop_loss
        })
    
    return summary