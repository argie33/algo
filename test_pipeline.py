#!/usr/bin/env python3
"""
Test the technical indicators processing pipeline
"""
import sys
sys.path.append('.')
from loadtechnicalsdaily import calculate_technicals_parallel
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Create test data with sufficient bars for all indicators
dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
np.random.seed(42)  # For reproducible results

# Create realistic stock data with some trends and volatility
base_price = 100
price_changes = np.random.normal(0, 0.02, 30)  # 2% daily volatility
prices = [base_price]

for change in price_changes[1:]:
    new_price = prices[-1] * (1 + change)
    prices.append(new_price)

# Create OHLCV data
test_data = []
for i, (date, close) in enumerate(zip(dates, prices)):
    # Generate realistic OHLC from close price
    volatility = close * 0.03  # 3% intraday range
    high = close + np.random.uniform(0, volatility)
    low = close - np.random.uniform(0, volatility)
    open_price = low + np.random.uniform(0, high - low)
    volume = np.random.randint(100000, 1000000)
    
    test_data.append({
        'date': date,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })

df = pd.DataFrame(test_data)
df.set_index('date', inplace=True)

print("Test data created:")
print(f"Date range: {df.index.min()} to {df.index.max()}")
print(f"Number of bars: {len(df)}")
print(f"Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

# Run the technical indicators calculation
print("\nCalculating technical indicators...")
try:
    result_df = calculate_technicals_parallel(df)
    
    print(f"\nResults:")
    print(f"Output dataframe shape: {result_df.shape}")
    print(f"Columns: {list(result_df.columns)}")
    
    # Check pivot results specifically
    pivot_high_count = result_df['pivot_high'].notna().sum()
    pivot_low_count = result_df['pivot_low'].notna().sum()
    
    print(f"\nPivot Results:")
    print(f"Pivot highs found: {pivot_high_count}")
    print(f"Pivot lows found: {pivot_low_count}")
    
    if pivot_high_count > 0:
        print("Pivot high values:")
        pivot_highs = result_df[result_df['pivot_high'].notna()][['pivot_high']]
        print(pivot_highs)
    
    if pivot_low_count > 0:
        print("Pivot low values:")
        pivot_lows = result_df[result_df['pivot_low'].notna()][['pivot_low']]
        print(pivot_lows)
    
    # Check other indicators
    print(f"\nOther Indicators Sample:")
    for col in ['ad', 'cmf', 'marketwatch', 'dm']:
        if col in result_df.columns:
            non_null_count = result_df[col].notna().sum()
            print(f"{col}: {non_null_count} non-null values")
            if non_null_count > 0:
                print(f"  Range: {result_df[col].min():.4f} to {result_df[col].max():.4f}")
        else:
            print(f"{col}: NOT FOUND")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
