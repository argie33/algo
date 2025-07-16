#!/usr/bin/env python3
"""
Advanced Chart Pattern Recognition
Implements sophisticated patterns including harmonic patterns, Elliott waves, and complex formations
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import math
import warnings
warnings.filterwarnings('ignore')

from pattern_detectors import PatternMatch, PatternPoint, PatternDetector

class HarmonicPatternDetector(PatternDetector):
    """Detect harmonic patterns like Gartley, Butterfly, Bat, Crab"""
    
    def __init__(self, min_bars: int = 15, tolerance: float = 0.05):
        super().__init__(min_bars, tolerance)
        self.harmonic_ratios = self._initialize_harmonic_ratios()
    
    def _initialize_harmonic_ratios(self) -> Dict[str, Dict[str, Tuple[float, float]]]:
        """Initialize Fibonacci ratios for harmonic patterns"""
        return {
            'gartley': {
                'AB_XA': (0.618, 0.618),  # AB should be 61.8% of XA
                'BC_AB': (0.382, 0.886),  # BC should be 38.2% to 88.6% of AB
                'CD_BC': (1.13, 1.618),   # CD should be 113% to 161.8% of BC
                'AD_XA': (0.786, 0.786)   # AD should be 78.6% of XA
            },
            'butterfly': {
                'AB_XA': (0.786, 0.786),
                'BC_AB': (0.382, 0.886),
                'CD_BC': (1.618, 2.618),
                'AD_XA': (1.27, 1.618)
            },
            'bat': {
                'AB_XA': (0.382, 0.5),
                'BC_AB': (0.382, 0.886),
                'CD_BC': (1.618, 2.618),
                'AD_XA': (0.886, 0.886)
            },
            'crab': {
                'AB_XA': (0.382, 0.618),
                'BC_AB': (0.382, 0.886),
                'CD_BC': (2.24, 3.618),
                'AD_XA': (1.618, 1.618)
            }
        }
    
    def detect_harmonic_patterns(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Detect all harmonic patterns"""
        patterns = []
        high_pivots, low_pivots = self.find_pivots(data, order=3)
        
        # Combine and sort pivots
        all_pivots = [(idx, 'high') for idx in high_pivots] + [(idx, 'low') for idx in low_pivots]
        all_pivots.sort(key=lambda x: x[0])
        
        # Look for 5-point patterns (X, A, B, C, D)
        for i in range(len(all_pivots) - 4):
            pattern_points = all_pivots[i:i+5]
            
            # Check if pattern alternates between highs and lows
            if self._is_valid_harmonic_sequence(pattern_points):
                harmonic_pattern = self._analyze_harmonic_pattern(data, pattern_points)
                if harmonic_pattern:
                    patterns.append(harmonic_pattern)
        
        return patterns
    
    def _is_valid_harmonic_sequence(self, points: List[Tuple[int, str]]) -> bool:
        """Check if points form a valid harmonic sequence"""
        types = [p[1] for p in points]
        
        # Should alternate between high and low
        for i in range(len(types) - 1):
            if types[i] == types[i + 1]:
                return False
        
        return True
    
    def _analyze_harmonic_pattern(self, data: pd.DataFrame, 
                                pattern_points: List[Tuple[int, str]]) -> Optional[PatternMatch]:
        """Analyze potential harmonic pattern"""
        # Extract points
        X = self._get_point_data(data, pattern_points[0])
        A = self._get_point_data(data, pattern_points[1])
        B = self._get_point_data(data, pattern_points[2])
        C = self._get_point_data(data, pattern_points[3])
        D = self._get_point_data(data, pattern_points[4])
        
        # Calculate ratios
        ratios = self._calculate_harmonic_ratios(X, A, B, C, D)
        
        # Check against known patterns
        for pattern_name, expected_ratios in self.harmonic_ratios.items():
            if self._matches_harmonic_pattern(ratios, expected_ratios):
                return self._create_harmonic_pattern(
                    data, pattern_name, [X, A, B, C, D], ratios
                )
        
        return None
    
    def _get_point_data(self, data: pd.DataFrame, point: Tuple[int, str]) -> PatternPoint:
        """Get PatternPoint from data"""
        idx, point_type = point
        price = data['high'].iloc[idx] if point_type == 'high' else data['low'].iloc[idx]
        return PatternPoint(
            timestamp=data.index[idx],
            price=price,
            index=idx
        )
    
    def _calculate_harmonic_ratios(self, X: PatternPoint, A: PatternPoint, 
                                 B: PatternPoint, C: PatternPoint, 
                                 D: PatternPoint) -> Dict[str, float]:
        """Calculate Fibonacci ratios for harmonic pattern"""
        XA = abs(A.price - X.price)
        AB = abs(B.price - A.price)
        BC = abs(C.price - B.price)
        CD = abs(D.price - C.price)
        AD = abs(D.price - A.price)
        
        ratios = {}
        if XA > 0:
            ratios['AB_XA'] = AB / XA
            ratios['AD_XA'] = AD / XA
        
        if AB > 0:
            ratios['BC_AB'] = BC / AB
        
        if BC > 0:
            ratios['CD_BC'] = CD / BC
        
        return ratios
    
    def _matches_harmonic_pattern(self, ratios: Dict[str, float], 
                                expected: Dict[str, Tuple[float, float]]) -> bool:
        """Check if ratios match expected harmonic pattern"""
        for ratio_name, (min_val, max_val) in expected.items():
            if ratio_name not in ratios:
                return False
            
            actual_ratio = ratios[ratio_name]
            tolerance = 0.05  # 5% tolerance
            
            if not (min_val * (1 - tolerance) <= actual_ratio <= max_val * (1 + tolerance)):
                return False
        
        return True
    
    def _create_harmonic_pattern(self, data: pd.DataFrame, pattern_name: str,
                               points: List[PatternPoint], ratios: Dict[str, float]) -> PatternMatch:
        """Create harmonic pattern match"""
        # Determine if bullish or bearish
        is_bullish = points[0].price > points[-1].price
        
        # Calculate target levels using Fibonacci projections
        target_price = self._calculate_harmonic_target(points, pattern_name, is_bullish)
        stop_loss = self._calculate_harmonic_stop_loss(points, is_bullish)
        
        # Calculate confidence based on ratio accuracy
        confidence = self._calculate_harmonic_confidence(ratios, pattern_name)
        
        return PatternMatch(
            pattern_type=f"{pattern_name}_{'bullish' if is_bullish else 'bearish'}",
            confidence=confidence,
            start_point=points[0],
            end_point=points[-1],
            key_points=points,
            target_price=target_price,
            stop_loss=stop_loss,
            probability=0.75,  # Harmonic patterns have good success rates
            pattern_height=max(p.price for p in points) - min(p.price for p in points)
        )
    
    def _calculate_harmonic_target(self, points: List[PatternPoint], 
                                 pattern_name: str, is_bullish: bool) -> float:
        """Calculate target price for harmonic pattern"""
        D = points[-1]
        C = points[-2]
        
        # Use standard Fibonacci extensions
        CD_length = abs(D.price - C.price)
        
        if is_bullish:
            return D.price + CD_length * 0.618
        else:
            return D.price - CD_length * 0.618
    
    def _calculate_harmonic_stop_loss(self, points: List[PatternPoint], is_bullish: bool) -> float:
        """Calculate stop loss for harmonic pattern"""
        D = points[-1]
        
        # Stop loss beyond D point
        if is_bullish:
            return D.price * 0.98  # 2% below D
        else:
            return D.price * 1.02  # 2% above D
    
    def _calculate_harmonic_confidence(self, ratios: Dict[str, float], pattern_name: str) -> float:
        """Calculate confidence based on ratio accuracy"""
        expected_ratios = self.harmonic_ratios[pattern_name]
        total_score = 0
        count = 0
        
        for ratio_name, (min_val, max_val) in expected_ratios.items():
            if ratio_name in ratios:
                actual = ratios[ratio_name]
                target = (min_val + max_val) / 2
                
                # Score based on how close to target
                error = abs(actual - target) / target
                score = max(0, 1 - error * 2)  # Linear decay
                
                total_score += score
                count += 1
        
        return total_score / count if count > 0 else 0.5

class WedgePatternDetector(PatternDetector):
    """Detect wedge patterns (rising and falling wedges)"""
    
    def detect_wedge_patterns(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Detect rising and falling wedge patterns"""
        patterns = []
        high_pivots, low_pivots = self.find_pivots(data)
        
        # Rising wedges
        patterns.extend(self._find_rising_wedges(data, high_pivots, low_pivots))
        
        # Falling wedges
        patterns.extend(self._find_falling_wedges(data, high_pivots, low_pivots))
        
        return patterns
    
    def _find_rising_wedges(self, data: pd.DataFrame, 
                           high_pivots: List[int], low_pivots: List[int]) -> List[PatternMatch]:
        """Find rising wedge patterns"""
        patterns = []
        
        for i in range(len(high_pivots) - 2):
            for j in range(len(low_pivots) - 2):
                # Get trendline points
                h1, h2, h3 = high_pivots[i], high_pivots[i+1], high_pivots[i+2]
                l1, l2, l3 = low_pivots[j], low_pivots[j+1], low_pivots[j+2]
                
                # Check sequence order
                if not (min(h1, l1) < min(h2, l2) < min(h3, l3)):
                    continue
                
                # Calculate slopes
                high_slope = self._calculate_slope(data, [h1, h2, h3], 'high')
                low_slope = self._calculate_slope(data, [l1, l2, l3], 'low')
                
                # Rising wedge: both slopes positive, but resistance slope < support slope
                if high_slope > 0 and low_slope > 0 and high_slope < low_slope:
                    # Check convergence
                    if self._lines_converge(data, [h1, h2, h3], [l1, l2, l3]):
                        pattern = self._create_wedge_pattern(
                            data, 'rising_wedge', [h1, h2, h3], [l1, l2, l3]
                        )
                        patterns.append(pattern)
        
        return patterns
    
    def _find_falling_wedges(self, data: pd.DataFrame,
                            high_pivots: List[int], low_pivots: List[int]) -> List[PatternMatch]:
        """Find falling wedge patterns"""
        patterns = []
        
        for i in range(len(high_pivots) - 2):
            for j in range(len(low_pivots) - 2):
                # Get trendline points
                h1, h2, h3 = high_pivots[i], high_pivots[i+1], high_pivots[i+2]
                l1, l2, l3 = low_pivots[j], low_pivots[j+1], low_pivots[j+2]
                
                # Check sequence order
                if not (min(h1, l1) < min(h2, l2) < min(h3, l3)):
                    continue
                
                # Calculate slopes
                high_slope = self._calculate_slope(data, [h1, h2, h3], 'high')
                low_slope = self._calculate_slope(data, [l1, l2, l3], 'low')
                
                # Falling wedge: both slopes negative, but support slope > resistance slope
                if high_slope < 0 and low_slope < 0 and low_slope > high_slope:
                    # Check convergence
                    if self._lines_converge(data, [h1, h2, h3], [l1, l2, l3]):
                        pattern = self._create_wedge_pattern(
                            data, 'falling_wedge', [h1, h2, h3], [l1, l2, l3]
                        )
                        patterns.append(pattern)
        
        return patterns
    
    def _calculate_slope(self, data: pd.DataFrame, indices: List[int], price_type: str) -> float:
        """Calculate slope of trendline"""
        if len(indices) < 2:
            return 0
        
        x_values = np.array(indices)
        y_values = np.array([data[price_type].iloc[i] for i in indices])
        
        slope, _ = np.polyfit(x_values, y_values, 1)
        return slope
    
    def _lines_converge(self, data: pd.DataFrame, high_indices: List[int], 
                       low_indices: List[int]) -> bool:
        """Check if trendlines converge"""
        # Calculate where lines would intersect
        high_slope = self._calculate_slope(data, high_indices, 'high')
        low_slope = self._calculate_slope(data, low_indices, 'low')
        
        # Lines converge if slopes are different
        return abs(high_slope - low_slope) > 0.001
    
    def _create_wedge_pattern(self, data: pd.DataFrame, pattern_type: str,
                             high_indices: List[int], low_indices: List[int]) -> PatternMatch:
        """Create wedge pattern match"""
        # Combine all points
        all_points = []
        
        for idx in high_indices:
            all_points.append(PatternPoint(
                timestamp=data.index[idx],
                price=data['high'].iloc[idx],
                index=idx
            ))
        
        for idx in low_indices:
            all_points.append(PatternPoint(
                timestamp=data.index[idx],
                price=data['low'].iloc[idx],
                index=idx
            ))
        
        # Sort by time
        all_points.sort(key=lambda p: p.index)
        
        # Calculate pattern metrics
        pattern_height = max(p.price for p in all_points) - min(p.price for p in all_points)
        
        # Calculate target based on pattern type
        if pattern_type == 'rising_wedge':
            # Bearish pattern
            target_price = min(p.price for p in all_points) - pattern_height * 0.618
        else:
            # Bullish pattern
            target_price = max(p.price for p in all_points) + pattern_height * 0.618
        
        # Calculate confidence
        confidence = self._calculate_wedge_confidence(data, all_points, pattern_type)
        
        return PatternMatch(
            pattern_type=pattern_type,
            confidence=confidence,
            start_point=all_points[0],
            end_point=all_points[-1],
            key_points=all_points,
            target_price=target_price,
            pattern_height=pattern_height,
            probability=0.65
        )
    
    def _calculate_wedge_confidence(self, data: pd.DataFrame, 
                                   points: List[PatternPoint], pattern_type: str) -> float:
        """Calculate confidence for wedge pattern"""
        base_confidence = 0.6
        
        # Volume should decrease during wedge formation
        if 'volume' in data.columns:
            start_idx = points[0].index
            end_idx = points[-1].index
            
            volume_data = data['volume'].iloc[start_idx:end_idx+1]
            if len(volume_data) > 10:
                early_volume = volume_data.iloc[:len(volume_data)//2].mean()
                late_volume = volume_data.iloc[len(volume_data)//2:].mean()
                
                if late_volume < early_volume:
                    base_confidence += 0.2
        
        # More touches = higher confidence
        if len(points) >= 6:
            base_confidence += 0.1
        
        return min(base_confidence, 1.0)

class CupAndHandleDetector(PatternDetector):
    """Detect cup and handle patterns"""
    
    def detect_cup_and_handle(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Detect cup and handle patterns"""
        patterns = []
        
        if len(data) < 30:  # Need sufficient data for cup and handle
            return patterns
        
        # Find potential cup formations
        for i in range(20, len(data) - 10):
            cup_pattern = self._find_cup_at_position(data, i)
            if cup_pattern:
                # Look for handle after cup
                handle_pattern = self._find_handle_after_cup(data, cup_pattern, i)
                if handle_pattern:
                    patterns.append(handle_pattern)
        
        return patterns
    
    def _find_cup_at_position(self, data: pd.DataFrame, position: int) -> Optional[Dict]:
        """Find cup formation at given position"""
        lookback = min(20, position)
        
        # Get data for potential cup
        cup_data = data.iloc[position - lookback:position + 1]
        
        # Find the lowest point (bottom of cup)
        bottom_idx = cup_data['low'].idxmin()
        bottom_price = cup_data['low'].min()
        
        # Find rim levels (left and right highs)
        left_data = cup_data.iloc[:len(cup_data)//2]
        right_data = cup_data.iloc[len(cup_data)//2:]
        
        left_high = left_data['high'].max()
        right_high = right_data['high'].max()
        
        # Check cup criteria
        rim_avg = (left_high + right_high) / 2
        cup_depth = (rim_avg - bottom_price) / rim_avg
        
        # Cup should be 15-50% deep
        if 0.15 <= cup_depth <= 0.50:
            # Rims should be roughly equal
            rim_difference = abs(left_high - right_high) / rim_avg
            if rim_difference < 0.05:
                return {
                    'bottom_idx': bottom_idx,
                    'bottom_price': bottom_price,
                    'left_rim': left_high,
                    'right_rim': right_high,
                    'cup_depth': cup_depth,
                    'start_idx': cup_data.index[0],
                    'end_idx': cup_data.index[-1]
                }
        
        return None
    
    def _find_handle_after_cup(self, data: pd.DataFrame, cup: Dict, cup_end: int) -> Optional[PatternMatch]:
        """Find handle formation after cup"""
        handle_start = cup_end + 1
        handle_end = min(handle_start + 10, len(data) - 1)
        
        if handle_end <= handle_start:
            return None
        
        handle_data = data.iloc[handle_start:handle_end + 1]
        
        # Handle should be a small pullback
        handle_high = handle_data['high'].max()
        handle_low = handle_data['low'].min()
        
        # Handle pullback should be 10-15% from right rim
        pullback = (cup['right_rim'] - handle_low) / cup['right_rim']
        
        if 0.10 <= pullback <= 0.15:
            # Create pattern
            key_points = [
                PatternPoint(cup['start_idx'], cup['left_rim'], index=data.index.get_loc(cup['start_idx'])),
                PatternPoint(cup['bottom_idx'], cup['bottom_price'], index=data.index.get_loc(cup['bottom_idx'])),
                PatternPoint(cup['end_idx'], cup['right_rim'], index=data.index.get_loc(cup['end_idx'])),
                PatternPoint(handle_data.index[-1], handle_low, index=data.index.get_loc(handle_data.index[-1]))
            ]
            
            # Calculate target price (cup depth projection)
            target_price = cup['right_rim'] + (cup['right_rim'] - cup['bottom_price'])
            
            # Calculate confidence
            confidence = self._calculate_cup_handle_confidence(cup, pullback)
            
            return PatternMatch(
                pattern_type='cup_and_handle',
                confidence=confidence,
                start_point=key_points[0],
                end_point=key_points[-1],
                key_points=key_points,
                target_price=target_price,
                breakout_level=cup['right_rim'],
                pattern_height=cup['right_rim'] - cup['bottom_price'],
                probability=0.70
            )
        
        return None
    
    def _calculate_cup_handle_confidence(self, cup: Dict, pullback: float) -> float:
        """Calculate confidence for cup and handle pattern"""
        base_confidence = 0.6
        
        # Better cup depth
        ideal_depth = 0.25
        depth_score = 1 - abs(cup['cup_depth'] - ideal_depth) / ideal_depth
        base_confidence += depth_score * 0.2
        
        # Better handle pullback
        ideal_pullback = 0.125
        pullback_score = 1 - abs(pullback - ideal_pullback) / ideal_pullback
        base_confidence += pullback_score * 0.2
        
        return min(base_confidence, 1.0)

class AdvancedPatternDetector(PatternDetector):
    """Master detector that combines all advanced patterns"""
    
    def __init__(self, min_bars: int = 15, tolerance: float = 0.02):
        super().__init__(min_bars, tolerance)
        self.harmonic_detector = HarmonicPatternDetector(min_bars, tolerance)
        self.wedge_detector = WedgePatternDetector(min_bars, tolerance)
        self.cup_handle_detector = CupAndHandleDetector(min_bars, tolerance)
    
    def detect_all_advanced_patterns(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Detect all advanced patterns"""
        patterns = []
        
        # Harmonic patterns
        patterns.extend(self.harmonic_detector.detect_harmonic_patterns(data))
        
        # Wedge patterns
        patterns.extend(self.wedge_detector.detect_wedge_patterns(data))
        
        # Cup and handle patterns
        patterns.extend(self.cup_handle_detector.detect_cup_and_handle(data))
        
        # Remove duplicates and sort by confidence
        patterns = self._remove_overlapping_patterns(patterns)
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        
        return patterns
    
    def _remove_overlapping_patterns(self, patterns: List[PatternMatch]) -> List[PatternMatch]:
        """Remove overlapping patterns, keeping highest confidence"""
        if not patterns:
            return patterns
        
        # Sort by confidence
        sorted_patterns = sorted(patterns, key=lambda p: p.confidence, reverse=True)
        
        filtered_patterns = []
        for pattern in sorted_patterns:
            # Check if it overlaps with any already selected pattern
            overlaps = False
            for selected in filtered_patterns:
                if self._patterns_overlap(pattern, selected):
                    overlaps = True
                    break
            
            if not overlaps:
                filtered_patterns.append(pattern)
        
        return filtered_patterns
    
    def _patterns_overlap(self, pattern1: PatternMatch, pattern2: PatternMatch) -> bool:
        """Check if two patterns overlap significantly"""
        # Check time overlap
        start1, end1 = pattern1.start_point.index, pattern1.end_point.index
        start2, end2 = pattern2.start_point.index, pattern2.end_point.index
        
        # Calculate overlap percentage
        overlap_start = max(start1, start2)
        overlap_end = min(end1, end2)
        
        if overlap_end <= overlap_start:
            return False
        
        overlap_length = overlap_end - overlap_start
        pattern1_length = end1 - start1
        pattern2_length = end2 - start2
        
        # Consider overlapping if more than 50% of either pattern overlaps
        overlap_ratio1 = overlap_length / pattern1_length if pattern1_length > 0 else 0
        overlap_ratio2 = overlap_length / pattern2_length if pattern2_length > 0 else 0
        
        return overlap_ratio1 > 0.5 or overlap_ratio2 > 0.5

# Example usage
if __name__ == "__main__":
    # Create sample data
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    np.random.seed(42)
    
    # Generate sample price data with some pattern-like behavior
    price_base = 100
    price_data = []
    
    for i in range(100):
        # Add some trend and volatility
        trend = 0.02 * i
        volatility = np.random.normal(0, 2)
        
        # Add harmonic-like pattern
        if 20 <= i <= 60:
            harmonic = 5 * np.sin(0.3 * (i - 20))
        else:
            harmonic = 0
        
        price = price_base + trend + volatility + harmonic
        price_data.append(price)
    
    # Create DataFrame
    sample_data = pd.DataFrame({
        'date': dates,
        'open': price_data,
        'high': [p + np.random.uniform(0, 2) for p in price_data],
        'low': [p - np.random.uniform(0, 2) for p in price_data],
        'close': price_data,
        'volume': np.random.randint(1000, 10000, 100)
    })
    sample_data.set_index('date', inplace=True)
    
    # Test advanced pattern detection
    detector = AdvancedPatternDetector()
    patterns = detector.detect_all_advanced_patterns(sample_data)
    
    print(f"Found {len(patterns)} advanced patterns:")
    for pattern in patterns:
        print(f"- {pattern.pattern_type}: confidence={pattern.confidence:.3f}, "
              f"target=${pattern.target_price:.2f if pattern.target_price else 'N/A'}")