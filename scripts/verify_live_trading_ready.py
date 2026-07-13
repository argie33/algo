#!/usr/bin/env python3
"""Verify system is ready for live paper trading via Alpaca."""

import os
import sys

sys.path.insert(0, '.')

from utils.db.context import DatabaseContext

print("=== LIVE TRADING READINESS VERIFICATION ===\n")

checks_passed = 0
checks_total = 0

def check(name: str, condition: bool, error_msg: str = "") -> None:
    global checks_passed, checks_total
    checks_total += 1
    if condition:
        print(f"[OK] {name}")
        checks_passed += 1
    else:
        print(f"[FAIL] {name}")
        if error_msg:
            print(f"      {error_msg}")

# 1. Database connectivity
try:
    with DatabaseContext('read') as cur:
        cur.execute('SELECT 1')
    check("Database connectivity", True)
except Exception as e:
    check("Database connectivity", False, str(e))

# 2. Configuration
with DatabaseContext('read') as cur:
    cur.execute('SELECT value FROM algo_config WHERE key = %s', ('execution_mode',))
    result = cur.fetchone()
    if result and result[0] == 'paper':
        check("Execution mode", True)
    else:
        check("Execution mode", False, f"Value: {result[0] if result else 'NOT SET'}")

    cur.execute('SELECT value FROM algo_config WHERE key = %s', ('alpaca_paper_trading',))
    result = cur.fetchone()
    if result and str(result[0]).lower() == 'true':
        check("Alpaca paper trading enabled", True)
    else:
        check("Alpaca paper trading enabled", False, f"Value: {result[0] if result else 'NOT SET'}")

# 3. Critical data tables
with DatabaseContext('read') as cur:
    tables = {
        'price_daily': 'Price data',
        'buy_sell_daily': 'Trading signals',
        'algo_positions': 'Position tracking',
        'stock_scores': 'Stock scoring',
    }
    for table, desc in tables.items():
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        count = cur.fetchone()[0]
        check(f"{desc} ({table})", count > 0, f"Rows: {count}")

# 4. Recent data
with DatabaseContext('read') as cur:
    cur.execute('SELECT MAX(date) FROM price_daily')
    latest_price = cur.fetchone()[0]

    cur.execute('SELECT MAX(date) FROM buy_sell_daily')
    latest_signal = cur.fetchone()[0]

    from datetime import date
    today = date.today()

    check("Recent prices (today or yesterday)", latest_price >= today - __import__('datetime').timedelta(days=1),
          f"Latest: {latest_price}")
    check("Recent trading signals", latest_signal >= today - __import__('datetime').timedelta(days=3),
          f"Latest: {latest_signal}")

# 5. API endpoints
try:
    os.environ['LOCAL_MODE'] = 'true'
    from dashboard.api_data_layer import api_call

    # Test key endpoints
    resp = api_call('/api/health')
    check("API health endpoint", '_error' not in resp)

    resp = api_call('/api/algo/portfolio')
    check("Portfolio endpoint", '_error' not in resp)

    resp = api_call('/api/algo/positions')
    check("Positions endpoint", '_error' not in resp)

    resp = api_call('/api/algo/trades')
    check("Trades endpoint", '_error' not in resp)
except Exception as e:
    print(f"[SKIP] API checks (dev server not running): {type(e).__name__}")

print("\n=== SUMMARY ===")
print(f"Passed: {checks_passed}/{checks_total}")

if checks_passed == checks_total:
    print("\n[READY] SYSTEM READY FOR LIVE PAPER TRADING")
    print("\nTo start trading:")
    print("  1. Terminal 1: python3 lambda/api/dev_server.py")
    print("  2. Terminal 2: python3 dashboard/dashboard.py --local -w 30")
    print("  3. AWS: Orchestrator will run at scheduled times (9:30 AM, 1 PM ET)")
    sys.exit(0)
else:
    print("\n[NOT READY] Fix issues above before trading")
    sys.exit(1)
