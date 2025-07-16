#!/usr/bin/env python3
"""
SIMPLE STOCK SYMBOLS LOADER - BYPASS ALL COMPLEXITY
This is a minimal version that just loads stock symbols directly
"""
import os
import requests
import csv
import json
import sys

def simple_load():
    print("🎯 SIMPLE STOCK SYMBOLS LOADER STARTING...")
    
    # Get basic stock symbols from NASDAQ
    try:
        print("📥 Downloading NASDAQ symbols...")
        response = requests.get("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt")
        lines = response.text.strip().split('\n')
        
        # Parse the CSV data (skip header)
        symbols = []
        for line in lines[1:]:  # Skip header
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 2:
                    symbol = parts[0].strip()
                    name = parts[1].strip()
                    if symbol and symbol != 'Symbol' and not symbol.endswith('$'):
                        symbols.append({'symbol': symbol, 'name': name})
        
        print(f"✅ Found {len(symbols)} symbols")
        
        # Just save to a JSON file for now to prove it works
        with open('/tmp/stock_symbols.json', 'w') as f:
            json.dump(symbols, f, indent=2)
        
        print("✅ Symbols saved to /tmp/stock_symbols.json")
        print("🎯 PROOF: The stock symbols loading logic WORKS")
        print("🔍 First 5 symbols:")
        for i, sym in enumerate(symbols[:5]):
            print(f"   {sym['symbol']}: {sym['name']}")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = simple_load()
    if success:
        print("✅ SUCCESS: Stock symbols can be loaded!")
        print("🎯 Now we just need to get YOUR full script running in ECS")
        sys.exit(0)
    else:
        print("❌ FAILED: Even simple loading failed")
        sys.exit(1)