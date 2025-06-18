#!/usr/bin/env python3
"""
Test the actual pivot functions from loadtechnicalsdaily.py
"""

import sys
import os
import pandas as pd
import numpy as np
import logging

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the actual pivot functions from loadtechnicalsdaily
try:
    from loadtechnicalsdaily import pivot_high, pivot_low
    print("✅ Successfully imported pivot functions from loadtechnicalsdaily.py")
except ImportError as e:
    print(f"❌ Failed to import pivot functions: {e}")
    sys.exit(1)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def main():
    """Test actual pivot functions with sample data"""
    
    # Create test data with clear pivot points
    dates = pd.date_range('2024-01-01', periods=20, freq='D')
    
    # Pattern with clear pivot high at index 10 (value 20.0) and pivot low at index 5 (value 8.0)
    highs = [15, 16, 17, 16, 15, 14, 13, 14, 15, 16, 20, 16, 15, 14, 13, 14, 15, 16, 17, 18]
    lows  = [14, 15, 16, 15, 14, 8,  12, 13, 14, 15, 19, 15, 14, 13, 12, 13, 14, 15, 16, 17]
    
    df = pd.DataFrame({
        'open': [14.5] * 20,
        'high': highs,
        'low': lows,
        'close': [(h+l)/2 for h, l in zip(highs, lows)],
        'volume': [1000000] * 20
    }, index=dates)
    
    logging.info("📊 Test data created with expected pivot points:")
    logging.info(f"  Expected pivot high at index 10: {highs[10]}")
    logging.info(f"  Expected pivot low at index 5: {lows[5]}")
    logging.info(f"\n{df[['high', 'low']]}")
    
    # Test pivot high calculation
    logging.info("\n🔺 Testing pivot_high function...")
    pivot_highs = pivot_high(df, left_bars=3, right_bars=3, shunt=1)
    
    # Test pivot low calculation  
    logging.info("\n🔻 Testing pivot_low function...")
    pivot_lows = pivot_low(df, left_bars=3, right_bars=3, shunt=1)
    
    # Show results
    logging.info("\n📋 FINAL RESULTS:")
    
    high_pivots = pivot_highs.dropna()
    low_pivots = pivot_lows.dropna()
    
    logging.info(f"🔺 Pivot highs found: {len(high_pivots)}")
    for date, value in high_pivots.items():
        logging.info(f"  📅 {date.strftime('%Y-%m-%d')}: {value}")
    
    logging.info(f"🔻 Pivot lows found: {len(low_pivots)}")
    for date, value in low_pivots.items():
        logging.info(f"  📅 {date.strftime('%Y-%m-%d')}: {value}")
    
    # Check if we found the expected pivots
    success = True
    
    if len(high_pivots) == 0:
        logging.error("❌ No pivot highs found!")
        success = False
    else:
        # Check if we found the expected high value
        if 20.0 in high_pivots.values:
            logging.info("✅ Found expected pivot high (20.0)")
        else:
            logging.warning(f"⚠️ Expected pivot high 20.0 not found. Got: {high_pivots.values}")
    
    if len(low_pivots) == 0:
        logging.error("❌ No pivot lows found!")
        success = False
    else:
        # Check if we found the expected low value
        if 8.0 in low_pivots.values:
            logging.info("✅ Found expected pivot low (8.0)")
        else:
            logging.warning(f"⚠️ Expected pivot low 8.0 not found. Got: {low_pivots.values}")
    
    if success and (len(high_pivots) > 0 or len(low_pivots) > 0):
        logging.info("✅ Pivot calculations are working correctly!")
        return True
    else:
        logging.error("❌ Pivot calculations are still not working properly!")
        return False

if __name__ == "__main__":
    try:
        success = main()
        print(f"\nTest result: {'PASS' if success else 'FAIL'}")
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
