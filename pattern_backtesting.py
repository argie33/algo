#!/usr/bin/env python3
"""
Pattern Recognition Backtesting Framework
Validates pattern performance and provides statistical analysis
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings('ignore')

from pattern_detectors import PatternMatch, PatternPoint
from pattern_recognition_service import PatternRecognitionService
from advanced_chart_patterns import AdvancedPatternDetector

@dataclass
class BacktestResult:
    """Single backtest result for a pattern"""
    pattern_type: str
    entry_date: datetime
    entry_price: float
    exit_date: datetime
    exit_price: float
    target_price: Optional[float]
    stop_loss: Optional[float]
    actual_return: float
    expected_return: float
    hit_target: bool
    hit_stop: bool
    days_held: int
    confidence: float
    pattern_height: float
    success: bool

@dataclass
class PatternStatistics:
    """Statistical analysis of pattern performance"""
    pattern_type: str
    total_occurrences: int
    successful_patterns: int
    success_rate: float
    avg_return: float
    avg_days_held: float
    best_return: float
    worst_return: float
    avg_target_hit_rate: float
    avg_stop_hit_rate: float
    confidence_correlation: float
    risk_adjusted_return: float
    sharpe_ratio: float
    max_drawdown: float

class PatternBacktester:
    """Pattern backtesting engine"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or self._default_config()
        self.pattern_service = PatternRecognitionService()
        self.advanced_detector = AdvancedPatternDetector()
        self.results = []
        
    def _default_config(self) -> Dict[str, Any]:
        """Default backtesting configuration"""
        return {
            'holding_period_days': 30,
            'min_confidence': 0.6,
            'commission': 0.001,  # 0.1% commission
            'slippage': 0.002,    # 0.2% slippage
            'risk_free_rate': 0.02,  # 2% annual risk-free rate
            'max_position_size': 0.1,  # 10% of portfolio
            'stop_loss_multiple': 1.5,  # 1.5x pattern height
            'target_multiple': 1.0,     # 1.0x pattern height
            'min_pattern_height': 0.02  # 2% minimum pattern height
        }
    
    def backtest_symbol(self, symbol: str, data: pd.DataFrame, 
                       start_date: datetime = None, end_date: datetime = None) -> List[BacktestResult]:
        """Backtest patterns for a single symbol"""
        if start_date:
            data = data[data.index >= start_date]
        if end_date:
            data = data[data.index <= end_date]
        
        results = []
        
        # Use sliding window to detect patterns
        window_size = 60  # 60-day window
        step_size = 5     # 5-day step
        
        for i in range(0, len(data) - window_size, step_size):
            window_data = data.iloc[i:i + window_size]
            
            # Detect patterns in window
            patterns = self.pattern_service.detect_all_patterns(window_data)
            
            # Also detect advanced patterns
            advanced_patterns = self.advanced_detector.detect_all_advanced_patterns(window_data)
            patterns.extend(advanced_patterns)
            
            # Filter patterns that complete near end of window
            valid_patterns = [p for p in patterns 
                            if p.end_point.index >= len(window_data) - 10]
            
            # Test each pattern
            for pattern in valid_patterns:
                if pattern.confidence >= self.config['min_confidence']:
                    result = self._test_pattern(pattern, data, i + pattern.end_point.index)
                    if result:
                        results.append(result)
        
        return results
    
    def _test_pattern(self, pattern: PatternMatch, full_data: pd.DataFrame, 
                     pattern_end_idx: int) -> Optional[BacktestResult]:
        """Test a single pattern's performance"""
        try:
            # Entry point is day after pattern completion
            entry_idx = pattern_end_idx + 1
            if entry_idx >= len(full_data):
                return None
            
            entry_date = full_data.index[entry_idx]
            entry_price = full_data['open'].iloc[entry_idx]  # Open price next day
            
            # Apply slippage and commission
            entry_price *= (1 + self.config['slippage'])
            
            # Calculate targets and stops
            target_price = self._calculate_target_price(pattern, entry_price)
            stop_loss = self._calculate_stop_loss(pattern, entry_price)
            
            # Find exit point
            exit_result = self._find_exit_point(
                full_data, entry_idx, entry_price, target_price, stop_loss
            )
            
            if not exit_result:
                return None
            
            exit_date, exit_price, hit_target, hit_stop = exit_result
            
            # Calculate returns
            actual_return = (exit_price - entry_price) / entry_price
            expected_return = (target_price - entry_price) / entry_price if target_price else 0
            
            # Apply commission
            actual_return -= self.config['commission'] * 2  # Buy and sell
            
            # Calculate days held
            days_held = (exit_date - entry_date).days
            
            # Determine success
            success = actual_return > 0 and (hit_target or actual_return >= expected_return * 0.5)
            
            return BacktestResult(
                pattern_type=pattern.pattern_type,
                entry_date=entry_date,
                entry_price=entry_price,
                exit_date=exit_date,
                exit_price=exit_price,
                target_price=target_price,
                stop_loss=stop_loss,
                actual_return=actual_return,
                expected_return=expected_return,
                hit_target=hit_target,
                hit_stop=hit_stop,
                days_held=days_held,
                confidence=pattern.confidence,
                pattern_height=pattern.pattern_height,
                success=success
            )
            
        except Exception as e:
            print(f"Error testing pattern: {e}")
            return None
    
    def _calculate_target_price(self, pattern: PatternMatch, entry_price: float) -> Optional[float]:
        """Calculate target price based on pattern"""
        if pattern.target_price:
            return pattern.target_price
        
        # Use pattern height as default
        if pattern.pattern_height:
            height_ratio = pattern.pattern_height / entry_price
            
            # Bullish patterns
            if pattern.pattern_type in ['ascending_triangle', 'inverse_head_and_shoulders', 
                                     'double_bottom', 'cup_and_handle', 'falling_wedge']:
                return entry_price * (1 + height_ratio * self.config['target_multiple'])
            
            # Bearish patterns
            elif pattern.pattern_type in ['descending_triangle', 'head_and_shoulders', 
                                        'double_top', 'rising_wedge']:
                return entry_price * (1 - height_ratio * self.config['target_multiple'])
        
        return None
    
    def _calculate_stop_loss(self, pattern: PatternMatch, entry_price: float) -> Optional[float]:
        """Calculate stop loss based on pattern"""
        if pattern.stop_loss:
            return pattern.stop_loss
        
        # Use pattern height as default
        if pattern.pattern_height:
            height_ratio = pattern.pattern_height / entry_price
            
            # Bullish patterns
            if pattern.pattern_type in ['ascending_triangle', 'inverse_head_and_shoulders', 
                                     'double_bottom', 'cup_and_handle', 'falling_wedge']:
                return entry_price * (1 - height_ratio * self.config['stop_loss_multiple'])
            
            # Bearish patterns
            elif pattern.pattern_type in ['descending_triangle', 'head_and_shoulders', 
                                        'double_top', 'rising_wedge']:
                return entry_price * (1 + height_ratio * self.config['stop_loss_multiple'])
        
        return None
    
    def _find_exit_point(self, data: pd.DataFrame, entry_idx: int, entry_price: float,
                        target_price: Optional[float], stop_loss: Optional[float]) -> Optional[Tuple]:
        """Find exit point based on target/stop or time limit"""
        max_holding_period = self.config['holding_period_days']
        
        for i in range(entry_idx + 1, min(entry_idx + max_holding_period + 1, len(data))):
            current_high = data['high'].iloc[i]
            current_low = data['low'].iloc[i]
            current_close = data['close'].iloc[i]
            
            # Check if target hit
            if target_price and ((entry_price < target_price and current_high >= target_price) or
                               (entry_price > target_price and current_low <= target_price)):
                exit_price = target_price * (1 - self.config['slippage'])
                return data.index[i], exit_price, True, False
            
            # Check if stop loss hit
            if stop_loss and ((entry_price > stop_loss and current_low <= stop_loss) or
                            (entry_price < stop_loss and current_high >= stop_loss)):
                exit_price = stop_loss * (1 + self.config['slippage'])
                return data.index[i], exit_price, False, True
        
        # Time-based exit
        exit_idx = min(entry_idx + max_holding_period, len(data) - 1)
        exit_price = data['close'].iloc[exit_idx] * (1 - self.config['slippage'])
        return data.index[exit_idx], exit_price, False, False
    
    def calculate_statistics(self, results: List[BacktestResult]) -> Dict[str, PatternStatistics]:
        """Calculate statistical analysis of backtest results"""
        if not results:
            return {}
        
        # Group by pattern type
        pattern_groups = {}
        for result in results:
            pattern_type = result.pattern_type
            if pattern_type not in pattern_groups:
                pattern_groups[pattern_type] = []
            pattern_groups[pattern_type].append(result)
        
        statistics = {}
        
        for pattern_type, pattern_results in pattern_groups.items():
            stats = self._calculate_pattern_statistics(pattern_type, pattern_results)
            statistics[pattern_type] = stats
        
        return statistics
    
    def _calculate_pattern_statistics(self, pattern_type: str, 
                                    results: List[BacktestResult]) -> PatternStatistics:
        """Calculate statistics for a specific pattern type"""
        if not results:
            return PatternStatistics(
                pattern_type=pattern_type,
                total_occurrences=0,
                successful_patterns=0,
                success_rate=0.0,
                avg_return=0.0,
                avg_days_held=0.0,
                best_return=0.0,
                worst_return=0.0,
                avg_target_hit_rate=0.0,
                avg_stop_hit_rate=0.0,
                confidence_correlation=0.0,
                risk_adjusted_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0
            )
        
        # Basic statistics
        total_occurrences = len(results)
        successful_patterns = sum(1 for r in results if r.success)
        success_rate = successful_patterns / total_occurrences
        
        returns = [r.actual_return for r in results]
        avg_return = np.mean(returns)
        best_return = max(returns)
        worst_return = min(returns)
        
        avg_days_held = np.mean([r.days_held for r in results])
        
        target_hit_rate = np.mean([1 if r.hit_target else 0 for r in results])
        stop_hit_rate = np.mean([1 if r.hit_stop else 0 for r in results])
        
        # Confidence correlation
        confidences = [r.confidence for r in results]
        confidence_correlation = np.corrcoef(confidences, returns)[0, 1] if len(returns) > 1 else 0
        
        # Risk-adjusted metrics
        risk_adjusted_return = avg_return / np.std(returns) if np.std(returns) > 0 else 0
        
        # Sharpe ratio (annualized)
        excess_return = avg_return - self.config['risk_free_rate'] / 252  # Daily risk-free rate
        sharpe_ratio = excess_return / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        
        # Maximum drawdown
        cumulative_returns = np.cumprod([1 + r for r in returns])
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdowns = (cumulative_returns - running_max) / running_max
        max_drawdown = abs(min(drawdowns)) if len(drawdowns) > 0 else 0
        
        return PatternStatistics(
            pattern_type=pattern_type,
            total_occurrences=total_occurrences,
            successful_patterns=successful_patterns,
            success_rate=success_rate,
            avg_return=avg_return,
            avg_days_held=avg_days_held,
            best_return=best_return,
            worst_return=worst_return,
            avg_target_hit_rate=target_hit_rate,
            avg_stop_hit_rate=stop_hit_rate,
            confidence_correlation=confidence_correlation,
            risk_adjusted_return=risk_adjusted_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown
        )
    
    def generate_report(self, results: List[BacktestResult], 
                       statistics: Dict[str, PatternStatistics]) -> Dict[str, Any]:
        """Generate comprehensive backtesting report"""
        if not results:
            return {
                'summary': {'total_patterns': 0, 'message': 'No patterns found'},
                'statistics': {},
                'recommendations': []
            }
        
        # Overall summary
        total_patterns = len(results)
        successful_patterns = sum(1 for r in results if r.success)
        overall_success_rate = successful_patterns / total_patterns
        
        overall_return = np.mean([r.actual_return for r in results])
        total_return = np.prod([1 + r.actual_return for r in results]) - 1
        
        # Best and worst patterns
        best_pattern = max(results, key=lambda r: r.actual_return)
        worst_pattern = min(results, key=lambda r: r.actual_return)
        
        # Pattern type performance ranking
        pattern_ranking = []
        for pattern_type, stats in statistics.items():
            pattern_ranking.append({
                'pattern_type': pattern_type,
                'success_rate': stats.success_rate,
                'avg_return': stats.avg_return,
                'sharpe_ratio': stats.sharpe_ratio,
                'total_occurrences': stats.total_occurrences
            })
        
        pattern_ranking.sort(key=lambda x: x['sharpe_ratio'], reverse=True)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(statistics)
        
        return {
            'summary': {
                'total_patterns': total_patterns,
                'successful_patterns': successful_patterns,
                'overall_success_rate': overall_success_rate,
                'average_return': overall_return,
                'total_return': total_return,
                'best_pattern': {
                    'type': best_pattern.pattern_type,
                    'return': best_pattern.actual_return,
                    'date': best_pattern.entry_date.isoformat()
                },
                'worst_pattern': {
                    'type': worst_pattern.pattern_type,
                    'return': worst_pattern.actual_return,
                    'date': worst_pattern.entry_date.isoformat()
                }
            },
            'pattern_ranking': pattern_ranking,
            'statistics': {k: asdict(v) for k, v in statistics.items()},
            'recommendations': recommendations,
            'generated_at': datetime.now().isoformat()
        }
    
    def _generate_recommendations(self, statistics: Dict[str, PatternStatistics]) -> List[str]:
        """Generate trading recommendations based on backtest results"""
        recommendations = []
        
        # Find best performing patterns
        best_patterns = sorted(statistics.items(), 
                             key=lambda x: x[1].sharpe_ratio, reverse=True)[:3]
        
        if best_patterns:
            best_pattern = best_patterns[0][1]
            recommendations.append(
                f"Focus on {best_pattern.pattern_type} patterns - "
                f"highest Sharpe ratio of {best_pattern.sharpe_ratio:.2f}"
            )
        
        # Confidence correlation insights
        high_confidence_patterns = [s for s in statistics.values() 
                                  if s.confidence_correlation > 0.3]
        if high_confidence_patterns:
            recommendations.append(
                "Higher confidence patterns show better performance - "
                "prioritize patterns with confidence > 0.7"
            )
        
        # Risk management insights
        high_risk_patterns = [s for s in statistics.values() 
                            if s.max_drawdown > 0.15]
        if high_risk_patterns:
            recommendations.append(
                f"Implement tighter risk management for {len(high_risk_patterns)} pattern types "
                "showing high drawdowns"
            )
        
        # Time-based insights
        quick_patterns = [s for s in statistics.values() 
                         if s.avg_days_held < 10 and s.success_rate > 0.6]
        if quick_patterns:
            recommendations.append(
                f"Consider shorter holding periods for {len(quick_patterns)} pattern types "
                "that show quick resolution"
            )
        
        return recommendations
    
    def export_results(self, results: List[BacktestResult], 
                      filename: str = None) -> str:
        """Export backtest results to CSV"""
        if not results:
            return "No results to export"
        
        # Convert to DataFrame
        df = pd.DataFrame([asdict(r) for r in results])
        
        # Add derived columns
        df['risk_reward_ratio'] = df['expected_return'] / abs(df['actual_return'] - df['expected_return'])
        df['annualized_return'] = df['actual_return'] * (365 / df['days_held'])
        
        if filename:
            df.to_csv(filename, index=False)
            return f"Results exported to {filename}"
        else:
            return df.to_csv(index=False)

# Example usage
if __name__ == "__main__":
    # Create sample data for testing
    dates = pd.date_range('2020-01-01', periods=500, freq='D')
    np.random.seed(42)
    
    # Generate realistic stock data
    returns = np.random.normal(0.001, 0.02, len(dates))  # Daily returns
    price_data = 100 * np.exp(np.cumsum(returns))
    
    sample_data = pd.DataFrame({
        'date': dates,
        'open': price_data,
        'high': price_data * (1 + np.random.uniform(0, 0.02, len(dates))),
        'low': price_data * (1 - np.random.uniform(0, 0.02, len(dates))),
        'close': price_data,
        'volume': np.random.randint(100000, 1000000, len(dates))
    })
    sample_data.set_index('date', inplace=True)
    
    # Run backtest
    backtester = PatternBacktester()
    results = backtester.backtest_symbol('TEST', sample_data)
    
    if results:
        statistics = backtester.calculate_statistics(results)
        report = backtester.generate_report(results, statistics)
        
        print("Backtest Report:")
        print(f"Total patterns tested: {report['summary']['total_patterns']}")
        print(f"Success rate: {report['summary']['overall_success_rate']:.2%}")
        print(f"Average return: {report['summary']['average_return']:.2%}")
        
        print("\nTop performing patterns:")
        for pattern in report['pattern_ranking'][:3]:
            print(f"- {pattern['pattern_type']}: {pattern['success_rate']:.2%} success rate")
    else:
        print("No patterns found in sample data")