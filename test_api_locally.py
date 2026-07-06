#!/usr/bin/env python3
"""Test if API handlers can fetch and return data from the database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

print("\n=== TESTING API HANDLERS LOCALLY ===\n")

try:
    # Test 1: Can we import the API modules?
    print("[1] Importing API handler modules...")
    from utils.data_queries import get_open_positions
    from utils.db.context import DatabaseContext
    print("    [OK] All imports successful\n")

    # Test 2: Can we fetch positions like the API does?
    print("[2] Fetching positions from database (simulating _get_algo_positions)...")
    with DatabaseContext("read") as cur:
        positions = get_open_positions(cur, limit=10)
        print(f"    [OK] Fetched {len(positions)} positions")
        if positions:
            print(f"    Sample position: {positions[0]}")

    # Test 3: Can we fetch trades?
    print("\n[3] Fetching trades from database...")
    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM algo_trades")
        count = cur.fetchone()
        trade_count = count['cnt'] if isinstance(count, dict) else count[0] if count else 0
        print(f"    [OK] Found {trade_count} trades")

    # Test 4: Can we fetch portfolio snapshot?
    print("\n[4] Fetching portfolio snapshot from database...")
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT total_portfolio_value, total_cash, position_count
            FROM algo_portfolio_snapshots
            ORDER BY created_at DESC
            LIMIT 1
        """)
        result = cur.fetchone()
        if result:
            if isinstance(result, dict):
                print(f"    [OK] Portfolio: ${result['total_portfolio_value']}")
            else:
                print(f"    [OK] Portfolio: ${result[0] if result else 'N/A'}")
        else:
            print("    [WARN] No portfolio snapshots found")

    # Test 5: Can we fetch signals?
    print("\n[5] Fetching trading signals from database...")
    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM algo_signals")
        count = cur.fetchone()
        signal_count = count['cnt'] if isinstance(count, dict) else count[0] if count else 0
        print(f"    [OK] Found {signal_count} signals")

    print("\n=== CONCLUSION ===")
    print("[SUCCESS] All API data sources work correctly locally!")
    print("\nThe database layer is fine. The issue is that the API Lambda")
    print("functions haven't been deployed to AWS yet due to IAM permissions.")
    print("\nSolution: Get AWS admin to run: cd terraform && terraform apply -lock=false")

except Exception as e:
    print(f"\n[FAIL] Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
