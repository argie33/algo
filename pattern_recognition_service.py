#!/usr/bin/env python3
"""
Pattern Recognition Service
Comprehensive pattern detection system with scoring and validation
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import json
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

from pattern_detectors import (
    PatternMatch, PatternPoint, PatternDetector,
    TriangleDetector, HeadAndShouldersDetector, DoubleTopBottomDetector
)

@dataclass
class PatternScores:
    """Comprehensive pattern scoring metrics"""
    technical_score: float
    volume_score: float
    trend_score: float
    breakout_score: float
    risk_score: float
    overall_score: float
    confidence_level: str  # 'low', 'medium', 'high'

@dataclass
class PatternSignal:
    """Trading signal based on pattern"""
    signal_type: str  # 'buy', 'sell', 'hold'
    strength: float  # 0-1
    entry_price: float
    target_price: Optional[float]
    stop_loss: Optional[float]
    risk_reward_ratio: float
    time_horizon: str  # 'short', 'medium', 'long'

class PatternRecognitionService:
    """Main pattern recognition service"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or self._default_config()
        self.detectors = self._initialize_detectors()
        self.logger = logging.getLogger(__name__)
        
    def _default_config(self) -> Dict[str, Any]:
        """Default configuration"""
        return {
            'min_confidence': 0.6,
            'min_bars': 10,
            'tolerance': 0.02,
            'volume_weight': 0.3,
            'trend_weight': 0.4,
            'breakout_weight': 0.3,
            'parallel_processing': True,
            'max_workers': 4
        }
    
    def _initialize_detectors(self) -> Dict[str, PatternDetector]:
        """Initialize all pattern detectors"""
        return {
            'triangle': TriangleDetector(
                min_bars=self.config['min_bars'],
                tolerance=self.config['tolerance']
            ),
            'head_shoulders': HeadAndShouldersDetector(
                min_bars=self.config['min_bars'],
                tolerance=self.config['tolerance']
            ),
            'double_patterns': DoubleTopBottomDetector(
                min_bars=self.config['min_bars'],
                tolerance=self.config['tolerance']
            )
        }
    
    def analyze_symbol(self, symbol: str, data: pd.DataFrame) -> Dict[str, Any]:
        """Comprehensive pattern analysis for a symbol"""
        try:
            # Detect all patterns
            patterns = self.detect_all_patterns(data)
            
            # Score patterns
            scored_patterns = []
            for pattern in patterns:
                scores = self.calculate_pattern_scores(pattern, data)
                signal = self.generate_trading_signal(pattern, scores, data)
                
                scored_patterns.append({
                    'pattern': pattern,
                    'scores': scores,
                    'signal': signal
                })
            
            # Filter by confidence
            high_confidence_patterns = [
                p for p in scored_patterns 
                if p['scores'].overall_score >= self.config['min_confidence']
            ]
            
            # Generate summary
            summary = self.generate_analysis_summary(symbol, high_confidence_patterns, data)
            
            return {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'patterns': high_confidence_patterns,
                'summary': summary,
                'raw_patterns': patterns
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing {symbol}: {str(e)}")
            return {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'patterns': [],
                'summary': {}
            }
    
    def detect_all_patterns(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Detect all patterns using all available detectors"""
        all_patterns = []
        
        if self.config['parallel_processing']:
            with ThreadPoolExecutor(max_workers=self.config['max_workers']) as executor:
                futures = {}
                
                # Submit detection tasks
                for name, detector in self.detectors.items():
                    if name == 'triangle':
                        futures[executor.submit(detector.detect_triangles, data)] = name
                    elif name == 'head_shoulders':
                        futures[executor.submit(detector.detect_head_and_shoulders, data)] = name
                    elif name == 'double_patterns':
                        futures[executor.submit(detector.detect_double_patterns, data)] = name
                
                # Collect results
                for future in as_completed(futures):
                    detector_name = futures[future]
                    try:
                        patterns = future.result()
                        all_patterns.extend(patterns)
                        self.logger.debug(f"{detector_name} found {len(patterns)} patterns")
                    except Exception as e:
                        self.logger.error(f"Error in {detector_name}: {str(e)}")
        else:
            # Sequential processing
            for name, detector in self.detectors.items():
                try:
                    if name == 'triangle':
                        patterns = detector.detect_triangles(data)
                    elif name == 'head_shoulders':
                        patterns = detector.detect_head_and_shoulders(data)
                    elif name == 'double_patterns':
                        patterns = detector.detect_double_patterns(data)
                    else:
                        patterns = []
                    
                    all_patterns.extend(patterns)
                    self.logger.debug(f"{name} found {len(patterns)} patterns")
                except Exception as e:
                    self.logger.error(f"Error in {name}: {str(e)}")
        
        return all_patterns
    
    def calculate_pattern_scores(self, pattern: PatternMatch, data: pd.DataFrame) -> PatternScores:
        """Calculate comprehensive scores for a pattern"""
        # Technical score (based on pattern quality)
        technical_score = self._calculate_technical_score(pattern, data)
        
        # Volume score
        volume_score = self._calculate_volume_score(pattern, data)
        
        # Trend score
        trend_score = self._calculate_trend_score(pattern, data)
        
        # Breakout score
        breakout_score = self._calculate_breakout_score(pattern, data)
        
        # Risk score
        risk_score = self._calculate_risk_score(pattern, data)
        
        # Overall weighted score
        overall_score = (
            technical_score * 0.3 +
            volume_score * self.config['volume_weight'] +
            trend_score * self.config['trend_weight'] +
            breakout_score * self.config['breakout_weight'] +
            risk_score * 0.1
        )
        
        # Confidence level
        if overall_score >= 0.8:
            confidence_level = 'high'
        elif overall_score >= 0.6:
            confidence_level = 'medium'
        else:
            confidence_level = 'low'
        
        return PatternScores(
            technical_score=technical_score,
            volume_score=volume_score,
            trend_score=trend_score,
            breakout_score=breakout_score,
            risk_score=risk_score,
            overall_score=overall_score,
            confidence_level=confidence_level
        )
    
    def _calculate_technical_score(self, pattern: PatternMatch, data: pd.DataFrame) -> float:
        """Calculate technical quality score"""
        score = pattern.confidence
        
        # Pattern completeness
        if pattern.end_point.index == len(data) - 1:
            score += 0.1  # Recent pattern
        
        # Pattern size (larger patterns are more significant)
        pattern_duration = pattern.end_point.index - pattern.start_point.index
        if pattern_duration > 20:
            score += 0.1
        
        # Pattern height significance
        if pattern.pattern_height / data['close'].iloc[-1] > 0.05:
            score += 0.1
        
        return min(score, 1.0)
    
    def _calculate_volume_score(self, pattern: PatternMatch, data: pd.DataFrame) -> float:
        """Calculate volume-based score"""
        if 'volume' not in data.columns:
            return 0.5  # Neutral if no volume data
        
        start_idx = pattern.start_point.index
        end_idx = pattern.end_point.index
        
        # Volume during pattern formation
        pattern_volume = data['volume'].iloc[start_idx:end_idx+1].mean()
        
        # Average volume before pattern
        pre_pattern_volume = data['volume'].iloc[max(0, start_idx-20):start_idx].mean()
        
        if pre_pattern_volume > 0:
            volume_ratio = pattern_volume / pre_pattern_volume
            
            # Higher volume during pattern formation is generally positive
            if volume_ratio > 1.2:
                return 0.8
            elif volume_ratio > 1.0:
                return 0.6
            else:
                return 0.4
        
        return 0.5
    
    def _calculate_trend_score(self, pattern: PatternMatch, data: pd.DataFrame) -> float:
        """Calculate trend alignment score"""
        # Calculate trend before pattern
        lookback = min(50, pattern.start_point.index)
        if lookback < 10:
            return 0.5
        
        pre_pattern_data = data.iloc[pattern.start_point.index - lookback:pattern.start_point.index]
        
        # Simple trend calculation
        trend_slope = (pre_pattern_data['close'].iloc[-1] - pre_pattern_data['close'].iloc[0]) / lookback
        
        # Bullish patterns in uptrends, bearish patterns in downtrends get higher scores
        if pattern.pattern_type in ['ascending_triangle', 'inverse_head_and_shoulders', 'double_bottom']:
            return 0.8 if trend_slope > 0 else 0.4
        elif pattern.pattern_type in ['descending_triangle', 'head_and_shoulders', 'double_top']:
            return 0.8 if trend_slope < 0 else 0.4
        else:
            return 0.6  # Neutral patterns
    
    def _calculate_breakout_score(self, pattern: PatternMatch, data: pd.DataFrame) -> float:
        """Calculate breakout potential score"""
        # Check if pattern is near completion
        current_price = data['close'].iloc[-1]
        
        if pattern.breakout_level:
            distance_to_breakout = abs(current_price - pattern.breakout_level) / current_price
            
            # Closer to breakout = higher score
            if distance_to_breakout < 0.02:
                return 0.9
            elif distance_to_breakout < 0.05:
                return 0.7
            else:
                return 0.5
        
        # Check if price is near pattern boundaries
        max_price = max(p.price for p in pattern.key_points)
        min_price = min(p.price for p in pattern.key_points)
        
        if current_price >= max_price * 0.98 or current_price <= min_price * 1.02:
            return 0.8
        
        return 0.5
    
    def _calculate_risk_score(self, pattern: PatternMatch, data: pd.DataFrame) -> float:
        """Calculate risk-adjusted score"""
        if pattern.target_price and pattern.stop_loss:
            risk_reward = abs(pattern.target_price - data['close'].iloc[-1]) / abs(pattern.stop_loss - data['close'].iloc[-1])
            
            # Higher risk-reward ratio = better score
            if risk_reward >= 3.0:
                return 1.0
            elif risk_reward >= 2.0:
                return 0.8
            elif risk_reward >= 1.5:
                return 0.6
            else:
                return 0.4
        
        return 0.5
    
    def generate_trading_signal(self, pattern: PatternMatch, scores: PatternScores, data: pd.DataFrame) -> PatternSignal:
        """Generate trading signal based on pattern and scores"""
        current_price = data['close'].iloc[-1]
        
        # Determine signal type
        if pattern.pattern_type in ['ascending_triangle', 'inverse_head_and_shoulders', 'double_bottom']:
            signal_type = 'buy'
        elif pattern.pattern_type in ['descending_triangle', 'head_and_shoulders', 'double_top']:
            signal_type = 'sell'
        else:
            signal_type = 'hold'
        
        # Signal strength based on overall score
        strength = scores.overall_score
        
        # Entry price
        entry_price = current_price
        
        # Target and stop loss
        target_price = pattern.target_price
        stop_loss = pattern.stop_loss
        
        # Calculate risk-reward ratio
        if target_price and stop_loss:
            risk_reward_ratio = abs(target_price - entry_price) / abs(stop_loss - entry_price)
        else:
            risk_reward_ratio = 0.0
        
        # Time horizon based on pattern duration
        pattern_duration = pattern.end_point.index - pattern.start_point.index
        if pattern_duration < 10:
            time_horizon = 'short'
        elif pattern_duration < 30:
            time_horizon = 'medium'
        else:
            time_horizon = 'long'
        
        return PatternSignal(
            signal_type=signal_type,
            strength=strength,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            risk_reward_ratio=risk_reward_ratio,
            time_horizon=time_horizon
        )
    
    def generate_analysis_summary(self, symbol: str, patterns: List[Dict], data: pd.DataFrame) -> Dict[str, Any]:
        """Generate summary of pattern analysis"""
        if not patterns:
            return {
                'total_patterns': 0,
                'recommendation': 'hold',
                'confidence': 0.0,
                'key_insights': ['No significant patterns detected']
            }
        
        # Count patterns by type
        pattern_counts = {}
        for p in patterns:
            pattern_type = p['pattern'].pattern_type
            pattern_counts[pattern_type] = pattern_counts.get(pattern_type, 0) + 1
        
        # Find highest scoring pattern
        best_pattern = max(patterns, key=lambda p: p['scores'].overall_score)
        
        # Generate recommendation
        buy_signals = sum(1 for p in patterns if p['signal'].signal_type == 'buy')
        sell_signals = sum(1 for p in patterns if p['signal'].signal_type == 'sell')
        
        if buy_signals > sell_signals:
            recommendation = 'buy'
        elif sell_signals > buy_signals:
            recommendation = 'sell'
        else:
            recommendation = 'hold'
        
        # Overall confidence
        avg_confidence = np.mean([p['scores'].overall_score for p in patterns])
        
        # Key insights
        insights = []
        insights.append(f"Found {len(patterns)} significant patterns")
        insights.append(f"Strongest pattern: {best_pattern['pattern'].pattern_type}")
        insights.append(f"Average confidence: {avg_confidence:.2f}")
        
        if best_pattern['pattern'].target_price:
            insights.append(f"Primary target: ${best_pattern['pattern'].target_price:.2f}")
        
        return {
            'total_patterns': len(patterns),
            'pattern_counts': pattern_counts,
            'recommendation': recommendation,
            'confidence': avg_confidence,
            'best_pattern': best_pattern['pattern'].pattern_type,
            'key_insights': insights,
            'current_price': data['close'].iloc[-1],
            'analysis_date': datetime.now().isoformat()
        }
    
    def batch_analyze(self, symbols: List[str], data_provider_func) -> Dict[str, Dict[str, Any]]:
        """Analyze multiple symbols in batch"""
        results = {}
        
        if self.config['parallel_processing']:
            with ThreadPoolExecutor(max_workers=self.config['max_workers']) as executor:
                futures = {}
                
                for symbol in symbols:
                    try:
                        data = data_provider_func(symbol)
                        if data is not None and not data.empty:
                            futures[executor.submit(self.analyze_symbol, symbol, data)] = symbol
                    except Exception as e:
                        self.logger.error(f"Error getting data for {symbol}: {str(e)}")
                        results[symbol] = {'error': str(e)}
                
                for future in as_completed(futures):
                    symbol = futures[future]
                    try:
                        result = future.result()
                        results[symbol] = result
                    except Exception as e:
                        self.logger.error(f"Error analyzing {symbol}: {str(e)}")
                        results[symbol] = {'error': str(e)}
        else:
            for symbol in symbols:
                try:
                    data = data_provider_func(symbol)
                    if data is not None and not data.empty:
                        results[symbol] = self.analyze_symbol(symbol, data)
                    else:
                        results[symbol] = {'error': 'No data available'}
                except Exception as e:
                    self.logger.error(f"Error analyzing {symbol}: {str(e)}")
                    results[symbol] = {'error': str(e)}
        
        return results
    
    def export_results(self, results: Dict[str, Any], format: str = 'json') -> str:
        """Export analysis results"""
        if format == 'json':
            return json.dumps(results, indent=2, default=str)
        elif format == 'csv':
            # Convert to CSV format
            csv_data = []
            for symbol, data in results.items():
                if 'patterns' in data:
                    for pattern_data in data['patterns']:
                        pattern = pattern_data['pattern']
                        scores = pattern_data['scores']
                        signal = pattern_data['signal']
                        
                        csv_data.append({
                            'symbol': symbol,
                            'pattern_type': pattern.pattern_type,
                            'confidence': pattern.confidence,
                            'overall_score': scores.overall_score,
                            'signal_type': signal.signal_type,
                            'signal_strength': signal.strength,
                            'target_price': pattern.target_price,
                            'stop_loss': pattern.stop_loss,
                            'risk_reward_ratio': signal.risk_reward_ratio
                        })
            
            if csv_data:
                df = pd.DataFrame(csv_data)
                return df.to_csv(index=False)
            else:
                return "No patterns found"
        
        return str(results)

# Example usage and testing
if __name__ == "__main__":
    # Example configuration
    config = {
        'min_confidence': 0.6,
        'min_bars': 10,
        'tolerance': 0.02,
        'volume_weight': 0.3,
        'trend_weight': 0.4,
        'breakout_weight': 0.3,
        'parallel_processing': True,
        'max_workers': 4
    }
    
    service = PatternRecognitionService(config)
    
    # Example with sample data
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    sample_data = pd.DataFrame({
        'date': dates,
        'open': np.random.randn(100).cumsum() + 100,
        'high': np.random.randn(100).cumsum() + 105,
        'low': np.random.randn(100).cumsum() + 95,
        'close': np.random.randn(100).cumsum() + 100,
        'volume': np.random.randint(1000, 10000, 100)
    })
    sample_data.set_index('date', inplace=True)
    
    # Run analysis
    result = service.analyze_symbol('TEST', sample_data)
    print(json.dumps(result, indent=2, default=str))