#!/usr/bin/env python3
"""
Test the Pine Script shunt approach
"""
import sys
sys.path.append('.')
from loadtechnicalsdaily import pivot_high, pivot_low
import pandas as pd
import numpy as np

# Test data
test_data = [100, 105, 110, 120, 115, 110, 105, 108, 112, 118, 115, 110, 105, 108, 115, 120, 125, 122, 118, 115]
df = pd.DataFrame({
    'high': test_data, 
    'low': [x-5 for x in test_data],
    'close': [x-2 for x in test_data]
})

print('Testing Pine Script shunt approach for more recent pivot data...')
print(f'Data length: {len(df)} bars (0-19)')

# Test with shunt=1 (like your Pine Script)
pivots_h = pivot_high(df, left_bars=3, right_bars=3, shunt=1)
pivots_l = pivot_low(df, left_bars=3, right_bars=3, shunt=1)

print(f'Pivot highs found: {pivots_h.notna().sum()}')
print(f'Pivot lows found: {pivots_l.notna().sum()}')

print('\nPivot High Details:')
for idx, val in pivots_h.dropna().items():
    bars_from_end = len(df) - 1 - idx
    print(f'  Index {idx}: {val:.2f} ({bars_from_end} bars from most recent)')

print('\nPivot Low Details:')  
for idx, val in pivots_l.dropna().items():
    bars_from_end = len(df) - 1 - idx
    print(f'  Index {idx}: {val:.2f} ({bars_from_end} bars from most recent)')

# Show the improvement
max_pivot_idx = max(pivots_h.dropna().index.max() if pivots_h.notna().sum() > 0 else -1,
                   pivots_l.dropna().index.max() if pivots_l.notna().sum() > 0 else -1)

if max_pivot_idx >= 0:
    bars_from_end = len(df) - 1 - max_pivot_idx
    print(f'\n✅ Most recent pivot is only {bars_from_end} bars from current!')
    print(f'   (Without shunt, it would be {bars_from_end + 1} bars from current)')
else:
    print('\n❌ No pivots found')
