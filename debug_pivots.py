#!/usr/bin/env python3
"""
Debug script to test pivot high/low calculations
"""
import pandas as pd
import numpy as np

def pivot_high_vectorized(high, left_bars=3, right_bars=3):
    """Vectorized pivot high calculation"""
    if len(high) < left_bars + right_bars + 1:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    result = pd.Series(np.full(len(high), np.nan), index=high.index)
    
    for i in range(left_bars, len(high) - right_bars):
        # Check if current high is higher than surrounding bars
        left_window = high.iloc[i-left_bars:i]
        right_window = high.iloc[i+1:i+right_bars+1]
        
        if (high.iloc[i] > left_window.max()) and (high.iloc[i] > right_window.max()):
            result.iloc[i] = high.iloc[i]
    
    return result

def pivot_low_vectorized(low, left_bars=3, right_bars=3):
    """Vectorized pivot low calculation"""
    if len(low) < left_bars + right_bars + 1:
        return pd.Series(np.full(len(low), np.nan), index=low.index)
    
    result = pd.Series(np.full(len(low), np.nan), index=low.index)
    
    for i in range(left_bars, len(low) - right_bars):
        # Check if current low is lower than surrounding bars
        left_window = low.iloc[i-left_bars:i]
        right_window = low.iloc[i+1:i+right_bars+1]
        
        if (low.iloc[i] < left_window.min()) and (low.iloc[i] < right_window.min()):
            result.iloc[i] = low.iloc[i]
    
    return result

# Test with sample data
print("Testing pivot calculations...")

# Create test data with obvious pivots
test_data = {
    'high': [100, 105, 110, 115, 120, 118, 116, 114, 112, 110, 115, 120, 125, 130, 128, 126, 124, 122, 120],
    'low': [95, 100, 105, 110, 115, 113, 111, 109, 107, 105, 110, 115, 120, 125, 123, 121, 119, 117, 115]
}

df = pd.DataFrame(test_data)
print("Test data:")
print(df.head(10))

# Calculate pivots
pivot_highs = pivot_high_vectorized(df['high'])
pivot_lows = pivot_low_vectorized(df['low'])

print("\nPivot Highs:")
print(pivot_highs.dropna())

print("\nPivot Lows:")  
print(pivot_lows.dropna())

print(f"\nFound {pivot_highs.notna().sum()} pivot highs out of {len(df)} bars")
print(f"Found {pivot_lows.notna().sum()} pivot lows out of {len(df)} bars")

# Test edge case - insufficient data
small_data = pd.Series([100, 105, 110])
small_pivots = pivot_high_vectorized(small_data)
print(f"\nSmall data test (3 bars): {small_pivots.notna().sum()} pivots found (should be 0)")
