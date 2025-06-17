#!/usr/bin/env python3
"""
Debug script to test with real market-like data patterns
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

def sanitize_value(x):
    """Convert NaN/inf values to None for database insertion and handle numpy types"""
    if x is None:
        return None
    
    # Handle numpy scalar types (float32, float64, int32, etc.)
    if hasattr(x, 'item'):
        x = x.item()  # Convert numpy scalar to Python scalar
    
    # Handle NaN/inf values for float types
    if isinstance(x, (float, np.floating)) and (np.isnan(x) or np.isinf(x)):
        return None
    
    # Convert numpy types to native Python types
    if isinstance(x, np.integer):
        return int(x)
    elif isinstance(x, np.floating):
        return float(x)
    elif isinstance(x, np.bool_):
        return bool(x)
    
    return x

# Test cases
print("=== Test Case 1: Insufficient Data (< 7 bars) ===")
short_data = pd.DataFrame({
    'high': [100, 105, 110, 115, 120, 118],
    'low': [95, 100, 105, 110, 115, 113]
})
print(f"Data length: {len(short_data)} (needs >= 7 for 3+1+3 pattern)")
pivots_h = pivot_high_vectorized(short_data['high'])
pivots_l = pivot_low_vectorized(short_data['low'])
print(f"Pivot highs found: {pivots_h.notna().sum()}")
print(f"Pivot lows found: {pivots_l.notna().sum()}")

print("\n=== Test Case 2: Exactly 7 bars ===")
exact_data = pd.DataFrame({
    'high': [100, 105, 110, 120, 115, 110, 105],  # Clear pivot at index 3
    'low': [95, 100, 105, 115, 110, 105, 100]
})
print(f"Data length: {len(exact_data)}")
pivots_h = pivot_high_vectorized(exact_data['high'])
pivots_l = pivot_low_vectorized(exact_data['low'])
print(f"Pivot highs found: {pivots_h.notna().sum()}")
print(f"Pivot lows found: {pivots_l.notna().sum()}")
print("Pivot highs:", pivots_h.dropna().to_dict())
print("Pivot lows:", pivots_l.dropna().to_dict())

print("\n=== Test Case 3: Trending Data (No Clear Pivots) ===")
trending_data = pd.DataFrame({
    'high': [100, 105, 110, 115, 120, 125, 130, 135, 140, 145],
    'low': [95, 100, 105, 110, 115, 120, 125, 130, 135, 140]
})
print(f"Data length: {len(trending_data)}")
pivots_h = pivot_high_vectorized(trending_data['high'])
pivots_l = pivot_low_vectorized(trending_data['low'])
print(f"Pivot highs found: {pivots_h.notna().sum()}")
print(f"Pivot lows found: {pivots_l.notna().sum()}")

print("\n=== Test Case 4: Testing sanitize_value on NaN results ===")
test_series = pd.Series([np.nan, 100.0, np.nan, 110.0, np.nan])
print("Original series:", test_series.tolist())
sanitized = [sanitize_value(x) for x in test_series]
print("Sanitized values:", sanitized)
print("Types:", [type(x).__name__ for x in sanitized])
