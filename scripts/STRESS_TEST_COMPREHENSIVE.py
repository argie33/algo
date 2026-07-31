#!/usr/bin/env python3
"""
Comprehensive stress test to find bugs before production deployment.
Tests all edge cases and error paths.
"""

import psycopg2
import os
import sys
from datetime import datetime, date
from decimal import Decimal

def get_db():
    """Connect to database."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "trading_algo"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "")
    )

def test_position_integrity():
    """Test 1: Position data integrity."""
    print("\n=== TEST 1: POSITION INTEGRITY ===")
    conn = get_db()
    cur = conn.cursor()

    issues = []

    # Check all required fields non-NULL
    cur.execute("""
    SELECT COUNT(*) FROM algo_positions
    WHERE status = 'open'
      AND (entry_price IS NULL OR current_price IS NULL OR
           quantity IS NULL OR stop_loss_price IS NULL)
    """)
    if cur.fetchone()[0] > 0:
        issues.append("FAIL: Positions with NULL required fields")

    # Check logical constraints
    cur.execute("""
    SELECT symbol, entry_price, stop_loss_price
    FROM algo_positions
    WHERE status = 'open' AND stop_loss_price >= entry_price
    """)
    bad = cur.fetchall()
    if bad:
        issues.append(f"FAIL: {len(bad)} positions with stop >= entry")
        for symbol, entry, stop in bad[:3]:
            print(f"  {symbol}: entry={entry}, stop={stop}")

    # Check quantity > 0
    cur.execute("""
    SELECT COUNT(*) FROM algo_positions
    WHERE status = 'open' AND quantity <= 0
    """)
    if cur.fetchone()[0] > 0:
        issues.append("FAIL: Positions with quantity <= 0")

    # Check position value calculation
    cur.execute("""
    SELECT symbol, quantity * current_price as calc_value, position_value
    FROM algo_positions
    WHERE status = 'open'
      AND ABS((quantity * current_price) - position_value) > 0.01
    """)
    if cur.rowcount > 0:
        issues.append(f"FAIL: {cur.rowcount} positions with mismatched value calc")

    conn.close()

    if not issues:
        print("PASS: All position data integrity checks pass")
    else:
        for issue in issues:
            print(issue)
    return len(issues) == 0

def test_trade_position_consistency():
    """Test 2: Trade-Position consistency."""
    print("\n=== TEST 2: TRADE-POSITION CONSISTENCY ===")
    conn = get_db()
    cur = conn.cursor()

    issues = []

    # Check for trades without positions
    cur.execute("""
    SELECT COUNT(*) FROM algo_trades t
    LEFT JOIN algo_positions p ON t.position_id = p.position_id
    WHERE t.status IN ('open', 'filled', 'partially_filled')
      AND p.position_id IS NULL
    """)
    orphaned = cur.fetchone()[0]
    if orphaned > 0:
        issues.append(f"FAIL: {orphaned} active trades without positions")

    # Check position trade_ids_arr matches actual trades
    cur.execute("""
    SELECT p.symbol, array_length(p.trade_ids_arr, 1) as arr_len, COUNT(t.trade_id) as actual_count
    FROM algo_positions p
    LEFT JOIN algo_trades t ON p.position_id = t.position_id AND t.status IN ('open', 'filled')
    WHERE p.status = 'open'
    GROUP BY p.symbol, p.position_id, array_length(p.trade_ids_arr, 1)
    HAVING (array_length(p.trade_ids_arr, 1) IS NOT NULL AND
            array_length(p.trade_ids_arr, 1) != COUNT(t.trade_id))
       OR (array_length(p.trade_ids_arr, 1) IS NULL AND COUNT(t.trade_id) > 0)
    """)
    mismatches = cur.fetchall()
    if mismatches:
        issues.append(f"FAIL: {len(mismatches)} positions with trade_ids_arr mismatch")

    conn.close()

    if not issues:
        print("PASS: All trade-position consistency checks pass")
    else:
        for issue in issues:
            print(issue)
    return len(issues) == 0

def test_circuit_breaker_state():
    """Test 3: Circuit breaker state integrity."""
    print("\n=== TEST 3: CIRCUIT BREAKER STATE ===")
    conn = get_db()
    cur = conn.cursor()

    issues = []

    # Check halt flag
    cur.execute("""
    SELECT halt_flag, halt_reason FROM algo_runtime_state
    WHERE state_key = 'orchestrator_halt'
    """)
    row = cur.fetchone()
    if row and row[0]:
        print(f"WARN: Halt is active: {row[1]}")
        # This is not necessarily a fail, but worth noting

    # Check for stale halt (older than 24 hours)
    cur.execute("""
    SELECT halt_triggered_at FROM algo_runtime_state
    WHERE state_key = 'orchestrator_halt'
      AND halt_flag = true
      AND halt_triggered_at < now() - interval '24 hours'
    """)
    stale = cur.fetchone()
    if stale:
        issues.append("FAIL: Halt flag stuck for >24 hours")

    conn.close()

    if not issues:
        print("PASS: Circuit breaker state OK")
    else:
        for issue in issues:
            print(issue)
    return len(issues) == 0

def test_config_validity():
    """Test 4: Configuration validity."""
    print("\n=== TEST 4: CONFIGURATION VALIDITY ===")
    conn = get_db()
    cur = conn.cursor()

    issues = []

    # Check critical config keys exist
    required_keys = [
        'execution_mode', 'max_positions', 'base_risk_pct', 'alpaca_paper_trading',
        'max_position_size_pct', 'min_signal_quality_score', 'halt_drawdown_pct'
    ]

    cur.execute("SELECT key FROM algo_config WHERE key = ANY(%s)", (required_keys,))
    found_keys = {row[0] for row in cur.fetchall()}
    missing = set(required_keys) - found_keys
    if missing:
        issues.append(f"FAIL: Missing config keys: {missing}")

    # Check config value ranges
    cur.execute("""
    SELECT key, value FROM algo_config
    WHERE key IN ('base_risk_pct', 'max_positions', 'vix_max_threshold')
    """)

    for key, value in cur.fetchall():
        try:
            val = float(value) if value != 'true' and value != 'false' else value
            if key == 'base_risk_pct' and (val < 0.01 or val > 5):
                issues.append(f"FAIL: {key} out of range: {val}")
            elif key == 'max_positions' and (val < 5 or val > 100):
                issues.append(f"FAIL: {key} out of range: {val}")
        except ValueError:
            issues.append(f"FAIL: {key} has non-numeric value: {value}")

    conn.close()

    if not issues:
        print("PASS: Configuration is valid")
    else:
        for issue in issues:
            print(issue)
    return len(issues) == 0

def test_data_freshness():
    """Test 5: Data freshness checks."""
    print("\n=== TEST 5: DATA FRESHNESS ===")
    conn = get_db()
    cur = conn.cursor()

    issues = []

    # Check price data
    cur.execute("SELECT MAX(date) FROM price_daily")
    latest_price = cur.fetchone()[0]
    if latest_price and (date.today() - latest_price).days > 1:
        issues.append(f"WARN: Price data stale ({latest_price})")

    # Check signal data
    cur.execute("SELECT MAX(created_at) FROM signal_quality_scores")
    latest_signal = cur.fetchone()[0]
    if latest_signal and (datetime.now() - latest_signal).days > 1:
        issues.append(f"WARN: Signal data stale ({latest_signal})")

    conn.close()

    if not issues:
        print("PASS: Data freshness OK")
    else:
        for issue in issues:
            print(issue)
    return len(issues) == 0

def main():
    """Run all tests."""
    print("="*60)
    print("COMPREHENSIVE STRESS TEST")
    print("="*60)

    tests = [
        ("Position Integrity", test_position_integrity),
        ("Trade-Position Consistency", test_trade_position_consistency),
        ("Circuit Breaker State", test_circuit_breaker_state),
        ("Configuration Validity", test_config_validity),
        ("Data Freshness", test_data_freshness),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"ERROR in {name}: {e}")
            results.append((name, False))

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{status}: {name}")

    failed_count = sum(1 for _, passed in results if not passed)
    if failed_count == 0:
        print("\nAll tests passed! System ready for production.")
        return 0
    else:
        print(f"\n{failed_count} test(s) failed. Review issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
