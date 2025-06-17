#!/usr/bin/env python3
"""
Comparison of OLD vs NEW pivot calculation behavior
"""
import pandas as pd
import numpy as np

# OLD VERSION (what was in your code before)
def pivot_high_old(high, left_bars=3, right_bars=3):
    """OLD: Original pivot high calculation"""
    if len(high) < left_bars + right_bars + 1:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    result = pd.Series(np.full(len(high), np.nan), index=high.index)
    
    for i in range(left_bars, len(high) - right_bars):
        left_window = high.iloc[i-left_bars:i]
        right_window = high.iloc[i+1:i+right_bars+1]
        
        if (high.iloc[i] > left_window.max()) and (high.iloc[i] > right_window.max()):
            result.iloc[i] = high.iloc[i]
    
    return result

# NEW VERSION (what I updated it to)
def pivot_high_new(high, left_bars=3, right_bars=3):
    """NEW: Updated pivot high calculation (SAME LOGIC, better documentation)"""
    min_required_bars = left_bars + right_bars + 1
    
    if len(high) < min_required_bars:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    result = pd.Series(np.full(len(high), np.nan), index=high.index)
    
    for i in range(left_bars, len(high) - right_bars):
        current_high = high.iloc[i]
        
        left_window = high.iloc[i-left_bars:i]
        right_window = high.iloc[i+1:i+right_bars+1]
        
        if (current_high > left_window.max()) and (current_high > right_window.max()):
            result.iloc[i] = current_high
    
    return result

# Test with same data
test_data = [100, 105, 110, 120, 115, 110, 105, 108, 112, 118, 115, 110, 105]
high_series = pd.Series(test_data)

print("=== COMPARISON TEST ===")
print(f"Test data: {test_data}")
print(f"Data length: {len(test_data)}")

old_result = pivot_high_old(high_series)
new_result = pivot_high_new(high_series)

print("\nOLD function results:")
print(old_result.dropna().to_dict())

print("\nNEW function results:")
print(new_result.dropna().to_dict())

print(f"\nAre results identical? {old_result.equals(new_result)}")

# Test with insufficient data
print("\n=== INSUFFICIENT DATA TEST (6 bars, need 7) ===")
short_data = [100, 105, 110, 115, 110, 105]
short_series = pd.Series(short_data)

old_short = pivot_high_old(short_series)
new_short = pivot_high_new(short_series)

print(f"OLD with {len(short_data)} bars: {old_short.notna().sum()} pivots found")
print(f"NEW with {len(short_data)} bars: {new_short.notna().sum()} pivots found")
print(f"Results identical? {old_short.equals(new_short)}")

print("\n=== THE REAL ISSUE WAS NOT THE CALCULATION ===")
print("The real issue was in the main processing loop:")
print("OLD: if len(symbol_data) < 1:  # This allowed 1-6 bars to be processed")
print("NEW: Added warning about insufficient data for pivots, but still processes")
print("\nSo symbols with 1-6 bars would:")
print("1. Be processed (not skipped)")
print("2. Have pivot functions called")
print("3. Pivot functions would return all NaN (because < 7 bars)")
print("4. All NaN values would be converted to NULL in database")
print("5. Result: Blank/NULL pivot columns in database")
