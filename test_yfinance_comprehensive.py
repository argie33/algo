#!/usr/bin/env python3
"""
Comprehensive test to determine which yfinance methods work for financial statements
Tests both old and new method names to find the working ones
"""

import yfinance as yf
import pandas as pd
import sys

def test_symbol_methods(symbol="AAPL"):
    """Test all possible yfinance methods for a given symbol"""
    print(f"=== Testing {symbol} ===")
    
    try:
        ticker = yf.Ticker(symbol)
        print(f"✓ Ticker object created for {symbol}")
        
        # Test all possible financial statement methods
        methods_to_test = [
            # Old method names (currently used in scripts)
            ('financials', 'Annual Income Statement (old method)'),
            ('quarterly_financials', 'Quarterly Income Statement (old method)'),
            ('balance_sheet', 'Annual Balance Sheet'),
            ('quarterly_balance_sheet', 'Quarterly Balance Sheet'),
            ('cashflow', 'Annual Cash Flow (old method)'),
            ('quarterly_cashflow', 'Quarterly Cash Flow (old method)'),
            
            # New method names (potentially working)
            ('income_stmt', 'Annual Income Statement (new method)'),
            ('quarterly_income_stmt', 'Quarterly Income Statement (new method)'),
            ('cash_flow', 'Annual Cash Flow (new method)'),
            ('quarterly_cash_flow', 'Quarterly Cash Flow (new method)'),
            
            # Other potential methods
            ('balancesheet', 'Annual Balance Sheet (alt name)'),
            ('earnings', 'Annual Earnings'),
            ('quarterly_earnings', 'Quarterly Earnings'),
        ]
        
        working_methods = []
        
        for method_name, description in methods_to_test:
            try:
                if hasattr(ticker, method_name):
                    data = getattr(ticker, method_name)
                    
                    if data is None:
                        print(f"  ✗ {method_name}: Returns None")
                    elif isinstance(data, pd.DataFrame):
                        if data.empty:
                            print(f"  ✗ {method_name}: Returns empty DataFrame")
                        else:
                            print(f"  ✓ {method_name}: Returns DataFrame {data.shape} - {description}")
                            working_methods.append((method_name, description, data.shape))
                            
                            # Show sample data for the first working method
                            if len(working_methods) == 1:
                                print(f"    Sample columns: {list(data.columns[:3])}")
                                print(f"    Sample rows: {list(data.index[:3])}")
                    else:
                        print(f"  ? {method_name}: Returns {type(data)} - {description}")
                else:
                    print(f"  ✗ {method_name}: Method doesn't exist")
                    
            except Exception as e:
                print(f"  ✗ {method_name}: Error - {e}")
        
        print(f"\n✓ Working methods for {symbol}: {len(working_methods)}")
        for method, desc, shape in working_methods:
            print(f"  - {method}: {desc} {shape}")
            
        return working_methods
        
    except Exception as e:
        print(f"✗ Failed to test {symbol}: {e}")
        return []

def test_multiple_symbols():
    """Test multiple symbols to ensure methods work consistently"""
    test_symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "JPM"]
    
    all_results = {}
    
    for symbol in test_symbols:
        print(f"\n{'='*50}")
        working_methods = test_symbol_methods(symbol)
        all_results[symbol] = working_methods
        
    # Summary
    print(f"\n{'='*50}")
    print("SUMMARY OF WORKING METHODS ACROSS ALL SYMBOLS")
    print(f"{'='*50}")
    
    # Find methods that work for all symbols
    if all_results:
        first_symbol_methods = set(method for method, _, _ in all_results[list(all_results.keys())[0]])
        common_methods = first_symbol_methods.copy()
        
        for symbol, methods_list in all_results.items():
            symbol_methods = set(method for method, _, _ in methods_list)
            common_methods = common_methods.intersection(symbol_methods)
            
        print(f"\nMethods that work for ALL symbols ({len(common_methods)}):")
        for method in sorted(common_methods):
            print(f"  ✓ {method}")
            
        print(f"\nPer-symbol working methods:")
        for symbol, methods_list in all_results.items():
            method_names = [method for method, _, _ in methods_list]
            print(f"  {symbol}: {method_names}")
    
    return all_results

def recommend_updates():
    """Provide recommendations for updating the scripts"""
    print(f"\n{'='*50}")
    print("RECOMMENDATIONS FOR SCRIPT UPDATES")
    print(f"{'='*50}")
    
    # Test the key methods our scripts use
    test_symbol = "AAPL"
    ticker = yf.Ticker(test_symbol)
    
    current_script_methods = {
        'loadannualincomestatement.py': 'financials',
        'loadquarterlyincomestatement.py': 'quarterly_financials',
        'loadannualbalancesheet.py': 'balance_sheet',
        'loadquarterlybalancesheet.py': 'quarterly_balance_sheet',
        'loadannualcashflow.py': 'cashflow',
        'loadquarterlycashflow.py': 'quarterly_cashflow'
    }
    
    replacement_methods = {
        'financials': ['income_stmt', 'financials'],
        'quarterly_financials': ['quarterly_income_stmt', 'quarterly_financials'],
        'balance_sheet': ['balance_sheet', 'balancesheet'],
        'quarterly_balance_sheet': ['quarterly_balance_sheet'],
        'cashflow': ['cash_flow', 'cashflow'],
        'quarterly_cashflow': ['quarterly_cash_flow', 'quarterly_cashflow']
    }
    
    recommendations = {}
    
    for script, current_method in current_script_methods.items():
        print(f"\n{script}:")
        print(f"  Current method: {current_method}")
        
        # Test current method
        try:
            current_data = getattr(ticker, current_method)
            if current_data is not None and not current_data.empty:
                print(f"  ✓ Current method WORKS: {current_data.shape}")
                recommendations[script] = current_method
                continue
            else:
                print(f"  ✗ Current method returns empty data")
        except Exception as e:
            print(f"  ✗ Current method fails: {e}")
        
        # Test replacement methods
        replacement_found = False
        for replacement in replacement_methods.get(current_method, []):
            try:
                if hasattr(ticker, replacement):
                    replacement_data = getattr(ticker, replacement)
                    if replacement_data is not None and not replacement_data.empty:
                        print(f"  ✓ REPLACEMENT FOUND: {replacement} {replacement_data.shape}")
                        recommendations[script] = replacement
                        replacement_found = True
                        break
                    else:
                        print(f"  ✗ {replacement}: returns empty data")
                else:
                    print(f"  ✗ {replacement}: method doesn't exist")
            except Exception as e:
                print(f"  ✗ {replacement}: error - {e}")
        
        if not replacement_found:
            print(f"  ⚠️ NO WORKING REPLACEMENT FOUND")
            recommendations[script] = None
    
    print(f"\n{'='*20} FINAL RECOMMENDATIONS {'='*20}")
    for script, recommended_method in recommendations.items():
        if recommended_method:
            print(f"✓ {script}: Use '{recommended_method}'")
        else:
            print(f"✗ {script}: NO WORKING METHOD FOUND")
    
    return recommendations

if __name__ == "__main__":
    print("Testing yfinance financial statement methods...")
    print(f"Python version: {sys.version}")
    
    try:
        print(f"yfinance version: {yf.__version__}")
    except:
        print("yfinance version: Unknown")
    
    # Test multiple symbols to find working methods
    results = test_multiple_symbols()
    
    # Get specific recommendations for our scripts
    recommendations = recommend_updates()
    
    print(f"\n{'='*50}")
    print("TEST COMPLETE")
    print(f"{'='*50}")