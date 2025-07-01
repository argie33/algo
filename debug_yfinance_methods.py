#!/usr/bin/env python3
"""
Debug script to test yfinance methods and see what's available in version 0.2.28
"""

import yfinance as yf
import pandas as pd

def test_yfinance_methods():
    print(f"yfinance version: {yf.__version__}")
    
    # Test with AAPL
    symbol = "AAPL"
    print(f"\nTesting methods for {symbol}:")
    
    try:
        ticker = yf.Ticker(symbol)
        print("✓ Ticker object created successfully")
        
        # List all available attributes
        attrs = [attr for attr in dir(ticker) if not attr.startswith('_')]
        print(f"Available attributes: {attrs}")
        
        # Test old methods from scripts
        print("\n=== Testing OLD METHODS from scripts ===")
        
        # 1. financials (annual income statement)
        try:
            data = ticker.financials
            print(f"✓ ticker.financials: {type(data)}, shape: {data.shape if data is not None and hasattr(data, 'shape') else 'N/A'}")
            if data is not None and not data.empty:
                print(f"  Columns: {list(data.columns[:3])}...")  # First 3 columns
                print(f"  Sample rows: {list(data.index[:3])}...")  # First 3 rows
            else:
                print("  ⚠️ No data returned or empty DataFrame")
        except Exception as e:
            print(f"✗ ticker.financials failed: {e}")
        
        # 2. quarterly_financials
        try:
            data = ticker.quarterly_financials
            print(f"✓ ticker.quarterly_financials: {type(data)}, shape: {data.shape if data is not None and hasattr(data, 'shape') else 'N/A'}")
            if data is not None and not data.empty:
                print(f"  Columns: {list(data.columns[:3])}...")
        except Exception as e:
            print(f"✗ ticker.quarterly_financials failed: {e}")
        
        # 3. balance_sheet
        try:
            data = ticker.balance_sheet
            print(f"✓ ticker.balance_sheet: {type(data)}, shape: {data.shape if data is not None and hasattr(data, 'shape') else 'N/A'}")
        except Exception as e:
            print(f"✗ ticker.balance_sheet failed: {e}")
        
        # 4. quarterly_balance_sheet
        try:
            data = ticker.quarterly_balance_sheet
            print(f"✓ ticker.quarterly_balance_sheet: {type(data)}, shape: {data.shape if data is not None and hasattr(data, 'shape') else 'N/A'}")
        except Exception as e:
            print(f"✗ ticker.quarterly_balance_sheet failed: {e}")
        
        # 5. cashflow
        try:
            data = ticker.cashflow
            print(f"✓ ticker.cashflow: {type(data)}, shape: {data.shape if data is not None and hasattr(data, 'shape') else 'N/A'}")
        except Exception as e:
            print(f"✗ ticker.cashflow failed: {e}")
        
        # 6. quarterly_cashflow
        try:
            data = ticker.quarterly_cashflow
            print(f"✓ ticker.quarterly_cashflow: {type(data)}, shape: {data.shape if data is not None and hasattr(data, 'shape') else 'N/A'}")
        except Exception as e:
            print(f"✗ ticker.quarterly_cashflow failed: {e}")
        
        # Test newer methods if they exist
        print("\n=== Testing NEWER METHODS ===")
        
        newer_methods = [
            'income_stmt', 'quarterly_income_stmt',
            'cash_flow', 'quarterly_cash_flow'
        ]
        
        for method in newer_methods:
            try:
                data = getattr(ticker, method)
                print(f"✓ ticker.{method}: {type(data)}, shape: {data.shape if data is not None and hasattr(data, 'shape') else 'N/A'}")
            except AttributeError:
                print(f"✗ ticker.{method}: Method doesn't exist")
            except Exception as e:
                print(f"✗ ticker.{method}: {e}")
                
    except Exception as e:
        print(f"✗ Failed to create ticker: {e}")

if __name__ == "__main__":
    test_yfinance_methods()