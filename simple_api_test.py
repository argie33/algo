#!/usr/bin/env python3
"""
Simple test of yfinance API to check if data is being returned properly
"""
import yfinance as yf
import json

def test_yfinance():
    print("Testing yfinance API with AAPL...")
    
    try:
        ticker = yf.Ticker("AAPL")
        info = ticker.info
        
        if not info:
            print("❌ No data returned from yfinance")
            return
        
        print(f"✅ Data received! Keys count: {len(info)}")
        
        # Check key fields that loadinfo script needs
        important_fields = [
            'symbol', 'shortName', 'longName', 'sector', 'industry',
            'marketCap', 'enterpriseValue', 'totalRevenue', 'regularMarketPrice',
            'fullTimeEmployees', 'website', 'longBusinessSummary'
        ]
        
        print("\nChecking important fields:")
        present = 0
        for field in important_fields:
            has_data = field in info and info[field] is not None
            status = "✅" if has_data else "❌"
            value = info.get(field, "MISSING")
            
            # Truncate long values
            if isinstance(value, str) and len(value) > 50:
                value = value[:47] + "..."
            elif isinstance(value, (int, float)) and value > 1000000:
                value = f"{value:,.0f}"
                
            print(f"  {status} {field}: {value}")
            if has_data:
                present += 1
        
        print(f"\n📊 Summary: {present}/{len(important_fields)} important fields have data")
        
        if present < 8:
            print("⚠️  WARNING: Missing too many important fields - this could cause 'No stocks match criteria'")
        else:
            print("✅ API data looks good!")
            
    except Exception as e:
        print(f"❌ Error testing yfinance: {e}")

if __name__ == "__main__":
    test_yfinance()
