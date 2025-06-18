#!/usr/bin/env python3
"""
Test script to diagnose A/D (Accumulation/Distribution) calculation issues
"""

import pandas as pd
import numpy as np
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

def ad_line_test(high, low, close, volume):
    """Test A/D calculation with detailed debugging"""
    print(f"🔍 A/D Test: Starting calculation")
    print(f"🔍 A/D: Input lengths - high:{len(high)}, low:{len(low)}, close:{len(close)}, volume:{len(volume)}")
    
    if len(high) == 0:
        print(f"⚠️  A/D: No data provided")
        return pd.Series([], dtype=float)
    
    # Check for volume data quality
    volume_valid = (volume > 0).sum()
    volume_zero = (volume == 0).sum()
    volume_negative = (volume < 0).sum()
    print(f"🔍 A/D: Volume data - total:{len(volume)}, valid:{volume_valid}, zero:{volume_zero}, negative:{volume_negative}")
    
    if volume_valid == 0:
        print(f"❌ A/D: No valid volume data - cannot calculate A/D line")
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # Check OHLC data quality
    print(f"🔍 A/D: High range: {high.min():.4f} to {high.max():.4f}")
    print(f"🔍 A/D: Low range: {low.min():.4f} to {low.max():.4f}")
    print(f"🔍 A/D: Close range: {close.min():.4f} to {close.max():.4f}")
    print(f"🔍 A/D: Volume range: {volume.min():.0f} to {volume.max():.0f}")
    
    # Money Flow Multiplier - handle edge cases where high == low
    high_low_diff = high - low
    doji_count = (high_low_diff == 0).sum()
    print(f"🔍 A/D: Price ranges - min:{high_low_diff.min():.4f}, max:{high_low_diff.max():.4f}, doji_days:{doji_count}")
    
    # Check for problematic data
    if doji_count == len(high):
        print(f"❌ A/D: All days are doji (high == low) - invalid price data")
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    high_low_diff_clean = high_low_diff.replace(0, 1e-10)  # Avoid division by zero
    
    mfm = ((close - low) - (high - close)) / high_low_diff_clean
    print(f"🔍 A/D: Money Flow Multiplier - min:{mfm.min():.4f}, max:{mfm.max():.4f}, mean:{mfm.mean():.4f}")
    
    # Check for extreme MFM values
    extreme_mfm = ((mfm > 10) | (mfm < -10)).sum()
    if extreme_mfm > 0:
        print(f"⚠️  A/D: {extreme_mfm} extreme MFM values found (may indicate data issues)")
    
    # Money Flow Volume
    mfv = mfm * volume
    print(f"🔍 A/D: Money Flow Volume - min:{mfv.min():.2f}, max:{mfv.max():.2f}, sum:{mfv.sum():.2f}")
    
    # Check for problematic MFV values
    mfv_nan = mfv.isna().sum()
    mfv_inf = np.isinf(mfv).sum()
    print(f"🔍 A/D: Money Flow Volume quality - NaN:{mfv_nan}, Inf:{mfv_inf}")
    
    # A/D Line (cumulative) - handle NaN values properly
    mfv_clean = mfv.fillna(0)
    ad_line = mfv_clean.cumsum()
    
    valid_count = ad_line.notna().sum()
    print(f"🔍 A/D: Final A/D line - valid:{valid_count}/{len(ad_line)}")
    print(f"🔍 A/D: A/D range: {ad_line.min():.2f} to {ad_line.max():.2f}")
    print(f"🔍 A/D: Sample values: {ad_line.tail(10).tolist()}")
    
    return ad_line

# Create test data
np.random.seed(42)
dates = pd.date_range('2024-01-01', periods=30, freq='D')

# Test Case 1: Normal data
print("="*60)
print("TEST CASE 1: Normal Stock Data")
print("="*60)

base_price = 100
price_changes = np.random.normal(0, 2, 30).cumsum()
close_prices = base_price + price_changes
high_prices = close_prices + np.random.uniform(0.5, 3, 30)
low_prices = close_prices - np.random.uniform(0.5, 3, 30)
volumes = np.random.randint(100000, 1000000, 30)

test_data = pd.DataFrame({
    'high': high_prices,
    'low': low_prices,
    'close': close_prices,
    'volume': volumes
}, index=dates)

ad_result = ad_line_test(test_data['high'], test_data['low'], test_data['close'], test_data['volume'])
print(f"Result: {len(ad_result)} values, {ad_result.notna().sum()} valid")

# Test Case 2: Doji data (high == low)
print("\n" + "="*60)
print("TEST CASE 2: Doji Data (high == low)")
print("="*60)

doji_data = test_data.copy()
doji_data['high'] = doji_data['close']
doji_data['low'] = doji_data['close']

ad_doji = ad_line_test(doji_data['high'], doji_data['low'], doji_data['close'], doji_data['volume'])
print(f"Result: {len(ad_doji)} values, {ad_doji.notna().sum()} valid")

# Test Case 3: Zero volume
print("\n" + "="*60)
print("TEST CASE 3: Zero Volume Data")
print("="*60)

zero_vol_data = test_data.copy()
zero_vol_data['volume'] = 0

ad_zero_vol = ad_line_test(zero_vol_data['high'], zero_vol_data['low'], zero_vol_data['close'], zero_vol_data['volume'])
print(f"Result: {len(ad_zero_vol)} values, {ad_zero_vol.notna().sum()} valid")

# Test Case 4: Mixed issues
print("\n" + "="*60)
print("TEST CASE 4: Mixed Data Quality Issues")
print("="*60)

mixed_data = test_data.copy()
# Some doji days
mixed_data.loc[mixed_data.index[0:5], 'high'] = mixed_data.loc[mixed_data.index[0:5], 'close']
mixed_data.loc[mixed_data.index[0:5], 'low'] = mixed_data.loc[mixed_data.index[0:5], 'close']
# Some zero volume days
mixed_data.loc[mixed_data.index[10:15], 'volume'] = 0

ad_mixed = ad_line_test(mixed_data['high'], mixed_data['low'], mixed_data['close'], mixed_data['volume'])
print(f"Result: {len(ad_mixed)} values, {ad_mixed.notna().sum()} valid")

print("\n" + "="*60)
print("DIAGNOSIS SUMMARY")
print("="*60)
print("A/D Line calculation issues likely caused by:")
print("1. ❌ All zero volume data")
print("2. ❌ All doji data (high == low)")  
print("3. ❌ Extreme price movements causing invalid MFM")
print("4. ⚠️  Mixed data quality reducing effectiveness")
print("5. 🔍 Check if A/D values are too large for database column constraints")
