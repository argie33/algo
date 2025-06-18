#!/usr/bin/env python3
"""
Test pivot calculations with more realistic data patterns
"""
import pandas as pd
import numpy as np

def pivot_high_vectorized(high, left_bars=3, right_bars=3, shunt=1):
    """Vectorized pivot high calculation exactly as in production"""
    if len(high) < left_bars + right_bars + 1:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    pivot_vals = [np.nan] * len(high)
    pivot_count = 0
    
    # First find raw pivots (like pvthi_)
    for i in range(left_bars, len(high) - right_bars):
        try:
            current_high = high.iloc[i]
            
            # Skip if current high is NaN or invalid
            if pd.isna(current_high) or current_high <= 0:
                continue
            
            # Check left bars - current high should be higher than all left bars
            left_higher = True
            for j in range(i - left_bars, i):
                left_val = high.iloc[j]
                if pd.isna(left_val) or current_high <= left_val:
                    left_higher = False
                    break
            
            if not left_higher:
                continue
                
            # Check right bars - current high should be higher than all right bars  
            right_higher = True
            for j in range(i + 1, i + right_bars + 1):
                right_val = high.iloc[j]
                if pd.isna(right_val) or current_high <= right_val:
                    right_higher = False
                    break
                    
            if left_higher and right_higher:
                # Apply shunt - Pine Script pvthi_[Shunt] means "get value from Shunt bars back"
                confirmed_bar = i + right_bars  # This is when the pivot is "confirmed"
                shunted_index = confirmed_bar - shunt  # Apply shunt backwards
                if 0 <= shunted_index < len(pivot_vals):
                    pivot_vals[shunted_index] = current_high
                    pivot_count += 1
        except Exception as e:
            print(f"ERROR at index {i}: {str(e)}")
            continue
    
    print(f"Found {pivot_count} pivot highs out of {len(high)} bars")
    return pd.Series(pivot_vals, index=high.index)

def pivot_low_vectorized(low, left_bars=3, right_bars=3, shunt=1):
    """Vectorized pivot low calculation exactly as in production"""
    if len(low) < left_bars + right_bars + 1:
        return pd.Series(np.full(len(low), np.nan), index=low.index)
    
    pivot_vals = [np.nan] * len(low)
    pivot_count = 0
    
    # First find raw pivots (like pvtlo_)
    for i in range(left_bars, len(low) - right_bars):
        try:
            current_low = low.iloc[i]
            
            # Skip if current low is NaN or invalid
            if pd.isna(current_low) or current_low <= 0:
                continue
            
            # Check left bars - current low should be lower than all left bars
            left_lower = True
            for j in range(i - left_bars, i):
                left_val = low.iloc[j]
                if pd.isna(left_val) or current_low >= left_val:
                    left_lower = False
                    break
            
            if not left_lower:
                continue
                
            # Check right bars - current low should be lower than all right bars
            right_lower = True
            for j in range(i + 1, i + right_bars + 1):
                right_val = low.iloc[j]
                if pd.isna(right_val) or current_low >= right_val:
                    right_lower = False
                    break
                    
            if left_lower and right_lower:
                # Apply shunt
                confirmed_bar = i + right_bars  # This is when the pivot is "confirmed"
                shunted_index = confirmed_bar - shunt  # Apply shunt backwards
                if 0 <= shunted_index < len(pivot_vals):
                    pivot_vals[shunted_index] = current_low
                    pivot_count += 1
        except Exception as e:
            print(f"ERROR at index {i}: {str(e)}")
            continue
    
    print(f"Found {pivot_count} pivot lows out of {len(low)} bars")
    return pd.Series(pivot_vals, index=low.index)

def sanitize_value(x):
    """Convert NaN/inf values to None for database insertion and handle numpy types"""
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

# Test 1: Simple ascending/descending pattern
print("=" * 60)
print("TEST 1: Simple Pattern")
print("=" * 60)

simple_data = {
    'high': [100, 102, 105, 108, 112, 110, 107, 104, 101, 99, 103, 107, 111, 115, 113, 110, 108, 105, 102],
    'low': [98, 100, 103, 106, 110, 108, 105, 102, 99, 97, 101, 105, 109, 113, 111, 108, 106, 103, 100]
}

df1 = pd.DataFrame(simple_data)
pivot_highs_1 = pivot_high_vectorized(df1['high'])
pivot_lows_1 = pivot_low_vectorized(df1['low'])

print("\nPivot Highs:")
for i, val in enumerate(pivot_highs_1):
    if not pd.isna(val):
        print(f"  Index {i}: {val} (sanitized: {sanitize_value(val)})")

print("\nPivot Lows:")
for i, val in enumerate(pivot_lows_1):
    if not pd.isna(val):
        print(f"  Index {i}: {val} (sanitized: {sanitize_value(val)})")

# Test 2: Very volatile pattern (more realistic)
print("\n" + "=" * 60)
print("TEST 2: Volatile Pattern")
print("=" * 60)

np.random.seed(42)  # For reproducible results
base_price = 100
prices = [base_price]
for i in range(30):
    change = np.random.normal(0, 2)  # Random walk with volatility
    new_price = max(prices[-1] + change, 1)  # Don't go negative
    prices.append(new_price)

# Create OHLC from prices (simplified)
highs = [p + abs(np.random.normal(0, 0.5)) for p in prices]
lows = [p - abs(np.random.normal(0, 0.5)) for p in prices]

df2 = pd.DataFrame({'high': highs, 'low': lows})
print(f"Data shape: {df2.shape}")
print("Sample data:")
print(df2.head(10))

pivot_highs_2 = pivot_high_vectorized(df2['high'])
pivot_lows_2 = pivot_low_vectorized(df2['low'])

print("\nPivot Highs:")
for i, val in enumerate(pivot_highs_2):
    if not pd.isna(val):
        print(f"  Index {i}: {val:.2f} (sanitized: {sanitize_value(val)})")

print("\nPivot Lows:")
for i, val in enumerate(pivot_lows_2):
    if not pd.isna(val):
        print(f"  Index {i}: {val:.2f} (sanitized: {sanitize_value(val)})")

# Test 3: Edge cases that might cause issues
print("\n" + "=" * 60)
print("TEST 3: Edge Cases")
print("=" * 60)

# Data with NaN values
edge_highs = [100, 102, np.nan, 108, 112, 110, 107, np.nan, 101, 99]
edge_lows = [98, 100, 96, 106, 110, 108, 105, 102, np.nan, 97]

df3 = pd.DataFrame({'high': edge_highs, 'low': edge_lows})
print("Data with NaN values:")
print(df3)

pivot_highs_3 = pivot_high_vectorized(df3['high'])
pivot_lows_3 = pivot_low_vectorized(df3['low'])

print("\nPivot Highs:")
for i, val in enumerate(pivot_highs_3):
    if not pd.isna(val):
        print(f"  Index {i}: {val} (sanitized: {sanitize_value(val)})")
    elif i < len(pivot_highs_3) - 5:  # Don't show all NaN at end
        print(f"  Index {i}: NaN")

print("\nPivot Lows:")
for i, val in enumerate(pivot_lows_3):
    if not pd.isna(val):
        print(f"  Index {i}: {val} (sanitized: {sanitize_value(val)})")
    elif i < len(pivot_lows_3) - 5:  # Don't show all NaN at end
        print(f"  Index {i}: NaN")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print("If the pivot calculations are working correctly in these tests,")
print("the issue might be:")
print("1. Data quality issues in the actual price data")
print("2. Database insertion/retrieval problems")
print("3. Date/time ordering issues in the data")
print("4. Symbol filtering or grouping issues")
