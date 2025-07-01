#!/usr/bin/env python3
"""
Test script to verify the updated financial statement functions work correctly
Tests the new methods with fallbacks against real yfinance API
"""

import sys
import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, date
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def safe_convert_to_float(value) -> Optional[float]:
    """Safely convert value to float, handling various edge cases"""
    if pd.isna(value) or value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(',', '').replace('$', '').strip()
            if value == '' or value == '-' or value.lower() == 'n/a':
                return None
        return float(value)
    except (ValueError, TypeError):
        return None

def safe_convert_date(dt) -> Optional[date]:
    """Safely convert various date formats to date object"""
    if pd.isna(dt) or dt is None:
        return None
    try:
        if hasattr(dt, 'date'):
            return dt.date()
        elif isinstance(dt, str):
            return datetime.strptime(dt, '%Y-%m-%d').date()
        elif isinstance(dt, date):
            return dt
        else:
            return pd.to_datetime(dt).date()
    except (ValueError, TypeError):
        return None

# Updated functions from the scripts
def get_income_statement_data(symbol: str) -> Optional[pd.DataFrame]:
    """Get annual income statement data using proper yfinance API with fallback methods"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Try multiple methods in order of preference
        methods_to_try = [
            ('income_stmt', 'annual income statement (new method)'),
            ('financials', 'annual income statement (legacy method)'),
        ]
        
        income_statement = None
        
        for method_name, description in methods_to_try:
            try:
                if hasattr(ticker, method_name):
                    logging.info(f"Trying {method_name} for {symbol}")
                    income_statement = getattr(ticker, method_name)
                    
                    if income_statement is not None and not income_statement.empty:
                        logging.info(f"✓ Successfully got data using {method_name} for {symbol}")
                        break
                    else:
                        logging.warning(f"{method_name} returned empty data for {symbol}")
                else:
                    logging.warning(f"Method {method_name} not available for {symbol}")
            except Exception as e:
                logging.warning(f"Error with {method_name} for {symbol}: {e}")
                continue
        
        if income_statement is None or income_statement.empty:
            logging.warning(f"No income statement data returned by any method for {symbol}")
            return None
        
        # Check if DataFrame contains any actual data (not all NaN)
        if income_statement.isna().all().all():
            logging.warning(f"Income statement data is all NaN for {symbol}")
            return None
            
        # Check if we have at least one column with data
        valid_columns = [col for col in income_statement.columns if not income_statement[col].isna().all()]
        if not valid_columns:
            logging.warning(f"No valid income statement columns found for {symbol}")
            return None
            
        # Sort columns by date (most recent first)
        income_statement = income_statement.reindex(sorted(income_statement.columns, reverse=True), axis=1)
        
        logging.info(f"Retrieved income statement data for {symbol}: {len(income_statement.columns)} periods, {len(income_statement.index)} line items")
        return income_statement
        
    except Exception as e:
        logging.error(f"Error fetching income statement for {symbol}: {e}")
        return None

def get_quarterly_income_statement_data(symbol: str) -> Optional[pd.DataFrame]:
    """Get quarterly income statement data using proper yfinance API with fallback methods"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Try multiple methods in order of preference
        methods_to_try = [
            ('quarterly_income_stmt', 'quarterly income statement (new method)'),
            ('quarterly_financials', 'quarterly income statement (legacy method)'),
        ]
        
        income_statement = None
        
        for method_name, description in methods_to_try:
            try:
                if hasattr(ticker, method_name):
                    logging.info(f"Trying {method_name} for {symbol}")
                    income_statement = getattr(ticker, method_name)
                    
                    if income_statement is not None and not income_statement.empty:
                        logging.info(f"✓ Successfully got data using {method_name} for {symbol}")
                        break
                    else:
                        logging.warning(f"{method_name} returned empty data for {symbol}")
                else:
                    logging.warning(f"Method {method_name} not available for {symbol}")
            except Exception as e:
                logging.warning(f"Error with {method_name} for {symbol}: {e}")
                continue
        
        if income_statement is None or income_statement.empty:
            logging.warning(f"No quarterly income statement data returned by any method for {symbol}")
            return None
        
        # Check if DataFrame contains any actual data (not all NaN)
        if income_statement.isna().all().all():
            logging.warning(f"Quarterly income statement data is all NaN for {symbol}")
            return None
            
        # Check if we have at least one column with data
        valid_columns = [col for col in income_statement.columns if not income_statement[col].isna().all()]
        if not valid_columns:
            logging.warning(f"No valid quarterly income statement columns found for {symbol}")
            return None
            
        # Sort columns by date (most recent first)
        income_statement = income_statement.reindex(sorted(income_statement.columns, reverse=True), axis=1)
        
        logging.info(f"Retrieved quarterly income statement data for {symbol}: {len(income_statement.columns)} periods, {len(income_statement.index)} line items")
        return income_statement
        
    except Exception as e:
        logging.error(f"Error fetching quarterly income statement for {symbol}: {e}")
        return None

def get_balance_sheet_data(symbol: str) -> Optional[pd.DataFrame]:
    """Get annual balance sheet data using proper yfinance API with fallback methods"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Try multiple methods in order of preference
        methods_to_try = [
            ('balance_sheet', 'annual balance sheet'),
            ('balancesheet', 'annual balance sheet (alt name)'),
        ]
        
        balance_sheet = None
        
        for method_name, description in methods_to_try:
            try:
                if hasattr(ticker, method_name):
                    logging.info(f"Trying {method_name} for {symbol}")
                    balance_sheet = getattr(ticker, method_name)
                    
                    if balance_sheet is not None and not balance_sheet.empty:
                        logging.info(f"✓ Successfully got data using {method_name} for {symbol}")
                        break
                    else:
                        logging.warning(f"{method_name} returned empty data for {symbol}")
                else:
                    logging.warning(f"Method {method_name} not available for {symbol}")
            except Exception as e:
                logging.warning(f"Error with {method_name} for {symbol}: {e}")
                continue
        
        if balance_sheet is None or balance_sheet.empty:
            logging.warning(f"No balance sheet data returned by any method for {symbol}")
            return None
        
        # Additional processing...
        logging.info(f"Retrieved balance sheet data for {symbol}: {balance_sheet.shape}")
        return balance_sheet
        
    except Exception as e:
        logging.error(f"Error fetching balance sheet for {symbol}: {e}")
        return None

def get_cash_flow_data(symbol: str) -> Optional[pd.DataFrame]:
    """Get annual cash flow data using proper yfinance API with fallback methods"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Try multiple methods in order of preference
        methods_to_try = [
            ('cash_flow', 'annual cash flow (new method)'),
            ('cashflow', 'annual cash flow (legacy method)'),
        ]
        
        cash_flow = None
        
        for method_name, description in methods_to_try:
            try:
                if hasattr(ticker, method_name):
                    logging.info(f"Trying {method_name} for {symbol}")
                    cash_flow = getattr(ticker, method_name)
                    
                    if cash_flow is not None and not cash_flow.empty:
                        logging.info(f"✓ Successfully got data using {method_name} for {symbol}")
                        break
                    else:
                        logging.warning(f"{method_name} returned empty data for {symbol}")
                else:
                    logging.warning(f"Method {method_name} not available for {symbol}")
            except Exception as e:
                logging.warning(f"Error with {method_name} for {symbol}: {e}")
                continue
        
        if cash_flow is None or cash_flow.empty:
            logging.warning(f"No cash flow data returned by any method for {symbol}")
            return None
        
        logging.info(f"Retrieved cash flow data for {symbol}: {cash_flow.shape}")
        return cash_flow
        
    except Exception as e:
        logging.error(f"Error fetching cash flow for {symbol}: {e}")
        return None

def test_all_functions():
    """Test all updated financial statement functions"""
    print(f"Testing updated financial statement functions...")
    print(f"yfinance version: {yf.__version__}")
    print(f"Testing at: {datetime.now()}")
    print("="*60)
    
    test_symbols = ["AAPL", "MSFT", "GOOGL"]
    
    functions_to_test = [
        (get_income_statement_data, "Annual Income Statement"),
        (get_quarterly_income_statement_data, "Quarterly Income Statement"),
        (get_balance_sheet_data, "Annual Balance Sheet"),
        (get_cash_flow_data, "Annual Cash Flow"),
    ]
    
    results = {}
    
    for symbol in test_symbols:
        print(f"\n{'='*20} Testing {symbol} {'='*20}")
        results[symbol] = {}
        
        for func, description in functions_to_test:
            print(f"\n--- {description} ---")
            try:
                data = func(symbol)
                if data is not None and not data.empty:
                    print(f"✓ SUCCESS: {description} for {symbol}")
                    print(f"  Shape: {data.shape}")
                    print(f"  Columns: {list(data.columns[:3])}...")
                    print(f"  Sample rows: {list(data.index[:3])}...")
                    results[symbol][description] = "SUCCESS"
                else:
                    print(f"✗ FAILED: {description} for {symbol} - No data returned")
                    results[symbol][description] = "NO_DATA"
            except Exception as e:
                print(f"✗ ERROR: {description} for {symbol} - {e}")
                results[symbol][description] = f"ERROR: {e}"
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY RESULTS")
    print(f"{'='*60}")
    
    for symbol, symbol_results in results.items():
        print(f"\n{symbol}:")
        for description, result in symbol_results.items():
            status = "✓" if result == "SUCCESS" else "✗"
            print(f"  {status} {description}: {result}")
    
    # Overall success rate
    total_tests = len(test_symbols) * len(functions_to_test)
    successful_tests = sum(1 for symbol_results in results.values() 
                          for result in symbol_results.values() 
                          if result == "SUCCESS")
    
    print(f"\nOverall Success Rate: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")
    
    return results

if __name__ == "__main__":
    results = test_all_functions()
    print(f"\n{'='*60}")
    print("TEST COMPLETE")
    print(f"{'='*60}")