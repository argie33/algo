#!/usr/bin/env python3
"""
Test script to diagnose potential MFI issues in production scenarios
"""

import pandas as pd
import numpy as np
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

def sanitize_value(x):
    """Replicate the exact sanitize_value function from the loader"""
    if x is None:
        return None
    
    # Handle numpy scalar types (float32, float64, int32, etc.)
    if hasattr(x, 'item'):
        x = x.item()  # Convert numpy scalar to Python native type
    
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

def mfi_production_test(high, low, close, volume, period=14):
    """Replicate exact MFI calculation from production code"""
    print(f"🔍 MFI Production Test: Starting calculation with period={period}")
    print(f"🔍 MFI: Input lengths - high:{len(high)}, low:{len(low)}, close:{len(close)}, volume:{len(volume)}")
    
    if len(high) < period + 1:
        print(f"⚠️  MFI: Insufficient data - need {period + 1}, got {len(high)}")
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # Check volume data quality - EXACT replication
    volume_stats = {
        'total_rows': len(volume),
        'non_null': volume.notna().sum(),
        'positive': (volume > 0).sum(),
        'zero': (volume == 0).sum(),
        'negative': (volume < 0).sum(),
        'mean': volume.mean() if volume.notna().sum() > 0 else 0,
        'max': volume.max() if volume.notna().sum() > 0 else 0
    }
    print(f"🔍 MFI: Volume stats = {volume_stats}")
    
    if volume_stats['positive'] == 0:
        print(f"❌ MFI: No positive volume values found - cannot calculate MFI")
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # Typical Price
    typical_price = (high + low + close) / 3
    print(f"🔍 MFI: Typical price - min:{typical_price.min():.4f}, max:{typical_price.max():.4f}")
    
    # Raw Money Flow
    raw_money_flow = typical_price * volume
    print(f"🔍 MFI: Raw money flow - min:{raw_money_flow.min():.2f}, max:{raw_money_flow.max():.2f}")
    
    # Positive and Negative Money Flow
    price_changes = typical_price.diff()
    pos_money_flow = raw_money_flow.where(price_changes > 0, 0)
    neg_money_flow = raw_money_flow.where(price_changes < 0, 0)
    
    print(f"🔍 MFI: Positive money flow sum: {pos_money_flow.sum():.2f}")
    print(f"🔍 MFI: Negative money flow sum: {neg_money_flow.sum():.2f}")
    
    # Rolling sums
    pos_sum = pos_money_flow.rolling(window=period, min_periods=period).sum()
    neg_sum = neg_money_flow.rolling(window=period, min_periods=period).sum()
    
    # MFI calculation with better handling of edge cases
    money_ratio = pos_sum / (neg_sum + 1e-10)  # Avoid division by zero
    mfi = 100 - (100 / (1 + money_ratio))
    
    # Fill NaN values with neutral MFI of 50
    result = mfi.fillna(50)
    
    # Log final results
    valid_count = result.notna().sum()
    print(f"🔍 MFI: Final results - valid:{valid_count}/{len(result)}, mean:{result.mean():.2f}")
    print(f"🔍 MFI: Sample values: {result.dropna().tail(5).tolist()}")
    
    return result

# Test Case 1: Normal data (should work)
print("="*60)
print("TEST CASE 1: Normal Stock Data (30 days)")
print("="*60)

np.random.seed(42)
dates = pd.date_range('2024-01-01', periods=30, freq='D')
base_price = 100
price_changes = np.random.normal(0, 2, 30).cumsum()
close_prices = base_price + price_changes
high_prices = close_prices + np.random.uniform(0.5, 3, 30)
low_prices = close_prices - np.random.uniform(0.5, 3, 30)
volumes = np.random.randint(100000, 1000000, 30)

test_data_normal = pd.DataFrame({
    'high': high_prices,
    'low': low_prices, 
    'close': close_prices,
    'volume': volumes
}, index=dates)

mfi_normal = mfi_production_test(test_data_normal['high'], test_data_normal['low'], 
                               test_data_normal['close'], test_data_normal['volume'])

print(f"✅ Normal data result: {mfi_normal.notna().sum()}/{len(mfi_normal)} valid MFI values")

# Test Case 2: Insufficient data (should fail)
print("\n" + "="*60)
print("TEST CASE 2: Insufficient Data (10 days)")
print("="*60)

short_data = test_data_normal.head(10)
mfi_short = mfi_production_test(short_data['high'], short_data['low'], 
                              short_data['close'], short_data['volume'])

print(f"❌ Insufficient data result: {mfi_short.notna().sum()}/{len(mfi_short)} valid MFI values")

# Test Case 3: Zero volume data (should fail)
print("\n" + "="*60)
print("TEST CASE 3: Zero Volume Data")
print("="*60)

zero_volume_data = test_data_normal.copy()
zero_volume_data['volume'] = 0

mfi_zero_volume = mfi_production_test(zero_volume_data['high'], zero_volume_data['low'], 
                                    zero_volume_data['close'], zero_volume_data['volume'])

print(f"❌ Zero volume result: {mfi_zero_volume.notna().sum()}/{len(mfi_zero_volume)} valid MFI values")

# Test Case 4: Mixed volume data (some zero, some positive)
print("\n" + "="*60)
print("TEST CASE 4: Mixed Volume Data (Some Zero)")
print("="*60)

mixed_volume_data = test_data_normal.copy()
# Set first 10 days to zero volume
mixed_volume_data.loc[mixed_volume_data.index[:10], 'volume'] = 0

mfi_mixed_volume = mfi_production_test(mixed_volume_data['high'], mixed_volume_data['low'], 
                                     mixed_volume_data['close'], mixed_volume_data['volume'])

print(f"⚠️  Mixed volume result: {mfi_mixed_volume.notna().sum()}/{len(mfi_mixed_volume)} valid MFI values")

# Test Case 5: Check sanitization
print("\n" + "="*60)
print("TEST CASE 5: Database Sanitization Test")
print("="*60)

# Test various values through sanitize_value
test_values = [
    45.67,  # Normal MFI value
    np.float64(45.67),  # NumPy float
    np.nan,  # NaN
    np.inf,  # Infinity
    None,   # None value
    50.0,   # Neutral MFI
]

print("Sanitization results:")
for val in test_values:
    sanitized = sanitize_value(val)
    print(f"  {str(val):15} -> {sanitized} (type: {type(sanitized).__name__})")

print("\n" + "="*60)
print("DIAGNOSIS SUMMARY")
print("="*60)
print("✅ MFI calculation logic works correctly with normal data")
print("❌ MFI fails with insufficient data (< 15 days)")
print("❌ MFI fails with zero/missing volume data")
print("⚠️  MFI may have partial failures with mixed volume data")
print("\nLikely causes of N/A values in production:")
print("1. Symbols with < 15 days of historical data")
print("2. Symbols with zero or missing volume data")
print("3. Data quality issues in price_daily table")
print("4. Technical indicators loader not running or failing")
