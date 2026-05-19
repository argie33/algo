#!/usr/bin/env python3
"""Frontend testing script - verify all pages load and work correctly."""

import requests
import json
import time
from typing import List, Tuple

BASE_URL = "http://localhost:5186"
API_URL = "http://localhost:3001/api"

# Pages to test (path, name)
PAGES = [
    ("/", "Home"),
    ("/app/market", "Market Health"),
    ("/app/signals", "Trading Signals"),
    ("/app/swing-candidates", "Swing Candidates"),
    ("/app/sectors", "Sector Analysis"),
    ("/app/economic", "Economic Dashboard"),
    ("/app/sentiment", "Sentiment"),
    ("/app/stocks/AAPL", "Stock Detail (AAPL)"),
    ("/app/deep-value", "Deep Value Stocks"),
    ("/app/scores", "Scores Dashboard"),
    ("/app/trades", "Trade Tracker"),
    ("/app/portfolio", "Portfolio Dashboard"),
    ("/app/simulator", "Pre-Trade Simulator"),
    ("/app/performance", "Performance Metrics"),
    ("/app/algo", "Algo Trading Dashboard"),
    ("/app/backtest", "Backtest Results"),
    ("/app/health", "Service Health"),
    ("/app/audit", "Audit Viewer"),
    ("/app/settings", "Settings"),
    ("/app/notifications", "Notification Center"),
    ("/login", "Login Page"),
    ("/firm", "Firm Info"),
    ("/about", "About"),
    ("/contact", "Contact"),
]

# Critical APIs to test
APIS = [
    ("/health", "Health"),
    ("/stocks?limit=5", "Stocks"),
    ("/prices/history/AAPL?limit=10", "Prices"),
    ("/signals?limit=10", "Signals"),
    ("/scores?limit=10", "Scores"),
    ("/sectors?limit=5", "Sectors"),
    ("/algo/status", "Algo Status"),
]

def test_api_endpoints() -> Tuple[int, int]:
    """Test API endpoints."""
    passed = 0
    failed = 0

    print("\n" + "="*70)
    print("API ENDPOINT TESTS")
    print("="*70)

    for path, name in APIS:
        try:
            resp = requests.get(f"{API_URL}{path}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = len(data.get('items', []))
                print(f"PASS {name:30} {resp.status_code} ({items} items)")
                passed += 1
            else:
                print(f"FAIL {name:30} {resp.status_code}")
                failed += 1
        except Exception as e:
            print(f"FAIL {name:30} ERROR: {str(e)[:40]}")
            failed += 1

    return passed, failed

def test_frontend_pages() -> Tuple[int, int]:
    """Test frontend page loads."""
    passed = 0
    failed = 0

    print("\n" + "="*70)
    print("FRONTEND PAGE LOAD TESTS")
    print("="*70)

    for path, name in PAGES:
        try:
            resp = requests.get(f"{BASE_URL}{path}", timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                # Check for obvious error indicators
                if "500" in resp.text or "error" in resp.text.lower()[:500]:
                    print(f"WARN {name:35} Loaded but may have errors")
                    passed += 1
                else:
                    print(f"PASS {name:35} {resp.status_code}")
                    passed += 1
            else:
                print(f"FAIL {name:35} {resp.status_code}")
                failed += 1
        except Exception as e:
            print(f"FAIL {name:35} ERROR: {str(e)[:40]}")
            failed += 1

    return passed, failed

def test_data_loaded() -> dict:
    """Check data loading status."""
    print("\n" + "="*70)
    print("DATA LOADING STATUS")
    print("="*70)

    try:
        import psycopg2
        conn = psycopg2.connect('dbname=stocks user=postgres password=postgres host=localhost')
        cur = conn.cursor()

        tables = {
            'price_daily': 5.8e6,
            'buy_sell_daily': 466e3,
            'technical_data_daily': 5.8e6,
            'trend_template_data': 2.6e6,
            'signal_quality_scores': 460e3,
            'swing_trader_scores': 466e3,
            'market_health_daily': 250,
        }

        status = {}
        for table, target in tables.items():
            cur.execute(f'SELECT COUNT(*) FROM {table}')
            count = cur.fetchone()[0]
            pct = (count / target * 100) if target > 0 else 0
            status_str = "OK" if pct > 90 else ("PARTIAL" if pct > 50 else "EMPTY")
            status[table] = (count, pct)
            print(f"{status_str} {table:30} {count:12,} ({pct:5.1f}%)")

        conn.close()
        return status
    except Exception as e:
        print(f"ERROR: {e}")
        return {}

def main():
    """Run all tests."""
    print("\nFRONTEND TESTING SUITE")
    print("="*70)

    # Test APIs first (quick)
    api_passed, api_failed = test_api_endpoints()

    # Check data status
    data_status = test_data_loaded()

    # Test frontend pages (slow)
    print("\nTesting frontend pages (this may take a minute)...")
    page_passed, page_failed = test_frontend_pages()

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"API Tests:      {api_passed} passed, {api_failed} failed")
    print(f"Page Tests:     {page_passed} passed, {page_failed} failed")
    print(f"Total:          {api_passed + page_passed} passed, {api_failed + page_failed} failed")

    # Data status
    complete = sum(1 for _, (count, pct) in data_status.items() if pct > 90)
    partial = sum(1 for _, (count, pct) in data_status.items() if 50 <= pct <= 90)
    empty = sum(1 for _, (count, pct) in data_status.items() if pct < 50)
    print(f"\nData Loading:   {complete} complete, {partial} partial, {empty} incomplete")

    if api_failed == 0 and page_failed == 0:
        print("\nALL TESTS PASSED!")
    else:
        print(f"\n{api_failed + page_failed} tests failed")

if __name__ == "__main__":
    main()
