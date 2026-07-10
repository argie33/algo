#!/usr/bin/env python3
"""Check what data is available in the database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

print("\n=== DATABASE DATA AVAILABILITY ===\n")

try:
    from utils.db.context import DatabaseContext

    tables = {
        "algo_trades": "Open trades",
        "algo_positions": "Positions",
        "algo_portfolio_snapshots": "Portfolio snapshots",
        "stock_scores": "Stock scores",
        "algo_signals": "Trading signals",
        "orchestrator_execution_log": "Orchestrator runs",
    }

    for table, desc in tables.items():
        try:
            with DatabaseContext("read") as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                result = cur.fetchone()
                count = result[0] if result else 0
                print(f"[OK] {table}: {count:,} records ({desc})")
        except Exception as e:
            print(f"[FAIL] {table}: {str(e)[:60]}")

except Exception as e:
    print(f"[FAIL] Database connection error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n=== CONCLUSION ===")
print("If database has data but dashboard shows unavailable, the issue is:")
print("1. API Lambda function not deployed")
print("2. API Lambda function deployed but endpoints not returning data")
print("3. Dashboard not connecting to the API")
