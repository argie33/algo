#!/usr/bin/env python3
"""Diagnose why API isn't returning data even though database has it."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

print("\n=== API INTEGRATION DIAGNOSTIC ===\n")

# Check 1: Can we import the API handlers?
print("[1] Checking API handler imports...")
try:
    from lambda.api.routes.algo_handlers import dashboard
    print("  [OK] API dashboard handler imported")
except ImportError as e:
    print(f"  [FAIL] Cannot import API handlers: {e}")

# Check 2: Do API endpoints exist in the contract?
print("\n[2] Checking API contract definitions...")
try:
    from lambda.api.shared_contracts import DASHBOARD_ENDPOINTS
    print(f"  [OK] Found {len(DASHBOARD_ENDPOINTS)} endpoints in contract")

    critical_endpoints = [
        ("run", "Last run status"),
        ("cfg", "Configuration"),
        ("pos", "Positions"),
        ("trades", "Trades"),
        ("port", "Portfolio"),
    ]

    for key, desc in critical_endpoints:
        if key in DASHBOARD_ENDPOINTS:
            ep = DASHBOARD_ENDPOINTS[key]
            print(f"    - {key}: {ep.get('path', 'N/A')} ({desc})")
        else:
            print(f"    - {key}: MISSING ({desc})")

except ImportError as e:
    print(f"  [FAIL] Cannot import API contract: {e}")

# Check 3: Can we simulate a typical API call?
print("\n[3] Testing API endpoint simulation...")
try:
    from utils.db.context import DatabaseContext

    # Simulate fetching positions (what the API should do)
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT symbol, quantity, entry_price
            FROM algo_positions
            LIMIT 1
        """)
        result = cur.fetchone()
        if result:
            print(f"  [OK] API can query positions from database")
            print(f"      Sample: {result}")
        else:
            print(f"  [WARN] No positions found (but table exists)")

except Exception as e:
    print(f"  [FAIL] Cannot query database: {e}")

# Check 4: Is the API Lambda function deployed?
print("\n[4] Checking AWS Lambda deployment...")
try:
    import os
    if "AWS_LAMBDA_FUNCTION_NAME" in os.environ:
        fn = os.environ["AWS_LAMBDA_FUNCTION_NAME"]
        print(f"  [OK] Running in Lambda: {fn}")
    else:
        print("  [INFO] Not running in Lambda (local/testing mode)")
        print("         This is normal for local development")
except Exception as e:
    print(f"  [FAIL] {e}")

print("\n=== SUMMARY ===")
print("Issue: Database HAS data, but dashboard shows 'data_unavailable'")
print("\nRoot cause options:")
print("1. API Lambda function not deployed to AWS")
print("   - Check: aws lambda list-functions --query 'Functions[?contains(FunctionName, `algo-api`)]'")
print("   - Fix: cd terraform && terraform apply -lock=false (requires AWS IAM permissions)")
print("\n2. API deployed but not returning data")
print("   - Check: Call the API endpoint directly and see what it returns")
print("   - Fix: Review lambda/api/routes/algo_handlers/*.py for data_unavailable markers")
print("\n3. Dashboard not configured to call the API")
print("   - Check: echo $DASHBOARD_API_URL")
print("   - Fix: Set DASHBOARD_API_URL to the API Gateway URL and try again")
print("   - For local: python -m dashboard --local (requires local API server)")
