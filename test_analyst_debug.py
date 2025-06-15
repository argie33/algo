#!/usr/bin/env python3
import yfinance as yf
import pandas as pd

# Test a few symbols to see the actual data structure
test_symbols = ['AAPL', 'MSFT', 'GOOGL']

for symbol in test_symbols:
    print(f"\n=== Testing {symbol} ===")
    try:
        ticker = yf.Ticker(symbol)
        upgrades_downgrades = ticker.upgrades_downgrades
        
        print(f"Type: {type(upgrades_downgrades)}")
        print(f"Shape: {upgrades_downgrades.shape if hasattr(upgrades_downgrades, 'shape') else 'No shape'}")
        print(f"Empty: {upgrades_downgrades.empty if hasattr(upgrades_downgrades, 'empty') else 'No empty method'}")
        
        if hasattr(upgrades_downgrades, 'head'):
            print(f"Columns: {list(upgrades_downgrades.columns)}")
            print(f"Index name: {upgrades_downgrades.index.name}")
            print("First 3 rows:")
            print(upgrades_downgrades.head(3))
            
            # Check a specific row
            if not upgrades_downgrades.empty:
                first_row = upgrades_downgrades.iloc[0]
                print(f"\nFirst row details:")
                for col in upgrades_downgrades.columns:
                    print(f"  {col}: '{first_row[col]}'")
        else:
            print(f"Data: {upgrades_downgrades}")
            
    except Exception as e:
        print(f"Error for {symbol}: {e}")
