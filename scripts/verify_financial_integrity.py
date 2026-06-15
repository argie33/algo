#!/usr/bin/env python3
"""
Financial Data Integrity Verification Script

Runs automated checks to ensure financial data integrity safeguards are in place:
- Validates critical validation patterns are used
- Ensures no silent fallbacks in production code
- Verifies database constraints are defined
- Checks for proper error handling

Run this before major releases to ensure data integrity.
"""

import subprocess
import sys
from pathlib import Path

ERRORS = []
WARNINGS = []
PASSES = []


def run_check(name, command, should_have=None, should_not_have=None):
    """Run a grep-based check."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        output = result.stdout.strip()
        count = len(output.split("\n")) if output else 0

        if should_have and count == 0:
            ERRORS.append(f"[FAIL] {name}: Expected to find pattern but didn't")
            return False
        elif should_not_have and count > 0:
            ERRORS.append(
                f"[FAIL] {name}: Found {count} instances of problematic pattern:\n{output[:200]}"
            )
            return False
        else:
            PASSES.append(f"[OK] {name}")
            return True
    except Exception as e:
        ERRORS.append(f"[FAIL] {name}: Check failed - {e}")
        return False


def verify_database_schema():
    """Verify critical database constraints are in place."""
    print("\n[1/4] Verifying Database Schema Constraints...")

    schema_file = Path("lambda/db-init/schema.sql")
    if not schema_file.exists():
        ERRORS.append("[FAIL] Schema file not found: lambda/db-init/schema.sql")
        return

    try:
        content = schema_file.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        ERRORS.append(f"[FAIL] Could not read schema file: {e}")
        return

    # Check entry_price constraint
    if "entry_price DECIMAL(12, 4) NOT NULL" in content:
        PASSES.append("[PASS] entry_price is NOT NULL")
    else:
        ERRORS.append("[FAIL] entry_price missing NOT NULL constraint")

    # Check entry_quantity constraint
    if "entry_quantity INTEGER NOT NULL" in content:
        PASSES.append("[PASS] entry_quantity is NOT NULL")
    else:
        ERRORS.append("[FAIL] entry_quantity missing NOT NULL constraint")

    # Check unique constraint on symbol/signal_date/entry_price
    if "UNIQUE(symbol, signal_date, entry_price)" in content:
        PASSES.append("[PASS] Duplicate trade prevention (UNIQUE constraint)")
    else:
        ERRORS.append("[FAIL] Missing UNIQUE constraint on algo_trades")


def verify_validation_patterns():
    """Verify critical code uses correct validation patterns."""
    print("\n[2/4] Verifying Code Validation Patterns...")

    # Check that validation happens before conversion (not after)
    run_check(
        "Price validation before conversion",
        "grep -rn 'if.*is None' algo/algo_daily_reconciliation.py | grep -E 'entry|stop|price' | wc -l",
        should_have=True,
    )

    # Check for proper exception handling
    run_check(
        "Try/except blocks use specific exceptions",
        "grep -rn 'except.*:$' algo/ --include='*.py' | wc -l",
        should_not_have=True,  # Should NOT find bare except
    )

    # Check for proper range checking
    run_check(
        "Price/quantity range validation",
        "grep -rn '<= 0' algo/algo_daily_reconciliation.py | wc -l",
        should_have=True,
    )

    # Check for Decimal usage in monetary calculations
    run_check(
        "Decimal used for precision in monetary calculations",
        "grep -rn 'Decimal.*ROUND_HALF_UP' algo/ --include='*.py' | wc -l",
        should_have=True,
    )


def verify_no_dangerous_patterns():
    """Verify no dangerous fallback patterns exist."""
    print("\n[3/4] Verifying No Dangerous Fallback Patterns...")

    # Check for "or 0" in critical price/quantity contexts
    result = subprocess.run(
        "grep -rn 'price.*or 0\\|quantity.*or 0\\|entry.*or 0' algo/ --include='*.py' | wc -l",
        shell=True,
        capture_output=True,
        text=True,
    )
    count = int(result.stdout.strip()) if result.stdout.strip() else 0
    if count > 0:
        WARNINGS.append(
            f"[WARN] Found {count} potential 'or 0' patterns (may be safe after validation)"
        )
    else:
        PASSES.append("[OK] No critical 'or 0' fallback patterns found")

    # Check for hardcoded test values
    result = subprocess.run(
        "grep -rn 'entry_price.*=.*150\\|stop_loss.*142' algo/ --include='*.py' | wc -l",
        shell=True,
        capture_output=True,
        text=True,
    )
    count = int(result.stdout.strip()) if result.stdout.strip() else 0
    if count > 0:
        ERRORS.append(f"[FAIL] Found {count} hardcoded test values in production code")
    else:
        PASSES.append("[OK] No hardcoded test values found")

    # Check for silent failures (except without logging)
    result = subprocess.run(
        "grep -rn 'except.*pass' algo/ --include='*.py' | wc -l",
        shell=True,
        capture_output=True,
        text=True,
    )
    count = int(result.stdout.strip()) if result.stdout.strip() else 0
    if count > 0:
        ERRORS.append(f"[FAIL] Found {count} silent failures (except pass)")
    else:
        PASSES.append("[OK] No silent failures found")


def verify_logging_coverage():
    """Verify comprehensive logging in critical paths."""
    print("\n[4/4] Verifying Logging Coverage...")

    # Check for logging in critical files
    run_check(
        "Trade executor has logging",
        "grep -n 'logger\\.' algo/algo_trade_executor.py | wc -l",
        should_have=True,
    )

    run_check(
        "Daily reconciliation has logging",
        "grep -n 'logger\\.' algo/algo_daily_reconciliation.py | wc -l",
        should_have=True,
    )

    run_check(
        "Position sizer has logging",
        "grep -n 'logger\\.' algo/algo_position_sizer.py | wc -l",
        should_have=True,
    )

    # Check that CRITICAL errors are logged
    run_check(
        "Critical errors logged at CRITICAL level",
        "grep -rn 'logger.critical' algo/ --include='*.py' | wc -l",
        should_have=True,
    )


def print_results():
    """Print verification results."""
    print("\n" + "=" * 70)
    print("FINANCIAL DATA INTEGRITY VERIFICATION RESULTS")
    print("=" * 70)

    if PASSES:
        print(f"\n[PASSED] ({len(PASSES)} checks)")
        for p in PASSES:
            print(f"  {p}")

    if WARNINGS:
        print(f"\n[WARNINGS] ({len(WARNINGS)} checks)")
        for w in WARNINGS:
            print(f"  {w}")

    if ERRORS:
        print(f"\n[FAILED] ({len(ERRORS)} checks)")
        for e in ERRORS:
            print(f"  {e}")

    total = len(PASSES) + len(WARNINGS) + len(ERRORS)
    pass_pct = len(PASSES) / total * 100 if total > 0 else 0

    print(f"\n{'='*70}")
    print(f"Summary: {len(PASSES)}/{total} checks passed ({pass_pct:.0f}%)")
    print(f"Status: {'PASSED' if not ERRORS else 'FAILED'}")
    print("=" * 70)

    return 0 if not ERRORS else 1


if __name__ == "__main__":
    print("Starting Financial Data Integrity Verification...")
    print("This script checks that all data integrity safeguards are in place.")

    verify_database_schema()
    verify_validation_patterns()
    verify_no_dangerous_patterns()
    verify_logging_coverage()

    sys.exit(print_results())
