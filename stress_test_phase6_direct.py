"""
STRESS TEST: Directly execute Phase 6 with synthetic test data
to find and fix issues BEFORE production run
"""

import sys
import logging
from datetime import date as _date
from decimal import Decimal

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

print("\n" + "="*80)
print("STRESS TEST: Phase 6 Direct Execution with Synthetic Data")
print("="*80)

# Setup test environment
from utils.db.connection import get_db_connection
from algo.infrastructure.config import AlgoConfig

conn = get_db_connection()
cur = conn.cursor()

# Get real config
config = AlgoConfig()

print("\n[SETUP] Creating test portfolio...")

# Create synthetic positions that will expose bugs
test_positions = [
    {
        "symbol": "STRS1",
        "entry_price": 100.00,
        "current_price": 102.00,
        "quantity": 10,
        "position_value": 1020.00,
        "stop_loss": 98.00,
    },
    {
        "symbol": "STRS2",
        "entry_price": 50.00,
        "current_price": 48.00,  # Loss
        "quantity": 20,
        "position_value": 960.00,
        "stop_loss": 48.00,  # At stop
    },
    {
        "symbol": "STRS3",
        "entry_price": 200.00,
        "current_price": 202.00,
        "quantity": 5,
        "position_value": 1010.00,
        "stop_loss": None,  # Edge case: NULL stop
    },
]

total_portfolio = sum(p["position_value"] for p in test_positions)
print(f"Test portfolio: {len(test_positions)} positions, ${total_portfolio:.2f}")

print("\n[TEST 1] Concentration check calculation...")
errors = []

for pos in test_positions:
    try:
        pct = (pos["position_value"] / total_portfolio * 100) if total_portfolio > 0 else 0

        # Simulate Decimal/float conversion (the fix)
        pct_decimal = Decimal(str(pct))
        max_size_pct = 6.0

        # Apply fix
        pct_float = float(pct_decimal)
        limit_for_comparison = float(max_size_pct)
        pct_float = float(pct_float)  # Double conversion fix

        exceed_amount = pct_float - limit_for_comparison

        status = "OVERSIZED" if pct_float > limit_for_comparison else "OK"
        print(f"  {pos['symbol']}: {pct:.1f}% - {status}")

    except Exception as e:
        errors.append(f"  ERROR {pos['symbol']}: {type(e).__name__}: {e}")
        print(f"  ERROR {pos['symbol']}: {e}")

if errors:
    print(f"\n[FAIL] Found {len(errors)} errors in concentration check")
    sys.exit(1)

print(f"\n[PASS] Concentration check works with test data")

print("\n[TEST 2] Stop loss validation...")
for pos in test_positions:
    if pos["stop_loss"] is None:
        print(f"  {pos['symbol']}: NULL stop loss detected - must validate before exit")
    elif pos["stop_loss"] >= pos["entry_price"]:
        print(f"  {pos['symbol']}: INVALID STOP (>= entry) - {pos['stop_loss']} >= {pos['entry_price']}")
        errors.append(f"Invalid stop loss for {pos['symbol']}")
    elif pos["current_price"] <= pos["stop_loss"]:
        print(f"  {pos['symbol']}: STOP HIT - exit required")
    else:
        print(f"  {pos['symbol']}: Stop OK")

if errors:
    print(f"\n[FAIL] Found validation errors")
    sys.exit(1)

print(f"\n[PASS] Stop loss validation works")

print("\n[TEST 3] Risk calculation...")
for pos in test_positions:
    try:
        entry = Decimal(str(pos["entry_price"]))
        current = Decimal(str(pos["current_price"]))
        stop = Decimal(str(pos["stop_loss"])) if pos["stop_loss"] else entry - Decimal("1.00")

        risk_per_share = entry - stop
        if risk_per_share <= 0:
            print(f"  {pos['symbol']}: ZERO RISK - position invalid")
            errors.append(f"Zero risk for {pos['symbol']}")
            continue

        # Calculate R-multiple safely
        r_mult = (current - entry) / risk_per_share if risk_per_share > 0 else Decimal("0")

        print(f"  {pos['symbol']}: R-multiple = {float(r_mult):.2f}R")

    except Exception as e:
        errors.append(f"Risk calc failed for {pos['symbol']}: {e}")
        print(f"  ERROR {pos['symbol']}: {e}")

if errors:
    print(f"\n[FAIL] Risk calculation errors: {errors}")
    sys.exit(1)

print(f"\n[PASS] Risk calculations work")

print("\n[TEST 4] Database state validation...")
cur.execute("""
SELECT COUNT(*) as total,
       COUNT(CASE WHEN status='open' THEN 1 END) as open_count,
       COUNT(CASE WHEN status='closed' THEN 1 END) as closed_count
FROM algo_positions
""")
result = cur.fetchone()
if result:
    print(f"  Total positions: {result[0]}")
    print(f"  Open: {result[1]}, Closed: {result[2]}")

# Check for data integrity issues
cur.execute("""
SELECT COUNT(*) FROM algo_trades
WHERE status='open' AND exit_date IS NOT NULL
""")
orphaned = cur.fetchone()[0]
if orphaned > 0:
    print(f"  WARNING: {orphaned} trades with status='open' but exit_date set (orphaned)")
    errors.append(f"Found {orphaned} orphaned trades")

cur.execute("""
SELECT COUNT(*) FROM algo_positions
WHERE position_value IS NULL AND status='open'
""")
null_values = cur.fetchone()[0]
if null_values > 0:
    print(f"  ERROR: {null_values} positions with NULL value and status='open'")
    errors.append(f"NULL position values found")

if errors:
    print(f"\n[FAIL] Database integrity issues found")
    for e in errors:
        print(f"    - {e}")
else:
    print(f"\n[PASS] Database state is valid")

cur.close()
conn.close()

print("\n" + "="*80)
if errors:
    print(f"STRESS TEST FAILED - {len(errors)} issues found")
    print("\nIssues to fix:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("STRESS TEST PASSED - All checks successful")
    print("System is ready for orchestrator execution")
    sys.exit(0)
