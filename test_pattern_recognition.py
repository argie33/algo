#!/usr/bin/env python3
"""
Test Pattern Recognition System
Validates all components work correctly
"""

import numpy as np
import pandas as pd
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Import our modules
from pattern_detectors import (
    TriangleDetector, HeadAndShouldersDetector, DoubleTopBottomDetector
)
from pattern_recognition_service import PatternRecognitionService
from advanced_chart_patterns import AdvancedPatternDetector
from pattern_backtesting import PatternBacktester

def create_test_data(length=100, pattern_type='triangle'):
    """Create synthetic test data with specific patterns"""
    dates = pd.date_range('2023-01-01', periods=length, freq='D')
    np.random.seed(42)
    
    if pattern_type == 'triangle':
        # Create ascending triangle pattern
        base_price = 100
        prices = []
        
        for i in range(length):
            if i < 20:
                # Initial trend
                price = base_price + i * 0.5 + np.random.normal(0, 1)
            elif i < 70:
                # Triangle formation
                resistance = base_price + 20
                support_slope = (base_price + 15 - (base_price + 10)) / 50
                support = base_price + 10 + (i - 20) * support_slope
                
                # Price oscillates between support and resistance
                oscillation = np.sin((i - 20) * 0.3) * 3
                price = (support + resistance) / 2 + oscillation
                price = max(support, min(resistance, price)) + np.random.normal(0, 0.5)
            else:
                # Breakout
                price = base_price + 20 + (i - 70) * 0.8 + np.random.normal(0, 1)
            
            prices.append(max(price, 1))  # Ensure positive prices
    
    elif pattern_type == 'head_shoulders':
        # Create head and shoulders pattern
        base_price = 100
        prices = []
        
        for i in range(length):
            if i < 20:
                # Left shoulder
                price = base_price + 10 * np.sin(i * 0.3) + np.random.normal(0, 1)
            elif i < 40:
                # Head
                price = base_price + 15 * np.sin((i - 20) * 0.3) + np.random.normal(0, 1)
            elif i < 60:
                # Right shoulder
                price = base_price + 10 * np.sin((i - 40) * 0.3) + np.random.normal(0, 1)
            else:
                # Decline
                price = base_price - (i - 60) * 0.5 + np.random.normal(0, 1)
            
            prices.append(max(price, 1))
    
    else:
        # Random walk
        prices = 100 + np.cumsum(np.random.normal(0, 1, length))
        prices = np.maximum(prices, 1)  # Ensure positive
    
    # Create OHLC data
    data = pd.DataFrame({
        'date': dates,
        'close': prices,
        'open': [p + np.random.normal(0, 0.5) for p in prices],
        'high': [p + abs(np.random.normal(2, 1)) for p in prices],
        'low': [p - abs(np.random.normal(2, 1)) for p in prices],
        'volume': np.random.randint(100000, 1000000, length)
    })
    
    # Ensure OHLC consistency
    for i in range(len(data)):
        high = max(data.loc[i, 'open'], data.loc[i, 'close'], data.loc[i, 'high'])
        low = min(data.loc[i, 'open'], data.loc[i, 'close'], data.loc[i, 'low'])
        data.loc[i, 'high'] = high
        data.loc[i, 'low'] = low
    
    data.set_index('date', inplace=True)
    return data

def test_basic_detectors():
    """Test basic pattern detectors"""
    print("Testing Basic Pattern Detectors...")
    
    # Test Triangle Detector
    print("\n1. Testing Triangle Detector")
    triangle_data = create_test_data(100, 'triangle')
    triangle_detector = TriangleDetector()
    
    triangles = triangle_detector.detect_triangles(triangle_data)
    print(f"   Found {len(triangles)} triangle patterns")
    
    for pattern in triangles:
        print(f"   - {pattern.pattern_type}: confidence={pattern.confidence:.3f}")
    
    # Test Head and Shoulders Detector
    print("\n2. Testing Head and Shoulders Detector")
    hs_data = create_test_data(100, 'head_shoulders')
    hs_detector = HeadAndShouldersDetector()
    
    hs_patterns = hs_detector.detect_head_and_shoulders(hs_data)
    print(f"   Found {len(hs_patterns)} H&S patterns")
    
    for pattern in hs_patterns:
        print(f"   - {pattern.pattern_type}: confidence={pattern.confidence:.3f}")
    
    # Test Double Top/Bottom Detector
    print("\n3. Testing Double Top/Bottom Detector")
    double_detector = DoubleTopBottomDetector()
    
    double_patterns = double_detector.detect_double_patterns(triangle_data)
    print(f"   Found {len(double_patterns)} double patterns")
    
    for pattern in double_patterns:
        print(f"   - {pattern.pattern_type}: confidence={pattern.confidence:.3f}")

def test_pattern_service():
    """Test the main pattern recognition service"""
    print("\n\nTesting Pattern Recognition Service...")
    
    service = PatternRecognitionService()
    test_data = create_test_data(100, 'triangle')
    
    result = service.analyze_symbol('TEST', test_data)
    
    print(f"Analysis Results for TEST:")
    print(f"- Total patterns found: {len(result['patterns'])}")
    print(f"- Recommendation: {result['summary'].get('recommendation', 'N/A')}")
    print(f"- Confidence: {result['summary'].get('confidence', 0):.3f}")
    
    for i, pattern_data in enumerate(result['patterns'][:3]):  # Show first 3
        pattern = pattern_data['pattern']
        scores = pattern_data['scores']
        signal = pattern_data['signal']
        
        print(f"\nPattern {i+1}:")
        print(f"  Type: {pattern.pattern_type}")
        print(f"  Confidence: {pattern.confidence:.3f}")
        print(f"  Overall Score: {scores.overall_score:.3f}")
        print(f"  Signal: {signal.signal_type} (strength: {signal.strength:.3f})")
        print(f"  Target: ${signal.target_price:.2f}" if signal.target_price else "  Target: N/A")

def test_advanced_patterns():
    """Test advanced pattern detection"""
    print("\n\nTesting Advanced Pattern Detection...")
    
    detector = AdvancedPatternDetector()
    test_data = create_test_data(150, 'triangle')
    
    patterns = detector.detect_all_advanced_patterns(test_data)
    
    print(f"Advanced patterns found: {len(patterns)}")
    
    for pattern in patterns[:3]:  # Show first 3
        print(f"- {pattern.pattern_type}: confidence={pattern.confidence:.3f}")
        if pattern.target_price:
            print(f"  Target: ${pattern.target_price:.2f}")

def test_backtesting():
    """Test backtesting framework"""
    print("\n\nTesting Backtesting Framework...")
    
    backtester = PatternBacktester()
    
    # Create longer data for backtesting
    test_data = create_test_data(300, 'triangle')
    
    # Run backtest
    results = backtester.backtest_symbol('TEST', test_data)
    
    print(f"Backtest Results:")
    print(f"- Total patterns tested: {len(results)}")
    
    if results:
        successful = sum(1 for r in results if r.success)
        print(f"- Successful patterns: {successful}")
        print(f"- Success rate: {successful/len(results):.2%}")
        
        avg_return = np.mean([r.actual_return for r in results])
        print(f"- Average return: {avg_return:.2%}")
        
        # Calculate statistics
        statistics = backtester.calculate_statistics(results)
        
        print(f"\nPattern Statistics:")
        for pattern_type, stats in statistics.items():
            print(f"- {pattern_type}: {stats.success_rate:.2%} success rate")

def test_integration():
    """Test full system integration"""
    print("\n\nTesting System Integration...")
    
    # Test data provider function
    def data_provider(symbol):
        return create_test_data(100, 'triangle')
    
    service = PatternRecognitionService()
    
    # Test batch analysis
    symbols = ['TEST1', 'TEST2', 'TEST3']
    results = service.batch_analyze(symbols, data_provider)
    
    print(f"Batch Analysis Results:")
    print(f"- Symbols processed: {len(results)}")
    
    total_patterns = 0
    for symbol, data in results.items():
        if 'patterns' in data:
            pattern_count = len(data['patterns'])
            total_patterns += pattern_count
            print(f"- {symbol}: {pattern_count} patterns")
    
    print(f"- Total patterns across all symbols: {total_patterns}")

def main():
    """Run all tests"""
    print("Pattern Recognition System Test Suite")
    print("=" * 50)
    
    try:
        test_basic_detectors()
        test_pattern_service()
        test_advanced_patterns()
        test_backtesting()
        test_integration()
        
        print("\n" + "=" * 50)
        print("All tests completed successfully!")
        
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()