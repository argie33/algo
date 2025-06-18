#!/usr/bin/env python3
import yfinance as yf
import pandas as pd

# Test what fields are actually available in growth_estimates
symbols = ['AAPL', 'MSFT', 'GOOGL']

for symbol in symbols:
    print(f"\n=== Testing {symbol} ===")
    try:
        ticker = yf.Ticker(symbol)
        growth_est = ticker.growth_estimates
        
        if growth_est is not None and not growth_est.empty:
            print("Growth estimates DataFrame:")
            print(growth_est)
            print("\nColumns:", list(growth_est.columns))
            print("Index (periods):", list(growth_est.index))
            print("\nFirst row:")
            for col in growth_est.columns:
                print(f"  {col}: {growth_est.iloc[0][col]}")
        else:
            print("No growth estimates data available")
            
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
