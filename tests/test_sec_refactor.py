#!/usr/bin/env python3
"""Test SEC Edgar refactored modules to diagnose data loading issues."""

import sys
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Test 1: Can we import the refactored modules?
print("=" * 60)
print("TEST 1: Import refactored modules")
print("=" * 60)
try:
    from utils.external.sec_edgar import SecEdgarClient
    from utils.external import sec_statements
    print("✓ Imports successful")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Create a SecEdgarClient and check ticker resolution
print("\n" + "=" * 60)
print("TEST 2: Ticker resolution (symbol_to_cik)")
print("=" * 60)
try:
    client = SecEdgarClient()
    for symbol in ["AAPL", "MSFT"]:
        cik = client.symbol_to_cik(symbol)
        print(f"✓ {symbol} -> {cik}")

    # Test that unknown symbols raise an exception
    try:
        client.symbol_to_cik("UNKNOWN")
        print("✗ UNKNOWN should have raised an exception")
        sys.exit(1)
    except (ValueError, RuntimeError):
        print("✓ UNKNOWN raises exception (fail-fast)")
except Exception as e:
    print(f"✗ Ticker resolution failed: {e}")
    sys.exit(1)

# Test 3: Fetch company facts
print("\n" + "=" * 60)
print("TEST 3: Fetch company facts (get_company_facts)")
print("=" * 60)
try:
    aapl_cik = client.symbol_to_cik("AAPL")
    if not aapl_cik:
        print("✗ Could not resolve AAPL")
        sys.exit(1)

    facts = client.get_company_facts(aapl_cik)
    if facts and "facts" in facts:
        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        print(f"✓ Got {len(us_gaap)} concepts from us-gaap")

        # Check for key concepts
        key_concepts = ["Assets", "AssetsCurrent", "Revenues", "NetIncomeLoss"]
        found = sum(1 for c in key_concepts if c in us_gaap)
        print(f"  {found}/{len(key_concepts)} key concepts found")
    else:
        print("✗ No facts returned")
        sys.exit(1)
except Exception as e:
    print(f"✗ get_company_facts failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Get balance sheet
print("\n" + "=" * 60)
print("TEST 4: Balance sheet (get_balance_sheet)")
print("=" * 60)
try:
    rows = client.get_balance_sheet("AAPL", period="annual")
    if rows:
        print(f"✓ Got {len(rows)} annual balance sheet rows")
        # Show first row
        if rows:
            row = rows[0]
            print(f"  Sample row keys: {list(row.keys())[:10]}...")
            print(f"  symbol: {row.get('symbol')}")
            print(f"  fiscal_year: {row.get('fiscal_year')}")
            print(f"  total_assets: {row.get('total_assets')}")
    else:
        print("✗ No balance sheet rows returned")
except Exception as e:
    print(f"✗ get_balance_sheet failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Get income statement
print("\n" + "=" * 60)
print("TEST 5: Income statement (get_income_statement)")
print("=" * 60)
try:
    rows = client.get_income_statement("AAPL", period="annual")
    if rows:
        print(f"✓ Got {len(rows)} annual income statement rows")
        if rows:
            row = rows[0]
            print(f"  symbol: {row.get('symbol')}")
            print(f"  fiscal_year: {row.get('fiscal_year')}")
            print(f"  revenue: {row.get('revenue')}")
    else:
        print("✗ No income statement rows returned")
except Exception as e:
    print(f"✗ get_income_statement failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Get cash flow
print("\n" + "=" * 60)
print("TEST 6: Cash flow (get_cash_flow)")
print("=" * 60)
try:
    rows = client.get_cash_flow("AAPL", period="annual")
    if rows:
        print(f"✓ Got {len(rows)} annual cash flow rows")
        if rows:
            row = rows[0]
            print(f"  symbol: {row.get('symbol')}")
            print(f"  fiscal_year: {row.get('fiscal_year')}")
            print(f"  operating_cash_flow: {row.get('operating_cash_flow')}")
    else:
        print("✗ No cash flow rows returned")
except Exception as e:
    print(f"✗ get_cash_flow failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
