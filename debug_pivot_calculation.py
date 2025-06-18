#!/usr/bin/env python3
"""
Debug script to test pivot high/low calculations specifically
This will help us identify why pivot values are not being calculated correctly
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import pandas as pd
    import numpy as np
    import logging
    from datetime import datetime, timedelta
    print("✅ All imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def create_test_data():
    """Create test data that should definitely produce pivot points"""
    dates = pd.date_range(start='2024-01-01', periods=20, freq='D')
    
    # Create artificial price data with clear pivot points
    # Pattern: low, rise to high (pivot high), fall, rise again
    highs = [10.0, 10.5, 11.0, 12.0, 15.0, 12.0, 11.0, 10.5, 11.0, 12.0, 
             13.0, 11.0, 10.0, 9.5, 10.0, 11.0, 12.5, 11.5, 10.8, 10.2]
    
    lows = [9.5, 10.0, 10.5, 11.5, 14.0, 11.5, 10.5, 10.0, 10.5, 11.5,
            12.5, 10.5, 9.5, 9.0, 9.5, 10.5, 12.0, 11.0, 10.3, 9.8]
    
    df = pd.DataFrame({
        'high': highs,
        'low': lows,
        'close': [(h + l) / 2 for h, l in zip(highs, lows)]  # midpoint
    }, index=dates)
    
    return df

def pivot_high_debug(df, left_bars=3, right_bars=3, shunt=1):
    """Debug version of pivot high calculation with extensive logging"""
    logging.info("🔍 PIVOT HIGH DEBUG - Starting calculation")
    logging.info(f"📊 Input data shape: {df.shape}")
    logging.info(f"📋 Parameters: left_bars={left_bars}, right_bars={right_bars}, shunt={shunt}")
    
    # Check data validity
    if 'high' not in df.columns:
        logging.error(f"❌ 'high' column missing. Available: {list(df.columns)}")
        return pd.Series(np.full(len(df), np.nan), index=df.index)
    
    # Data quality checks
    logging.info(f"📊 High values range: {df['high'].min():.2f} to {df['high'].max():.2f}")
    logging.info(f"📊 NaN count in high: {df['high'].isna().sum()}")
    logging.info(f"📊 Zero/negative count: {(df['high'] <= 0).sum()}")
    
    # Sort data if needed
    if not df.index.is_monotonic_increasing:
        logging.warning("⚠️ Sorting data by index")
        df = df.sort_index()
    
    pivot_vals = [np.nan] * len(df)
    pivot_count = 0
    
    # Calculate minimum required data length
    min_required = left_bars + 1 + right_bars
    logging.info(f"📏 Minimum required data length: {min_required}, actual: {len(df)}")
    
    if len(df) < min_required:
        logging.error(f"❌ Insufficient data: need {min_required}, got {len(df)}")
        return pd.Series(pivot_vals, index=df.index)
    
    # Main pivot calculation loop
    for i in range(left_bars, len(df) - right_bars):
        current_high = df['high'].iloc[i]
        
        logging.debug(f"🔍 Checking index {i}, date: {df.index[i]}, high: {current_high:.2f}")
        
        # FIXED: Don't skip zero values - they might be valid in some datasets
        if pd.isna(current_high):
            logging.debug(f"  ⚠️ Skipping NaN value at index {i}")
            continue
        
        # Check left bars
        left_higher = True
        left_values = []
        for j in range(i - left_bars, i):
            left_val = df['high'].iloc[j]
            left_values.append(left_val)
            if pd.isna(left_val) or current_high <= left_val:
                left_higher = False
                logging.debug(f"  ❌ Left check failed: current({current_high:.2f}) <= left[{j}]({left_val:.2f})")
                break
        
        if not left_higher:
            continue
        
        # Check right bars
        right_higher = True
        right_values = []
        for j in range(i + 1, i + right_bars + 1):
            right_val = df['high'].iloc[j]
            right_values.append(right_val)
            if pd.isna(right_val) or current_high <= right_val:
                right_higher = False
                logging.debug(f"  ❌ Right check failed: current({current_high:.2f}) <= right[{j}]({right_val:.2f})")
                break
        
        if left_higher and right_higher:
            # FIXED: Simplified shunt logic
            # Original Pine Script: pvthi_[Shunt] means look back 'shunt' bars from current confirmation
            pivot_index = i  # Place pivot at the actual pivot bar, not shifted
            
            logging.info(f"  ✅ PIVOT HIGH FOUND at index {i} (date: {df.index[i]}, value: {current_high:.2f})")
            logging.info(f"     Left values: {[f'{v:.2f}' for v in left_values]}")
            logging.info(f"     Right values: {[f'{v:.2f}' for v in right_values]}")
            
            if 0 <= pivot_index < len(pivot_vals):
                pivot_vals[pivot_index] = current_high
                pivot_count += 1
                logging.info(f"  ✅ Pivot #{pivot_count} recorded at index {pivot_index}")
            else:
                logging.error(f"  ❌ Invalid pivot index: {pivot_index}")
    
    logging.info(f"🎯 PIVOT HIGH SUMMARY: Found {pivot_count} pivots out of {len(df)} bars")
    
    result = pd.Series(pivot_vals, index=df.index)
    non_nan_count = result.notna().sum()
    logging.info(f"📊 Result: {non_nan_count} non-NaN values in result series")
    
    # Show the pivot points found
    pivots_found = result.dropna()
    if len(pivots_found) > 0:
        logging.info("🔍 PIVOT POINTS FOUND:")
        for date, value in pivots_found.items():
            logging.info(f"  📅 {date.strftime('%Y-%m-%d')}: {value:.2f}")
    else:
        logging.warning("⚠️ NO PIVOT POINTS FOUND!")
    
    return result

def pivot_low_debug(df, left_bars=3, right_bars=3, shunt=1):
    """Debug version of pivot low calculation with extensive logging"""
    logging.info("🔍 PIVOT LOW DEBUG - Starting calculation")
    
    # Similar logic to pivot_high_debug but for lows
    if 'low' not in df.columns:
        logging.error(f"❌ 'low' column missing. Available: {list(df.columns)}")
        return pd.Series(np.full(len(df), np.nan), index=df.index)
    
    logging.info(f"📊 Low values range: {df['low'].min():.2f} to {df['low'].max():.2f}")
    
    pivot_vals = [np.nan] * len(df)
    pivot_count = 0
    
    min_required = left_bars + 1 + right_bars
    if len(df) < min_required:
        logging.error(f"❌ Insufficient data: need {min_required}, got {len(df)}")
        return pd.Series(pivot_vals, index=df.index)
    
    for i in range(left_bars, len(df) - right_bars):
        current_low = df['low'].iloc[i]
        
        if pd.isna(current_low):
            continue
        
        # Check left bars - current should be LOWER than all left bars
        left_lower = True
        for j in range(i - left_bars, i):
            left_val = df['low'].iloc[j]
            if pd.isna(left_val) or current_low >= left_val:
                left_lower = False
                break
        
        if not left_lower:
            continue
        
        # Check right bars - current should be LOWER than all right bars
        right_lower = True
        for j in range(i + 1, i + right_bars + 1):
            right_val = df['low'].iloc[j]
            if pd.isna(right_val) or current_low >= right_val:
                right_lower = False
                break
        
        if left_lower and right_lower:
            pivot_vals[i] = current_low
            pivot_count += 1
            logging.info(f"  ✅ PIVOT LOW FOUND at index {i} (date: {df.index[i]}, value: {current_low:.2f})")
    
    logging.info(f"🎯 PIVOT LOW SUMMARY: Found {pivot_count} pivots")
    
    result = pd.Series(pivot_vals, index=df.index)
    pivots_found = result.dropna()
    if len(pivots_found) > 0:
        logging.info("🔍 PIVOT LOW POINTS FOUND:")
        for date, value in pivots_found.items():
            logging.info(f"  📅 {date.strftime('%Y-%m-%d')}: {value:.2f}")
    
    return result

def main():
    """Test pivot calculations with known data"""
    logging.info("🧪 PIVOT DEBUG TEST SCRIPT")
    logging.info("=" * 50)
    
    # Create test data
    test_df = create_test_data()
    logging.info("📊 Created test data:")
    logging.info(f"\n{test_df}")
    
    # Test pivot high calculation
    logging.info("\n" + "=" * 50)
    pivot_highs = pivot_high_debug(test_df)
    
    logging.info("\n" + "=" * 50)
    pivot_lows = pivot_low_debug(test_df)
    
    # Summary
    logging.info("\n" + "=" * 50)
    logging.info("📋 FINAL SUMMARY:")
    logging.info(f"🔺 Pivot highs found: {pivot_highs.notna().sum()}")
    logging.info(f"🔻 Pivot lows found: {pivot_lows.notna().sum()}")
    
    if pivot_highs.notna().sum() == 0 and pivot_lows.notna().sum() == 0:
        logging.error("❌ NO PIVOTS FOUND - THERE IS A BUG IN THE CALCULATION!")
        return False
    else:
        logging.info("✅ Pivots found - calculation appears to be working")
        return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
