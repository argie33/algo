#!/usr/bin/env python3
"""
Simple test to see what yfinance methods exist and what data they return
"""

print("Testing yfinance methods used in financial statement scripts...")

# Test if we can at least import the modules
try:
    import yfinance as yf
    print("✓ yfinance imported successfully")
    print(f"yfinance version: {yf.__version__}")
except ImportError as e:
    print(f"✗ yfinance import failed: {e}")
    exit(1)

try:
    import pandas as pd
    print("✓ pandas imported successfully")
except ImportError as e:
    print(f"✗ pandas import failed: {e}")
    exit(1)

# Test ticker creation
symbol = "AAPL"
print(f"\nTesting with symbol: {symbol}")

try:
    ticker = yf.Ticker(symbol)
    print("✓ Ticker object created")
    
    # Get all available attributes
    attrs = [attr for attr in dir(ticker) if not attr.startswith('_')]
    print(f"Available ticker attributes: {attrs}")
    
    # Test the specific methods used in the scripts
    methods_to_test = [
        'financials',           # Used in loadannualincomestatement.py
        'quarterly_financials', # Used in loadquarterlyincomestatement.py  
        'balance_sheet',        # Used in loadannualbalancesheet.py
        'quarterly_balance_sheet', # Used in loadquarterlybalancesheet.py
        'cashflow',            # Used in loadannualcashflow.py
        'quarterly_cashflow'   # Used in loadquarterlycashflow.py
    ]
    
    print(f"\n=== Testing methods used in scripts ===")
    for method in methods_to_test:
        print(f"\nTesting ticker.{method}:")
        try:
            data = getattr(ticker, method)
            if data is None:
                print(f"  ✗ {method}: Returns None")
            elif hasattr(data, 'empty') and data.empty:
                print(f"  ✗ {method}: Returns empty DataFrame")
            elif hasattr(data, 'shape'):
                print(f"  ✓ {method}: Returns DataFrame with shape {data.shape}")
                if hasattr(data, 'columns') and len(data.columns) > 0:
                    print(f"    - Columns: {list(data.columns)}")
                if hasattr(data, 'index') and len(data.index) > 0:
                    print(f"    - Row names (sample): {list(data.index[:5])}")
            else:
                print(f"  ? {method}: Returns {type(data)}")
        except AttributeError:
            print(f"  ✗ {method}: Method does not exist")
        except Exception as e:
            print(f"  ✗ {method}: Error - {e}")
    
    # Test newer method names that might be available
    print(f"\n=== Testing possible newer method names ===")
    newer_methods = [
        'income_stmt',
        'quarterly_income_stmt', 
        'cash_flow',
        'quarterly_cash_flow'
    ]
    
    for method in newer_methods:
        try:
            if hasattr(ticker, method):
                data = getattr(ticker, method)
                print(f"  ✓ {method}: Available, returns {type(data)}")
                if hasattr(data, 'shape'):
                    print(f"    - Shape: {data.shape}")
            else:
                print(f"  ✗ {method}: Not available")
        except Exception as e:
            print(f"  ✗ {method}: Error - {e}")
            
except Exception as e:
    print(f"✗ Failed to test ticker: {e}")

print("\nTest completed.")