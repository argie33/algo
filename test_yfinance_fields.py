#!/usr/bin/env python3
"""
Test script to check what fields yfinance actually returns
"""
import yfinance as yf
import json

def test_yfinance_fields(symbol='AAPL'):
    print(f"Testing yfinance fields for {symbol}")
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        if not info:
            print("No data returned from yfinance")
            return
            
        print(f"\nTotal fields available: {len(info.keys())}")
        
        # Check specific fields we're interested in
        key_fields = [
            'trailingPE', 'forwardPE', 'priceToBook', 'bookValue', 'pegRatio',
            'enterpriseValue', 'enterpriseToRevenue', 'enterpriseToEbitda',
            'totalRevenue', 'netIncome', 'netIncomeToCommon', 'ebitda', 'grossProfits',
            'trailingEps', 'forwardEps', 'currentYear', 'epsCurrentYear',
            'priceEpsCurrentYear', 'dividendRate', 'dividendYield',
            'totalCash', 'totalCashPerShare', 'operatingCashflow', 'freeCashflow',
            'totalDebt', 'debtToEquity', 'quickRatio', 'currentRatio',
            'profitMargins', 'grossMargins', 'operatingMargins',
            'returnOnAssets', 'returnOnEquity'
        ]
        
        print(f"\nChecking key financial fields:")
        found_fields = {}
        missing_fields = []
        
        for field in key_fields:
            value = info.get(field)
            if value is not None:
                found_fields[field] = value
                print(f"✓ {field}: {value}")
            else:
                missing_fields.append(field)
                print(f"✗ {field}: NULL/Missing")
        
        print(f"\nSummary:")
        print(f"Found: {len(found_fields)}/{len(key_fields)} fields")
        print(f"Missing: {missing_fields}")
        
        # Look for alternative field names for missing ones
        print(f"\nLooking for alternative field names:")
        for missing in missing_fields:
            alternatives = [k for k in info.keys() if missing.lower() in k.lower() or 
                          any(word in k.lower() for word in missing.lower().split())]
            if alternatives:
                print(f"{missing} alternatives: {alternatives}")
        
        # Show all field names containing key financial terms
        print(f"\nAll fields containing financial terms:")
        financial_terms = ['revenue', 'income', 'profit', 'margin', 'cash', 'debt', 'ratio', 'eps', 'pe']
        for term in financial_terms:
            matches = [k for k in info.keys() if term in k.lower()]
            if matches:
                print(f"{term}: {matches}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_yfinance_fields('AAPL')

print("=== ALL AVAILABLE FIELDS IN YFINANCE INFO ===")
for key in sorted(info.keys()):
    value = info[key]
    if value is not None:
        print(f"{key}: {value}")

print("\n=== FIELDS THE SCRIPT IS LOOKING FOR BUT MIGHT BE WRONG ===")
fields_to_check = [
    'priceToSalesTrailing12Months',  # Script uses this
    'priceToSales',                  # Alternative name
    'netIncomeToCommon',            # Script uses this
    'netIncome',                    # Alternative name
    'totalRevenue',                 # Script uses this
    'revenue',                      # Alternative name
    'trailingEps',                  # Script uses this
    'epsTrailingTwelveMonths',      # Alternative name
    'forwardEps',                   # Script uses this
    'epsForward',                   # Alternative name
    'currentYear',                  # Script uses this - likely wrong
    'epsCurrentYear',               # Alternative name
    'earningsQuarterlyGrowth',      # Script uses this
    'quarterlyEarningsGrowth',      # Alternative name
    'revenueGrowth',               # Script uses this
    'quarterlyRevenueGrowth',      # Alternative name
    'earningsGrowth',              # Script uses this
    'annualEarningsGrowth',        # Alternative name
    'profitMargins',               # Script uses this
    'profitMargin',                # Alternative name
    'grossMargins',                # Script uses this
    'grossMargin',                 # Alternative name
    'ebitdaMargins',               # Script uses this
    'ebitdaMargin',                # Alternative name
    'operatingMargins',            # Script uses this
    'operatingMargin',             # Alternative name
]

print("\nChecking specific fields:")
for field in fields_to_check:
    value = info.get(field)
    if value is not None:
        print(f"✓ {field}: {value}")
    else:
        print(f"✗ {field}: NOT FOUND")
