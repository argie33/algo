#!/usr/bin/env python3
import yfinance as yf
from pprint import pprint

# Test with a few sample stocks
symbols = ['AAPL', 'MSFT', 'GOOG']

for symbol in symbols:
    print(f"\n\n{'='*50}")
    print(f"Testing {symbol}")
    print(f"{'='*50}")
    
    ticker = yf.Ticker(symbol)
    
    print("\n--- Earnings History ---")
    pprint(ticker.earnings_history)
    
    # Print the data types and structure
    if ticker.earnings_history is not None and not ticker.earnings_history.empty:
        print("\nData types:")
        print(ticker.earnings_history.dtypes)
        
        print("\nExample row structure:")
        print(ticker.earnings_history.iloc[0].to_dict())
