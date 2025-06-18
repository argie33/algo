#!/usr/bin/env python3
"""
Test script to verify MFI calculation logic works correctly
"""

import pandas as pd
import numpy as np
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

def mfi_test(high, low, close, volume, period=14):
    """Simplified MFI calculation for testing"""
    print(f"Testing MFI calculation:")
    print(f"Input data length: {len(high)}")
    print(f"Period requirement: {period + 1}")
    
    if len(high) < period + 1:
        print(f"❌ Insufficient data - need {period + 1}, got {len(high)}")
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # Check volume data quality
    volume_stats = {
        'total_rows': len(volume),
        'non_null': volume.notna().sum(),
        'positive': (volume > 0).sum(),
        'zero': (volume == 0).sum(),
        'negative': (volume < 0).sum(),
        'mean': volume.mean() if volume.notna().sum() > 0 else 0,
        'max': volume.max() if volume.notna().sum() > 0 else 0
    }
    print(f"Volume stats: {volume_stats}")
    
    if volume_stats['positive'] == 0:
        print(f"❌ No positive volume values found")
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # Typical Price
    typical_price = (high + low + close) / 3
    print(f"Typical price range: {typical_price.min():.4f} to {typical_price.max():.4f}")
    
    # Raw Money Flow
    raw_money_flow = typical_price * volume
    print(f"Raw money flow range: {raw_money_flow.min():.2f} to {raw_money_flow.max():.2f}")
    
    # Positive and Negative Money Flow
    price_changes = typical_price.diff()
    pos_money_flow = raw_money_flow.where(price_changes > 0, 0)
    neg_money_flow = raw_money_flow.where(price_changes < 0, 0)
    
    print(f"Positive money flow sum: {pos_money_flow.sum():.2f}")
    print(f"Negative money flow sum: {neg_money_flow.sum():.2f}")
    
    # Rolling sums
    pos_sum = pos_money_flow.rolling(window=period, min_periods=period).sum()
    neg_sum = neg_money_flow.rolling(window=period, min_periods=period).sum()
    
    print(f"Rolling positive sum valid count: {pos_sum.notna().sum()}")
    print(f"Rolling negative sum valid count: {neg_sum.notna().sum()}")
    
    # MFI calculation
    money_ratio = pos_sum / (neg_sum + 1e-10)
    mfi = 100 - (100 / (1 + money_ratio))
    
    # Fill NaN values with neutral MFI of 50
    result = mfi.fillna(50)
    
    valid_count = result.notna().sum()
    print(f"Final MFI - valid:{valid_count}/{len(result)}, mean:{result.mean():.2f}")
    print(f"Sample MFI values: {result.dropna().tail(10).tolist()}")
    
    return result

# Create test data - simulate 30 days of stock data
np.random.seed(42)  # For reproducible results
dates = pd.date_range('2024-01-01', periods=30, freq='D')

# Generate realistic OHLC data
base_price = 100
price_changes = np.random.normal(0, 2, 30).cumsum()
close_prices = base_price + price_changes

# Generate OHLC with proper relationships
high_prices = close_prices + np.random.uniform(0.5, 3, 30)
low_prices = close_prices - np.random.uniform(0.5, 3, 30)
open_prices = close_prices + np.random.uniform(-1, 1, 30)

# Generate volume data
volumes = np.random.randint(100000, 1000000, 30)

# Create DataFrame
test_data = pd.DataFrame({
    'high': high_prices,
    'low': low_prices, 
    'close': close_prices,
    'open': open_prices,
    'volume': volumes
}, index=dates)

print("Test Data Summary:")
print(test_data.describe())
print("\n" + "="*50)

# Test MFI calculation
mfi_result = mfi_test(test_data['high'], test_data['low'], test_data['close'], test_data['volume'])

print("\n" + "="*50)
print("MFI Calculation Results:")
print(f"Total calculated values: {len(mfi_result)}")
print(f"Non-null values: {mfi_result.notna().sum()}")
print(f"Null values: {mfi_result.isna().sum()}")

# Show final 10 values with dates
print("\nFinal 10 MFI values:")
for i in range(-10, 0):
    date = test_data.index[i]
    mfi_val = mfi_result.iloc[i]
    print(f"{date.strftime('%Y-%m-%d')}: {mfi_val:.2f}")

print("\n" + "="*50)
print("ANALYSIS:")
print("✅ If you see MFI values between 0-100, the calculation logic works")
print("❌ If you see all NaN or 50.00 values, there's an issue with the calculation")
