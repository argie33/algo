#!/usr/bin/env python3
"""Quick test to see if yfinance works in current environment."""

import sys
from datetime import date, timedelta

def test_yfinance():
    try:
        import yfinance as yf
        print("[OK] yfinance imported")
    except ImportError as e:
        print(f"[FAIL] Cannot import yfinance: {e}")
        return False

    # Test with a simple, liquid symbol
    symbol = "AAPL"
    start = date.today() - timedelta(days=5)
    end = date.today()
    
    print(f"[TEST] Fetching {symbol} from {start} to {end}...")
    try:
        hist = yf.download(
            symbol,
            start=start,
            end=end,
            auto_adjust=False,
            progress=False,
        )
        if hist is None or hist.empty:
            print("[WARN] No data returned")
            return False
        print(f"[OK] Got {len(hist)} rows from yfinance")
        print(hist.head(2))
        return True
    except Exception as e:
        print(f"[FAIL] yfinance error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_yfinance()
    sys.exit(0 if success else 1)
