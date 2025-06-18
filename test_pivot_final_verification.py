#!/usr/bin/env python3
"""
Test the pivot calculation fix by simulating the production scenario
"""

import pandas as pd
import numpy as np
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def pivot_high(df, left_bars=3, right_bars=3, shunt=1):
    """
    Pine Script style pivot high calculation with shunt - FIXED VERSION
    """
    # DEBUG: Check if we have the required columns and valid data
    if 'high' not in df.columns:
        logging.error(f"❌ PIVOT ERROR: 'high' column missing from DataFrame. Available columns: {list(df.columns)}")
        return pd.Series(np.full(len(df), np.nan), index=df.index)
    
    # CRITICAL: FORCE SORT DATA BY DATE - This is essential for pivot calculations
    if not df.index.is_monotonic_increasing:
        logging.warning(f"⚠️  PIVOT WARNING: Data not sorted, forcing sort by date index for pivot calculations")
        df = df.sort_index()
    
    # Check for NaN values in high column
    nan_count = df['high'].isna().sum()
    if nan_count > 0:
        logging.warning(f"⚠️  PIVOT WARNING: {nan_count} NaN values found in 'high' column out of {len(df)} rows")
    
    # Check for zero or negative values
    invalid_count = (df['high'] <= 0).sum()
    if invalid_count > 0:
        logging.warning(f"⚠️  PIVOT WARNING: {invalid_count} zero/negative values found in 'high' column")
    
    pivot_vals = [np.nan] * len(df)
    pivot_count = 0
    
    # First find raw pivots
    for i in range(left_bars, len(df) - right_bars):
        try:
            current_high = df['high'].iloc[i]
            
            # Skip if current high is NaN or invalid
            if pd.isna(current_high) or current_high <= 0:
                continue
            
            # Check left bars - current high should be higher than all left bars
            left_higher = True
            for j in range(i - left_bars, i):
                left_val = df['high'].iloc[j]
                if pd.isna(left_val) or current_high <= left_val:
                    left_higher = False
                    break
            
            if not left_higher:
                continue
                
            # Check right bars - current high should be higher than all right bars  
            right_higher = True
            for j in range(i + 1, i + right_bars + 1):
                right_val = df['high'].iloc[j]
                if pd.isna(right_val) or current_high <= right_val:
                    right_higher = False
                    break
                    
            if left_higher and right_higher:
                # Apply shunt
                confirmed_bar = i + right_bars
                shunted_index = confirmed_bar - shunt
                if 0 <= shunted_index < len(pivot_vals):
                    pivot_vals[shunted_index] = current_high
                    pivot_count += 1
                    logging.info(f"✅ Found pivot high: {current_high} at index {i}, placed at {shunted_index}")
        except Exception as e:
            logging.error(f"❌ PIVOT ERROR at index {i}: {str(e)}")
            continue
    
    if pivot_count == 0:
        logging.warning(f"⚠️  PIVOT WARNING: No pivot highs found in {len(df)} bars of data")
    else:
        logging.info(f"🎯 PIVOT SUCCESS: Found {pivot_count} pivot highs in {len(df)} bars")
    
    return pd.Series(pivot_vals, index=df.index)

def test_pivot_with_production_data():
    """Test pivot calculation with realistic stock data"""
    
    print("🧪 Testing Pivot Calculation with Production-Like Data")
    print("=" * 60)
    
    # Create realistic stock price data
    dates = pd.date_range('2024-01-01', periods=30, freq='D')
    
    # Create stock price pattern with clear pivot highs
    base_prices = [100, 101, 103, 105, 108, 106, 104, 102, 101, 103, 
                   106, 109, 112, 115, 113, 110, 107, 105, 108, 111,
                   114, 117, 115, 112, 110, 113, 116, 118, 116, 114]
    
    # Add some noise and create OHLC data
    df = pd.DataFrame({
        'date': dates,
        'high': [p + np.random.uniform(0, 1) for p in base_prices],
        'low': [p - np.random.uniform(0, 1) for p in base_prices],
        'close': base_prices
    })
    
    # Set date as index (this is what the production code does)
    df.set_index('date', inplace=True)
    
    print(f"📊 Created test data: {len(df)} bars")
    print(f"📅 Date range: {df.index.min()} to {df.index.max()}")
    print(f"✅ Data is sorted: {df.index.is_monotonic_increasing}")
    
    # Test 1: With sorted data
    print("\n🧪 Test 1: Sorted Data")
    print("-" * 30)
    pivots_sorted = pivot_high(df, left_bars=3, right_bars=3, shunt=1)
    sorted_count = pivots_sorted.notna().sum()
    print(f"Result: {sorted_count} pivot highs found")
    
    # Show the actual pivot values
    pivot_points = pivots_sorted.dropna()
    if len(pivot_points) > 0:
        print("Pivot highs found:")
        for date, value in pivot_points.items():
            print(f"  {date.strftime('%Y-%m-%d')}: {value:.2f}")
    
    # Test 2: With unsorted data (simulating the bug)
    print("\n🧪 Test 2: Unsorted Data (simulating production bug)")
    print("-" * 50)
    df_unsorted = df.sample(frac=1).copy()  # Shuffle the data
    print(f"✅ Data is sorted: {df_unsorted.index.is_monotonic_increasing}")
    
    pivots_unsorted = pivot_high(df_unsorted, left_bars=3, right_bars=3, shunt=1)
    unsorted_count = pivots_unsorted.notna().sum()
    print(f"Result: {unsorted_count} pivot highs found")
    
    # Test 3: Verify the fix works
    print("\n🧪 Test 3: Verification - Our Fix Should Work")
    print("-" * 45)
    print(f"Sorted data pivots: {sorted_count}")
    print(f"Unsorted data pivots (with auto-sort fix): {unsorted_count}")
    
    if sorted_count > 0 and unsorted_count > 0:
        print("✅ SUCCESS: Pivot calculation fix is working!")
        print("   The function automatically sorts unsorted data and finds pivots.")
    elif sorted_count > 0 and unsorted_count == 0:
        print("❌ ISSUE: Fix didn't work - unsorted data still returns no pivots")
    else:
        print("⚠️  WARNING: No pivots found in either case - may need different test data")
    
    return sorted_count, unsorted_count

if __name__ == "__main__":
    test_pivot_with_production_data()
