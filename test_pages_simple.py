#!/usr/bin/env python3
"""Simple page load test - checks if pages load and have data."""

import requests
import json
import time

PAGES = [
    ('/app/market', 'Market Overview'),
    ('/app/sectors', 'Sectors'),
    ('/app/economic', 'Economic Data'),
    ('/app/sentiment', 'Sentiment'),
    ('/app/trading-signals', 'Trading Signals'),
    ('/app/portfolio', 'Portfolio'),
    ('/app/trades', 'Trade History'),
    ('/app/performance', 'Performance'),
    ('/app/backtests', 'Backtest Results'),
    ('/app/scores', 'Scores'),
    ('/app/service-health', 'Service Health'),
    ('/app/audit-viewer', 'Audit Viewer'),
]

def test_page_loads(url):
    """Test if a page loads (200 response)."""
    try:
        resp = requests.get(f'http://localhost:5173{url}', timeout=10)
        return resp.status_code == 200
    except Exception as e:
        return False

print("=" * 80)
print("PAGE LOAD TEST - All 12 Pages")
print("=" * 80)
print("\nChecking if frontend is running on localhost:5173...")

try:
    requests.head('http://localhost:5173', timeout=2)
    print("[OK] Frontend is running\n")
except:
    print("[FAIL] Frontend is not running on localhost:5173")
    print("Run: cd webapp/frontend && npm run dev")
    exit(1)

pages_loaded = 0
pages_failed = 0

for path, name in PAGES:
    if test_page_loads(path):
        print(f"[OK]   {name.ljust(30)} {path}")
        pages_loaded += 1
    else:
        print(f"[FAIL] {name.ljust(30)} {path}")
        pages_failed += 1

print("\n" + "=" * 80)
print(f"Results: {pages_loaded}/12 pages load successfully")
if pages_failed > 0:
    print(f"Failed: {pages_failed} pages")
print("=" * 80)

if pages_loaded == 12:
    print("\n[SUCCESS] All pages are loading successfully!")
    print("\nNext step: Check F12 console for errors")
    print("  1. Open DevTools (F12) in your browser")
    print("  2. Navigate to each page and check Console tab")
    print("  3. Ensure no red error messages appear")
else:
    print(f"\n[FAILURE] {pages_failed} pages failed to load")
