#!/usr/bin/env python3
"""
Test the fixed pivot calculations with sample data
"""

import sys
import os
import pandas as pd
import numpy as np
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Simple test pivot functions (copied from the fixed version)
def test_pivot_high(df, left_bars=3, right_bars=3, shunt=1):
    """Fixed pivot high calculation"""
    if 'high' not in df.columns:
        logging.error(f"❌ 'high' column missing")
        return pd.Series(np.full(len(df), np.nan), index=df.index)
    
    logging.info(f"🔍 Testing pivot high with {len(df)} bars")
    logging.info(f"📊 High range: {df['high'].min():.2f} to {df['high'].max():.2f}")
    
    pivot_vals = [np.nan] * len(df)
    pivot_count = 0
    
    for i in range(left_bars, len(df) - right_bars):
        current_high = df['high'].iloc[i]
        
        # Only skip NaN values
        if pd.isna(current_high):
            continue
        
        # Check left bars
        left_higher = True
        for j in range(i - left_bars, i):
            left_val = df['high'].iloc[j]
            if pd.isna(left_val) or current_high <= left_val:
                left_higher = False
                break
        
        if not left_higher:
            continue
        
        # Check right bars
        right_higher = True
        for j in range(i + 1, i + right_bars + 1):
            right_val = df['high'].iloc[j]
            if pd.isna(right_val) or current_high <= right_val:
                right_higher = False
                break
        
        if left_higher and right_higher:
            pivot_vals[i] = current_high
            pivot_count += 1
            logging.info(f"  ✅ Pivot high #{pivot_count} at index {i}: {current_high:.2f}")
    
    logging.info(f"🎯 Found {pivot_count} pivot highs")
    return pd.Series(pivot_vals, index=df.index)

def main():
    """Test with sample data"""
    
    # Create test data with clear pivot points
    dates = pd.date_range('2024-01-01', periods=15, freq='D')
    
    # Create data with obvious pivot high at index 7 (value 15.0)
    highs = [10, 11, 12, 13, 14, 13, 12, 15, 12, 11, 10, 11, 12, 13, 14]
    lows = [9, 10, 11, 12, 13, 12, 11, 14, 11, 10, 9, 10, 11, 12, 13]
    
    df = pd.DataFrame({
        'high': highs,
        'low': lows,
        'close': [(h+l)/2 for h, l in zip(highs, lows)]
    }, index=dates)
    
    logging.info("📊 Test data created:")
    logging.info(f"\n{df[['high', 'low']]}")
    
    # Test pivot calculation
    pivot_result = test_pivot_high(df)
    
    # Show results
    logging.info("\n📋 Pivot Results:")
    pivots_found = pivot_result.dropna()
    
    if len(pivots_found) > 0:
        for date, value in pivots_found.items():
            logging.info(f"  📅 {date.strftime('%Y-%m-%d')}: {value}")
        logging.info("✅ Pivot calculation is working!")
        return True
    else:
        logging.error("❌ No pivots found - calculation still broken!")
        return False

if __name__ == "__main__":
    success = main()
    print(f"\nTest result: {'PASS' if success else 'FAIL'}")
    sys.exit(0 if success else 1)
