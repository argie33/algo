#!/usr/bin/env python3
"""
Test script to verify the pivot sort fix
"""
import pandas as pd
import numpy as np

# Simulate the exact same scenario as production
def test_pivot_sort_issue():
    print("Testing pivot calculations with unsorted vs sorted data...")
    
    # Create test data that would be typical in production
    dates = pd.date_range('2024-01-01', periods=20, freq='D')
    prices = [100, 102, 105, 108, 112, 110, 107, 104, 101, 99, 103, 107, 111, 115, 113, 110, 108, 105, 102, 100]
    
    # Create DataFrame similar to production
    df_sorted = pd.DataFrame({
        'date': dates,
        'high': [p + np.random.uniform(0, 1) for p in prices],
        'low': [p - np.random.uniform(0, 1) for p in prices],
        'close': prices
    })
    df_sorted.set_index('date', inplace=True)
    
    # Create UNSORTED version (simulating the bug)
    df_unsorted = df_sorted.sample(frac=1).copy()  # Shuffle the data
    
    print(f"Sorted data date range: {df_sorted.index.min()} to {df_sorted.index.max()}")
    print(f"Sorted data is monotonic increasing: {df_sorted.index.is_monotonic_increasing}")
    print(f"Unsorted data is monotonic increasing: {df_unsorted.index.is_monotonic_increasing}")
    
    # Production-style pivot calculation
    def pivot_high_production(df, left_bars=3, right_bars=3, shunt=1):
        """Exactly like production code"""
        if len(df) < left_bars + right_bars + 1:
            return pd.Series(np.full(len(df), np.nan), index=df.index)
        
        # CRITICAL: Check if data is sorted
        if not df.index.is_monotonic_increasing:
            print("❌ ERROR: Data is not sorted by date!")
            return pd.Series(np.full(len(df), np.nan), index=df.index)
        
        pivot_vals = [np.nan] * len(df)
        pivot_count = 0
        
        for i in range(left_bars, len(df) - right_bars):
            current_high = df['high'].iloc[i]
            
            if pd.isna(current_high) or current_high <= 0:
                continue
            
            # Check left bars
            left_higher = True
            for j in range(i - left_bars, i):
                if pd.isna(df['high'].iloc[j]) or current_high <= df['high'].iloc[j]:
                    left_higher = False
                    break
            
            if not left_higher:
                continue
                
            # Check right bars
            right_higher = True
            for j in range(i + 1, i + right_bars + 1):
                if pd.isna(df['high'].iloc[j]) or current_high <= df['high'].iloc[j]:
                    right_higher = False
                    break
                    
            if left_higher and right_higher:
                confirmed_bar = i + right_bars
                shunted_index = confirmed_bar - shunt
                if 0 <= shunted_index < len(pivot_vals):
                    pivot_vals[shunted_index] = current_high
                    pivot_count += 1
        
        print(f"Found {pivot_count} pivot highs")
        return pd.Series(pivot_vals, index=df.index)
    
    print("\n" + "="*50)
    print("Testing with SORTED data:")
    print("="*50)
    pivots_sorted = pivot_high_production(df_sorted)
    sorted_count = pivots_sorted.notna().sum()
    print(f"Pivots found in sorted data: {sorted_count}")
    
    print("\n" + "="*50)
    print("Testing with UNSORTED data:")
    print("="*50)
    pivots_unsorted = pivot_high_production(df_unsorted)
    unsorted_count = pivots_unsorted.notna().sum()
    print(f"Pivots found in unsorted data: {unsorted_count}")
    
    print("\n" + "="*50)
    print("Testing with UNSORTED data after sorting:")
    print("="*50)
    df_fixed = df_unsorted.sort_index()  # This is our fix!
    pivots_fixed = pivot_high_production(df_fixed)
    fixed_count = pivots_fixed.notna().sum()
    print(f"Pivots found in fixed data: {fixed_count}")
    
    print("\n" + "="*50)
    print("SUMMARY:")
    print("="*50)
    print(f"Sorted data pivots: {sorted_count}")
    print(f"Unsorted data pivots: {unsorted_count}")
    print(f"Fixed data pivots: {fixed_count}")
    
    if fixed_count > 0 and fixed_count == sorted_count:
        print("✅ SUCCESS: The sort fix works correctly!")
    else:
        print("❌ ISSUE: The sort fix didn't work as expected")

if __name__ == "__main__":
    test_pivot_sort_issue()
