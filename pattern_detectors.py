#!/usr/bin/env python3
"""
Core Pattern Detection Algorithms
Implements foundational pattern recognition methods
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional, NamedTuple
from dataclasses import dataclass
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

@dataclass
class PatternPoint:
    """Single point in a pattern"""
    timestamp: datetime
    price: float
    volume: Optional[float] = None
    index: int = 0
    
@dataclass
class PatternMatch:
    """Complete pattern match result"""
    pattern_type: str
    confidence: float
    start_point: PatternPoint
    end_point: PatternPoint
    key_points: List[PatternPoint]
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    probability: float = 0.0
    risk_reward_ratio: float = 0.0
    pattern_height: float = 0.0
    breakout_level: Optional[float] = None
    
class PatternDetector:
    """Base class for pattern detection algorithms"""
    
    def __init__(self, min_bars: int = 10, tolerance: float = 0.02):
        self.min_bars = min_bars
        self.tolerance = tolerance
        self.patterns = []
        
    def find_pivots(self, data: pd.DataFrame, order: int = 5) -> Tuple[List[int], List[int]]:
        """Find pivot highs and lows"""
        from scipy.signal import argrelextrema
        
        high_pivots = argrelextrema(data['high'].values, np.greater, order=order)[0]
        low_pivots = argrelextrema(data['low'].values, np.less, order=order)[0]
        
        return high_pivots.tolist(), low_pivots.tolist()
    
    def calculate_trendline(self, points: List[PatternPoint]) -> Tuple[float, float]:
        """Calculate trendline slope and intercept"""
        if len(points) < 2:
            return 0.0, 0.0
            
        x = np.array([p.index for p in points])
        y = np.array([p.price for p in points])
        
        slope, intercept = np.polyfit(x, y, 1)
        return slope, intercept
    
    def is_support_resistance(self, data: pd.DataFrame, level: float, 
                            tolerance: float = 0.01, min_touches: int = 2) -> bool:
        """Check if price level acts as support or resistance"""
        touches = 0
        for _, row in data.iterrows():
            if abs(row['high'] - level) / level <= tolerance or \
               abs(row['low'] - level) / level <= tolerance:
                touches += 1
        return touches >= min_touches

class TriangleDetector(PatternDetector):
    """Detect ascending, descending, and symmetrical triangles"""
    
    def detect_triangles(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Find all triangle patterns"""
        patterns = []
        high_pivots, low_pivots = self.find_pivots(data)
        
        if len(high_pivots) < 3 or len(low_pivots) < 3:
            return patterns
            
        # Check for ascending triangles
        patterns.extend(self._find_ascending_triangles(data, high_pivots, low_pivots))
        
        # Check for descending triangles
        patterns.extend(self._find_descending_triangles(data, high_pivots, low_pivots))
        
        # Check for symmetrical triangles
        patterns.extend(self._find_symmetrical_triangles(data, high_pivots, low_pivots))
        
        return patterns
    
    def _find_ascending_triangles(self, data: pd.DataFrame, 
                                high_pivots: List[int], 
                                low_pivots: List[int]) -> List[PatternMatch]:
        """Find ascending triangle patterns"""
        patterns = []
        
        # Look for horizontal resistance with ascending support
        for i in range(len(high_pivots) - 1):
            for j in range(i + 1, len(high_pivots)):
                h1, h2 = high_pivots[i], high_pivots[j]
                
                # Check if highs are roughly equal (horizontal resistance)
                if abs(data['high'].iloc[h1] - data['high'].iloc[h2]) / data['high'].iloc[h1] < self.tolerance:
                    
                    # Find relevant low pivots between the highs
                    relevant_lows = [idx for idx in low_pivots if h1 < idx < h2]
                    
                    if len(relevant_lows) >= 2:
                        # Check if lows are ascending
                        low_prices = [data['low'].iloc[idx] for idx in relevant_lows]
                        if all(low_prices[k] < low_prices[k+1] for k in range(len(low_prices)-1)):
                            
                            pattern = self._create_triangle_pattern(
                                data, 'ascending_triangle', h1, h2, relevant_lows
                            )
                            patterns.append(pattern)
        
        return patterns
    
    def _find_descending_triangles(self, data: pd.DataFrame,
                                 high_pivots: List[int],
                                 low_pivots: List[int]) -> List[PatternMatch]:
        """Find descending triangle patterns"""
        patterns = []
        
        # Look for horizontal support with descending resistance
        for i in range(len(low_pivots) - 1):
            for j in range(i + 1, len(low_pivots)):
                l1, l2 = low_pivots[i], low_pivots[j]
                
                # Check if lows are roughly equal (horizontal support)
                if abs(data['low'].iloc[l1] - data['low'].iloc[l2]) / data['low'].iloc[l1] < self.tolerance:
                    
                    # Find relevant high pivots between the lows
                    relevant_highs = [idx for idx in high_pivots if l1 < idx < l2]
                    
                    if len(relevant_highs) >= 2:
                        # Check if highs are descending
                        high_prices = [data['high'].iloc[idx] for idx in relevant_highs]
                        if all(high_prices[k] > high_prices[k+1] for k in range(len(high_prices)-1)):
                            
                            pattern = self._create_triangle_pattern(
                                data, 'descending_triangle', l1, l2, relevant_highs
                            )
                            patterns.append(pattern)
        
        return patterns
    
    def _find_symmetrical_triangles(self, data: pd.DataFrame,
                                  high_pivots: List[int],
                                  low_pivots: List[int]) -> List[PatternMatch]:
        """Find symmetrical triangle patterns"""
        patterns = []
        
        # Look for converging trendlines
        for i in range(len(high_pivots) - 2):
            for j in range(len(low_pivots) - 2):
                h1, h2 = high_pivots[i], high_pivots[i+1]
                l1, l2 = low_pivots[j], low_pivots[j+1]
                
                # Ensure proper timing sequence
                if not (min(h1, l1) < max(h1, l1) < min(h2, l2) < max(h2, l2)):
                    continue
                
                # Calculate trendline slopes
                high_slope = (data['high'].iloc[h2] - data['high'].iloc[h1]) / (h2 - h1)
                low_slope = (data['low'].iloc[l2] - data['low'].iloc[l1]) / (l2 - l1)
                
                # Check for convergence (descending highs, ascending lows)
                if high_slope < -0.001 and low_slope > 0.001:
                    pattern = self._create_symmetrical_triangle_pattern(
                        data, h1, h2, l1, l2
                    )
                    patterns.append(pattern)
        
        return patterns
    
    def _create_triangle_pattern(self, data: pd.DataFrame, pattern_type: str,
                               start_idx: int, end_idx: int, 
                               pivot_indices: List[int]) -> PatternMatch:
        """Create triangle pattern match object"""
        key_points = []
        
        # Add start and end points
        key_points.append(PatternPoint(
            timestamp=data.index[start_idx],
            price=data['high'].iloc[start_idx] if 'ascending' in pattern_type else data['low'].iloc[start_idx],
            index=start_idx
        ))
        
        # Add pivot points
        for idx in pivot_indices:
            key_points.append(PatternPoint(
                timestamp=data.index[idx],
                price=data['high'].iloc[idx] if idx in self.find_pivots(data)[0] else data['low'].iloc[idx],
                index=idx
            ))
        
        key_points.append(PatternPoint(
            timestamp=data.index[end_idx],
            price=data['high'].iloc[end_idx] if 'ascending' in pattern_type else data['low'].iloc[end_idx],
            index=end_idx
        ))
        
        # Calculate pattern metrics
        pattern_height = max(p.price for p in key_points) - min(p.price for p in key_points)
        confidence = self._calculate_triangle_confidence(data, key_points, pattern_type)
        
        return PatternMatch(
            pattern_type=pattern_type,
            confidence=confidence,
            start_point=key_points[0],
            end_point=key_points[-1],
            key_points=key_points,
            pattern_height=pattern_height,
            probability=0.65 if pattern_type == 'ascending_triangle' else 0.60
        )
    
    def _create_symmetrical_triangle_pattern(self, data: pd.DataFrame,
                                           h1: int, h2: int, l1: int, l2: int) -> PatternMatch:
        """Create symmetrical triangle pattern"""
        key_points = [
            PatternPoint(data.index[h1], data['high'].iloc[h1], index=h1),
            PatternPoint(data.index[l1], data['low'].iloc[l1], index=l1),
            PatternPoint(data.index[h2], data['high'].iloc[h2], index=h2),
            PatternPoint(data.index[l2], data['low'].iloc[l2], index=l2)
        ]
        
        # Sort by time
        key_points.sort(key=lambda p: p.index)
        
        pattern_height = max(p.price for p in key_points) - min(p.price for p in key_points)
        confidence = self._calculate_triangle_confidence(data, key_points, 'symmetrical_triangle')
        
        return PatternMatch(
            pattern_type='symmetrical_triangle',
            confidence=confidence,
            start_point=key_points[0],
            end_point=key_points[-1],
            key_points=key_points,
            pattern_height=pattern_height,
            probability=0.55  # Symmetrical triangles are less directional
        )
    
    def _calculate_triangle_confidence(self, data: pd.DataFrame, 
                                     key_points: List[PatternPoint], 
                                     pattern_type: str) -> float:
        """Calculate confidence score for triangle pattern"""
        base_confidence = 0.5
        
        # Volume analysis
        if 'volume' in data.columns:
            volume_trend = self._analyze_volume_trend(data, key_points)
            base_confidence += volume_trend * 0.2
        
        # Trendline strength
        trendline_strength = self._calculate_trendline_strength(key_points)
        base_confidence += trendline_strength * 0.3
        
        return min(base_confidence, 1.0)
    
    def _analyze_volume_trend(self, data: pd.DataFrame, key_points: List[PatternPoint]) -> float:
        """Analyze volume trend during pattern formation"""
        if len(key_points) < 2:
            return 0.0
            
        start_idx = key_points[0].index
        end_idx = key_points[-1].index
        
        volume_data = data['volume'].iloc[start_idx:end_idx+1]
        
        # Volume should generally decrease during triangle formation
        early_volume = volume_data.iloc[:len(volume_data)//2].mean()
        late_volume = volume_data.iloc[len(volume_data)//2:].mean()
        
        if late_volume < early_volume:
            return 0.5
        return 0.0
    
    def _calculate_trendline_strength(self, key_points: List[PatternPoint]) -> float:
        """Calculate strength of trendlines"""
        if len(key_points) < 3:
            return 0.0
            
        # More touches = stronger trendline
        return min(len(key_points) / 6.0, 1.0)

class HeadAndShouldersDetector(PatternDetector):
    """Detect head and shoulders patterns"""
    
    def detect_head_and_shoulders(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Find head and shoulders patterns"""
        patterns = []
        high_pivots, low_pivots = self.find_pivots(data)
        
        if len(high_pivots) < 3:
            return patterns
            
        # Regular head and shoulders
        patterns.extend(self._find_head_and_shoulders(data, high_pivots, low_pivots))
        
        # Inverse head and shoulders
        patterns.extend(self._find_inverse_head_and_shoulders(data, high_pivots, low_pivots))
        
        return patterns
    
    def _find_head_and_shoulders(self, data: pd.DataFrame,
                               high_pivots: List[int],
                               low_pivots: List[int]) -> List[PatternMatch]:
        """Find regular head and shoulders patterns"""
        patterns = []
        
        for i in range(len(high_pivots) - 2):
            left_shoulder = high_pivots[i]
            head = high_pivots[i + 1]
            right_shoulder = high_pivots[i + 2]
            
            # Check H&S criteria
            ls_price = data['high'].iloc[left_shoulder]
            head_price = data['high'].iloc[head]
            rs_price = data['high'].iloc[right_shoulder]
            
            # Head should be higher than both shoulders
            if head_price > ls_price and head_price > rs_price:
                # Shoulders should be roughly equal
                shoulder_diff = abs(ls_price - rs_price) / ls_price
                if shoulder_diff < self.tolerance * 2:
                    
                    # Find neckline points
                    neckline_points = self._find_neckline_points(
                        data, left_shoulder, head, right_shoulder, low_pivots
                    )
                    
                    if len(neckline_points) >= 2:
                        pattern = self._create_head_shoulders_pattern(
                            data, 'head_and_shoulders', 
                            left_shoulder, head, right_shoulder, neckline_points
                        )
                        patterns.append(pattern)
        
        return patterns
    
    def _find_inverse_head_and_shoulders(self, data: pd.DataFrame,
                                       high_pivots: List[int],
                                       low_pivots: List[int]) -> List[PatternMatch]:
        """Find inverse head and shoulders patterns"""
        patterns = []
        
        for i in range(len(low_pivots) - 2):
            left_shoulder = low_pivots[i]
            head = low_pivots[i + 1]
            right_shoulder = low_pivots[i + 2]
            
            # Check inverse H&S criteria
            ls_price = data['low'].iloc[left_shoulder]
            head_price = data['low'].iloc[head]
            rs_price = data['low'].iloc[right_shoulder]
            
            # Head should be lower than both shoulders
            if head_price < ls_price and head_price < rs_price:
                # Shoulders should be roughly equal
                shoulder_diff = abs(ls_price - rs_price) / ls_price
                if shoulder_diff < self.tolerance * 2:
                    
                    # Find neckline points
                    neckline_points = self._find_neckline_points(
                        data, left_shoulder, head, right_shoulder, high_pivots
                    )
                    
                    if len(neckline_points) >= 2:
                        pattern = self._create_head_shoulders_pattern(
                            data, 'inverse_head_and_shoulders',
                            left_shoulder, head, right_shoulder, neckline_points
                        )
                        patterns.append(pattern)
        
        return patterns
    
    def _find_neckline_points(self, data: pd.DataFrame, 
                            left_shoulder: int, head: int, right_shoulder: int,
                            pivots: List[int]) -> List[int]:
        """Find neckline pivot points"""
        neckline_points = []
        
        # Find pivots between left shoulder and head
        for pivot in pivots:
            if left_shoulder < pivot < head:
                neckline_points.append(pivot)
        
        # Find pivots between head and right shoulder
        for pivot in pivots:
            if head < pivot < right_shoulder:
                neckline_points.append(pivot)
        
        return neckline_points
    
    def _create_head_shoulders_pattern(self, data: pd.DataFrame, pattern_type: str,
                                     left_shoulder: int, head: int, right_shoulder: int,
                                     neckline_points: List[int]) -> PatternMatch:
        """Create head and shoulders pattern match"""
        key_points = []
        
        # Add main pattern points
        if pattern_type == 'head_and_shoulders':
            key_points.extend([
                PatternPoint(data.index[left_shoulder], data['high'].iloc[left_shoulder], index=left_shoulder),
                PatternPoint(data.index[head], data['high'].iloc[head], index=head),
                PatternPoint(data.index[right_shoulder], data['high'].iloc[right_shoulder], index=right_shoulder)
            ])
        else:
            key_points.extend([
                PatternPoint(data.index[left_shoulder], data['low'].iloc[left_shoulder], index=left_shoulder),
                PatternPoint(data.index[head], data['low'].iloc[head], index=head),
                PatternPoint(data.index[right_shoulder], data['low'].iloc[right_shoulder], index=right_shoulder)
            ])
        
        # Add neckline points
        for point in neckline_points:
            price = data['low'].iloc[point] if pattern_type == 'head_and_shoulders' else data['high'].iloc[point]
            key_points.append(PatternPoint(data.index[point], price, index=point))
        
        # Calculate pattern metrics
        pattern_height = max(p.price for p in key_points) - min(p.price for p in key_points)
        confidence = self._calculate_hs_confidence(data, key_points, pattern_type)
        
        # Calculate target price
        if len(neckline_points) >= 2:
            neckline_price = np.mean([data['low'].iloc[p] for p in neckline_points] if pattern_type == 'head_and_shoulders' 
                                   else [data['high'].iloc[p] for p in neckline_points])
            
            if pattern_type == 'head_and_shoulders':
                target_price = neckline_price - pattern_height
            else:
                target_price = neckline_price + pattern_height
        else:
            target_price = None
        
        return PatternMatch(
            pattern_type=pattern_type,
            confidence=confidence,
            start_point=key_points[0],
            end_point=key_points[2],  # Right shoulder
            key_points=key_points,
            target_price=target_price,
            pattern_height=pattern_height,
            probability=0.70  # H&S patterns have good success rates
        )
    
    def _calculate_hs_confidence(self, data: pd.DataFrame,
                               key_points: List[PatternPoint],
                               pattern_type: str) -> float:
        """Calculate confidence for head and shoulders pattern"""
        base_confidence = 0.6
        
        # Volume analysis
        if 'volume' in data.columns:
            volume_score = self._analyze_hs_volume(data, key_points, pattern_type)
            base_confidence += volume_score * 0.2
        
        # Symmetry analysis
        symmetry_score = self._analyze_hs_symmetry(key_points)
        base_confidence += symmetry_score * 0.2
        
        return min(base_confidence, 1.0)
    
    def _analyze_hs_volume(self, data: pd.DataFrame, key_points: List[PatternPoint], pattern_type: str) -> float:
        """Analyze volume pattern for H&S"""
        if len(key_points) < 3:
            return 0.0
            
        # Volume should be highest at the head
        head_idx = key_points[1].index
        left_shoulder_idx = key_points[0].index
        right_shoulder_idx = key_points[2].index
        
        head_volume = data['volume'].iloc[head_idx]
        ls_volume = data['volume'].iloc[left_shoulder_idx]
        rs_volume = data['volume'].iloc[right_shoulder_idx]
        
        if head_volume > ls_volume and head_volume > rs_volume:
            return 0.8
        elif head_volume > max(ls_volume, rs_volume):
            return 0.5
        
        return 0.0
    
    def _analyze_hs_symmetry(self, key_points: List[PatternPoint]) -> float:
        """Analyze symmetry of head and shoulders pattern"""
        if len(key_points) < 3:
            return 0.0
            
        left_shoulder = key_points[0]
        head = key_points[1]
        right_shoulder = key_points[2]
        
        # Time symmetry
        left_time = head.index - left_shoulder.index
        right_time = right_shoulder.index - head.index
        time_symmetry = 1.0 - abs(left_time - right_time) / max(left_time, right_time)
        
        # Price symmetry
        price_symmetry = 1.0 - abs(left_shoulder.price - right_shoulder.price) / max(left_shoulder.price, right_shoulder.price)
        
        return (time_symmetry + price_symmetry) / 2.0

class DoubleTopBottomDetector(PatternDetector):
    """Detect double top and double bottom patterns"""
    
    def detect_double_patterns(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Find double top and double bottom patterns"""
        patterns = []
        high_pivots, low_pivots = self.find_pivots(data)
        
        # Double tops
        patterns.extend(self._find_double_tops(data, high_pivots, low_pivots))
        
        # Double bottoms
        patterns.extend(self._find_double_bottoms(data, high_pivots, low_pivots))
        
        return patterns
    
    def _find_double_tops(self, data: pd.DataFrame,
                        high_pivots: List[int],
                        low_pivots: List[int]) -> List[PatternMatch]:
        """Find double top patterns"""
        patterns = []
        
        for i in range(len(high_pivots) - 1):
            for j in range(i + 1, len(high_pivots)):
                first_top = high_pivots[i]
                second_top = high_pivots[j]
                
                # Check if tops are roughly equal
                first_price = data['high'].iloc[first_top]
                second_price = data['high'].iloc[second_top]
                
                if abs(first_price - second_price) / first_price < self.tolerance:
                    
                    # Find valley between tops
                    valley_candidates = [idx for idx in low_pivots if first_top < idx < second_top]
                    
                    if valley_candidates:
                        valley = min(valley_candidates, key=lambda x: data['low'].iloc[x])
                        valley_price = data['low'].iloc[valley]
                        
                        # Valley should be significantly lower than tops
                        if (first_price - valley_price) / first_price > 0.05:
                            pattern = self._create_double_pattern(
                                data, 'double_top', first_top, second_top, valley
                            )
                            patterns.append(pattern)
        
        return patterns
    
    def _find_double_bottoms(self, data: pd.DataFrame,
                           high_pivots: List[int],
                           low_pivots: List[int]) -> List[PatternMatch]:
        """Find double bottom patterns"""
        patterns = []
        
        for i in range(len(low_pivots) - 1):
            for j in range(i + 1, len(low_pivots)):
                first_bottom = low_pivots[i]
                second_bottom = low_pivots[j]
                
                # Check if bottoms are roughly equal
                first_price = data['low'].iloc[first_bottom]
                second_price = data['low'].iloc[second_bottom]
                
                if abs(first_price - second_price) / first_price < self.tolerance:
                    
                    # Find peak between bottoms
                    peak_candidates = [idx for idx in high_pivots if first_bottom < idx < second_bottom]
                    
                    if peak_candidates:
                        peak = max(peak_candidates, key=lambda x: data['high'].iloc[x])
                        peak_price = data['high'].iloc[peak]
                        
                        # Peak should be significantly higher than bottoms
                        if (peak_price - first_price) / first_price > 0.05:
                            pattern = self._create_double_pattern(
                                data, 'double_bottom', first_bottom, second_bottom, peak
                            )
                            patterns.append(pattern)
        
        return patterns
    
    def _create_double_pattern(self, data: pd.DataFrame, pattern_type: str,
                             first_point: int, second_point: int, middle_point: int) -> PatternMatch:
        """Create double top/bottom pattern match"""
        if pattern_type == 'double_top':
            key_points = [
                PatternPoint(data.index[first_point], data['high'].iloc[first_point], index=first_point),
                PatternPoint(data.index[middle_point], data['low'].iloc[middle_point], index=middle_point),
                PatternPoint(data.index[second_point], data['high'].iloc[second_point], index=second_point)
            ]
        else:
            key_points = [
                PatternPoint(data.index[first_point], data['low'].iloc[first_point], index=first_point),
                PatternPoint(data.index[middle_point], data['high'].iloc[middle_point], index=middle_point),
                PatternPoint(data.index[second_point], data['low'].iloc[second_point], index=second_point)
            ]
        
        pattern_height = max(p.price for p in key_points) - min(p.price for p in key_points)
        confidence = self._calculate_double_confidence(data, key_points, pattern_type)
        
        # Calculate target price
        if pattern_type == 'double_top':
            target_price = key_points[1].price - pattern_height
        else:
            target_price = key_points[1].price + pattern_height
        
        return PatternMatch(
            pattern_type=pattern_type,
            confidence=confidence,
            start_point=key_points[0],
            end_point=key_points[2],
            key_points=key_points,
            target_price=target_price,
            pattern_height=pattern_height,
            probability=0.65
        )
    
    def _calculate_double_confidence(self, data: pd.DataFrame,
                                   key_points: List[PatternPoint],
                                   pattern_type: str) -> float:
        """Calculate confidence for double patterns"""
        base_confidence = 0.6
        
        # Volume analysis
        if 'volume' in data.columns:
            volume_score = self._analyze_double_volume(data, key_points, pattern_type)
            base_confidence += volume_score * 0.2
        
        # Price equality
        first_price = key_points[0].price
        second_price = key_points[2].price
        price_equality = 1.0 - abs(first_price - second_price) / max(first_price, second_price)
        base_confidence += price_equality * 0.2
        
        return min(base_confidence, 1.0)
    
    def _analyze_double_volume(self, data: pd.DataFrame, key_points: List[PatternPoint], pattern_type: str) -> float:
        """Analyze volume for double patterns"""
        if len(key_points) < 3:
            return 0.0
            
        first_volume = data['volume'].iloc[key_points[0].index]
        second_volume = data['volume'].iloc[key_points[2].index]
        
        # Second formation should have lower volume
        if second_volume < first_volume:
            return 0.8
        
        return 0.3