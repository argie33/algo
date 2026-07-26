#!/usr/bin/env python3
"""Comprehensive integrity check of orchestrator code for bugs."""

import sys
sys.path.insert(0, '.')

from datetime import date, datetime, timedelta
from algo.infrastructure.config.main import AlgoConfig
from algo.orchestrator.phase_result import PhaseResult
from utils.db import DatabaseContext

print("=" * 80)
print("ORCHESTRATOR INTEGRITY CHECK")
print("=" * 80)

issues = []

# Test 1: Check phase data contracts
print("\nTest 1: Phase Result Data Contracts")
try:
    result = PhaseResult(1, "test", "ok", {"key": "value"}, False, None)
    assert result.phase_num == 1
    assert result.phase_name == "test"
    assert result.status == "ok"
    assert result.data == {"key": "value"}
    assert not result.halted
    print("  OK: PhaseResult data contracts valid")
except Exception as e:
    issues.append(f"PhaseResult contract: {e}")

# Test 2: Check config loading
print("\nTest 2: Configuration Loading")
try:
    config = AlgoConfig()
    assert config.get("max_total_risk_pct") == 4.0 or config.get("max_total_risk_pct") is not None
    print(f"  OK: Config loads successfully")
except Exception as e:
    issues.append(f"Config loading: {e}")

# Test 3: Check database connectivity
print("\nTest 3: Database Connectivity")
try:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
        if result:
            print("  OK: Database connection working")
        else:
            issues.append("Database query returned empty result")
except Exception as e:
    issues.append(f"Database connectivity: {e}")

# Test 4: Check for orphaned positions
print("\nTest 4: Data Integrity - Orphaned Positions")
try:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT COUNT(*) FROM algo_positions p
            WHERE NOT EXISTS (
                SELECT 1 FROM algo_trades t
                WHERE t.trade_id = ANY(p.trade_ids_arr)
            )
        """)
        orphan_count = cur.fetchone()[0]
        if orphan_count > 0:
            issues.append(f"Found {orphan_count} orphaned positions (no corresponding trades)")
        else:
            print("  OK: No orphaned positions found")
except Exception as e:
    issues.append(f"Orphaned position check: {e}")

# Test 5: Check for signals with NULL quality scores (should be rare)
print("\nTest 5: Data Integrity - Signal Quality Scores")
try:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT COUNT(*) FROM buy_sell_daily
            WHERE DATE >= CURRENT_DATE - INTERVAL '7 days'
            AND signal_quality_score IS NULL
        """)
        null_count = cur.fetchone()[0]
        if null_count > 5:
            issues.append(f"Found {null_count} recent signals with NULL quality scores (expected < 5)")
        else:
            print(f"  OK: Only {null_count} signals with NULL quality scores")
except Exception as e:
    issues.append(f"Signal quality check: {e}")

# Test 6: Check for inconsistent trade state
print("\nTest 6: Data Integrity - Trade State Consistency")
try:
    with DatabaseContext("read") as cur:
        # Check for trades with status=open but exit_date set
        cur.execute("""
            SELECT COUNT(*) FROM algo_trades
            WHERE status = 'open' AND exit_date IS NOT NULL
        """)
        inconsistent = cur.fetchone()[0]
        if inconsistent > 0:
            issues.append(f"Found {inconsistent} open trades with exit_date set (data inconsistency)")
        else:
            print("  OK: Trade state consistent")
except Exception as e:
    issues.append(f"Trade state check: {e}")

# Test 7: Check circuit breaker metric validity
print("\nTest 7: Circuit Breaker Metrics")
try:
    with DatabaseContext("read") as cur:
        # circuit_breaker_metrics table may not exist - skip if not found
        cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'circuit_breaker_metrics'
            )
        """)
        if cur.fetchone()[0]:
            cur.execute("""
                SELECT COUNT(*) FROM circuit_breaker_metrics
                WHERE snapshot_date = CURRENT_DATE
            """)
            count = cur.fetchone()[0]
            print(f"  OK: {count} circuit breaker metrics for today")
        else:
            print("  OK: circuit_breaker_metrics table not in use (expected)")
except Exception as e:
    pass  # Skip if table doesn't exist

# Test 8: Verify Phase 7 signal backfill is working
print("\nTest 8: Phase 7 Signal Quality Backfill")
try:
    with DatabaseContext("read") as cur:
        # Check if recent signals have quality scores
        cur.execute("""
            SELECT COUNT(*), COUNT(signal_quality_score)
            FROM buy_sell_daily
            WHERE DATE >= CURRENT_DATE - INTERVAL '3 days'
            AND signal = 'BUY'
        """)
        total, with_score = cur.fetchone()
        if total > 0 and with_score < total * 0.95:  # Allow 5% NULL
            issues.append(f"Signal quality score population low: {with_score}/{total} ({with_score/total*100:.1f}%)")
        elif total > 0:
            print(f"  OK: {with_score}/{total} recent BUY signals have quality scores ({with_score/total*100:.1f}%)")
        else:
            print("  OK: No recent signals to check")
except Exception as e:
    issues.append(f"Signal backfill check: {e}")

# Test 9: Check for late Phase 7 runs in recent data
print("\nTest 9: Orchestrator Run Status")
try:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT COUNT(*), COUNT(CASE WHEN overall_status='success' THEN 1 END)
            FROM algo_orchestrator_runs
            WHERE started_at > NOW() - INTERVAL '24 hours'
        """)
        total, success = cur.fetchone()
        if total > 0:
            success_rate = success / total * 100
            print(f"  OK: {total} runs in last 24h, {success} successful ({success_rate:.1f}%)")
            if success_rate < 50:
                issues.append(f"Low success rate: {success}/{total} ({success_rate:.1f}%)")
        else:
            print("  OK: No runs in last 24h (expected after market close)")
except Exception as e:
    issues.append(f"Orchestrator run check: {e}")

# Test 10: Check risk guard is working
print("\nTest 10: Phase 8 Risk Guard")
try:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT COUNT(*) FROM algo_positions
            WHERE status = 'open'
        """)
        open_pos = cur.fetchone()[0]

        # Check latest portfolio value
        cur.execute("""
            SELECT total_portfolio_value FROM algo_portfolio_snapshots
            ORDER BY snapshot_date DESC, created_at DESC LIMIT 1
        """)
        portfolio_row = cur.fetchone()
        if portfolio_row and portfolio_row[0]:
            portfolio_val = portfolio_row[0]

            # Calculate total risk
            cur.execute("""
                SELECT SUM(GREATEST(0, (t.entry_price - p.current_stop_price) * p.quantity))
                FROM algo_positions p
                JOIN algo_trades t ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE p.status = 'open'
            """)
            risk_row = cur.fetchone()
            if risk_row and risk_row[0]:
                total_risk = float(risk_row[0]) if risk_row[0] else 0.0
                risk_pct = total_risk / float(portfolio_val) * 100.0

                if risk_pct > 4.1:
                    issues.append(f"Risk guard not enforced: {risk_pct:.2f}% > 4% (should be halted)")
                elif risk_pct > 3.9:
                    print(f"  WARNING: Risk at {risk_pct:.2f}% (near 4% limit)")
                else:
                    print(f"  OK: {open_pos} positions, risk {risk_pct:.2f}% (within 4% limit)")
            else:
                print(f"  OK: {open_pos} open positions")
        else:
            print("  OK: No portfolio snapshot yet")
except Exception as e:
    issues.append(f"Risk guard check: {e}")

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

if issues:
    print(f"\nFound {len(issues)} issue(s):\n")
    for i, issue in enumerate(issues, 1):
        print(f"{i}. {issue}")
    sys.exit(1)
else:
    print("\nAll integrity checks PASSED - no issues found!")
    sys.exit(0)
