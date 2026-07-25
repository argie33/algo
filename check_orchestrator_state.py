#!/usr/bin/env python3
"""Comprehensive orchestrator state analysis - find all issues."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
os.environ.setdefault("LOCAL_MODE", "true")
os.environ.setdefault("ENVIRONMENT", "development")

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

print("=" * 80)
print("ORCHESTRATOR STATE ANALYSIS")
print(f"Check Time: {datetime.now(EASTERN_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}")
print("=" * 80)

issues_found = []

# 1. Check recent orchestrator runs
print("\n[1/10] Recent Orchestrator Runs (last 24 hours)...")
try:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT run_id, run_date, overall_status, started_at, execution_time_seconds, halt_reason
            FROM algo_orchestrator_runs
            WHERE started_at > NOW() - INTERVAL '24 hours'
            ORDER BY started_at DESC
            LIMIT 10
        """)
        runs = cur.fetchall()
        if not runs:
            print("  WARNING: No orchestrator runs in last 24 hours")
            issues_found.append("No recent orchestrator runs")
        else:
            print(f"  Found {len(runs)} recent runs:")
            for run_id, run_date, status, started, duration, reason in runs:
                print(f"    {run_id}: {status:10s} started={started} duration={duration:.1f}s")
                if status not in ("ok", "success"):
                    if reason:
                        print(f"             reason: {reason[:60]}")
                    issues_found.append(f"Run {run_id} status={status}")
except Exception as e:
    issues_found.append(f"Cannot query orchestrator_runs: {e}")
    print(f"  ERROR: {e}")

# 2. Check for stale data loaders
print("\n[2/10] Data Loader Status...")
try:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT table_name, last_updated, status, completion_pct
            FROM data_loader_status
            WHERE table_name IN ('price_daily', 'technical_data_daily', 'buy_sell_daily', 'market_health_daily')
            ORDER BY last_updated DESC
        """)
        loaders = cur.fetchall()
        now_utc = datetime.now(timezone.utc)

        for table_name, last_updated, status, completion in loaders:
            age_hours = (now_utc - last_updated).total_seconds() / 3600 if last_updated else None
            if age_hours and age_hours > 24:
                issues_found.append(f"Stale loader: {table_name} ({age_hours:.1f}h old)")
            print(f"    {table_name:25s} age={age_hours:.1f}h status={status:8s} completion={completion:.1f}%")
except Exception as e:
    issues_found.append(f"Cannot query loader_status: {e}")
    print(f"  ERROR: {e}")

# 3. Check for halt flag status
print("\n[3/10] Halt Flag Status...")
try:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT halt_reason, set_at, expires_at, cleared_at
            FROM halt_flag_state
            ORDER BY set_at DESC
            LIMIT 5
        """)
        flags = cur.fetchall()
        if not flags:
            print("  OK: No halt flags found")
        else:
            print(f"  Found {len(flags)} recent halt flags:")
            for reason, set_at, expires_at, cleared_at in flags:
                status = "ACTIVE" if not cleared_at else "CLEARED"
                print(f"    {status}: {reason[:50]}")
                if not cleared_at:
                    issues_found.append(f"Active halt flag: {reason[:50]}")
except Exception as e:
    print(f"  Note: Halt flag query failed (may not exist): {e}")

# 4. Check for Phase 1 degraded mode
print("\n[4/10] Phase 1 Data Freshness...")
try:
    with DatabaseContext("read") as cur:
        # Get latest Phase 1 results from execution logs
        cur.execute("""
            SELECT run_id, action_date, details, status
            FROM algo_audit_log
            WHERE action_type LIKE 'phase_1%'
            ORDER BY action_date DESC
            LIMIT 5
        """)
        phase1_logs = cur.fetchall()
        if phase1_logs:
            for run_id, action_date, details, status in phase1_logs:
                print(f"    Phase 1 {status:10s} at {action_date}")
                if status not in ("ok", "success"):
                    issues_found.append(f"Phase 1 {status}: {details[:60] if details else 'no details'}")
        else:
            print("  No Phase 1 logs found")
except Exception as e:
    print(f"  Error checking Phase 1: {e}")

# 5. Check for open positions state
print("\n[5/10] Portfolio State...")
try:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
        open_count = cur.fetchone()[0]

        cur.execute("SELECT SUM(current_value) FROM algo_positions WHERE status = 'open'")
        total_value = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status = 'open'")
        open_trades = cur.fetchone()[0]

        print(f"    Open Positions: {open_count}")
        print(f"    Open Trades: {open_trades}")
        print(f"    Total Value: ${total_value:,.2f}" if total_value else "    Total Value: N/A")
except Exception as e:
    issues_found.append(f"Cannot query portfolio state: {e}")
    print(f"  ERROR: {e}")

# 6. Check for signal quality consistency
print("\n[6/10] Signal Quality Checks...")
try:
    with DatabaseContext("read") as cur:
        # Check signals with NULL quality scores
        cur.execute("""
            SELECT COUNT(*), COUNT(signal_quality_score)
            FROM buy_sell_daily
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            AND signal IN ('BUY', 'SELL')
        """)
        total, with_score = cur.fetchone()
        if total and with_score < total * 0.90:
            issues_found.append(f"Low signal quality population: {with_score}/{total} ({with_score/total*100:.1f}%)")
            print(f"  WARNING: Only {with_score}/{total} signals have quality scores ({with_score/total*100:.1f}%)")
        else:
            print(f"  OK: {with_score}/{total} signals have quality scores" if total else "  OK: No recent signals")
except Exception as e:
    print(f"  Error checking signal quality: {e}")

# 7. Check for execution logs completeness
print("\n[7/10] Execution Log Coverage...")
try:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT COUNT(DISTINCT run_id) FROM orchestrator_execution_log
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)
        logged_runs = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(DISTINCT run_id) FROM algo_orchestrator_runs
            WHERE started_at > NOW() - INTERVAL '24 hours'
        """)
        total_runs = cur.fetchone()[0]

        print(f"    Execution logs: {logged_runs}/{total_runs} runs")
        if logged_runs < total_runs:
            issues_found.append(f"Missing execution logs: {total_runs - logged_runs} runs not logged")
except Exception as e:
    print(f"  Error checking execution logs: {e}")

# 8. Check for orphaned trades/positions
print("\n[8/10] Data Integrity Checks...")
try:
    with DatabaseContext("read") as cur:
        # Orphaned positions
        cur.execute("""
            SELECT COUNT(*) FROM algo_positions p
            WHERE NOT EXISTS (
                SELECT 1 FROM algo_trades t
                WHERE t.trade_id = ANY(p.trade_ids_arr) OR p.trade_ids_arr IS NULL
            )
        """)
        orphaned_positions = cur.fetchone()[0]
        if orphaned_positions > 0:
            issues_found.append(f"Found {orphaned_positions} orphaned positions")
            print(f"  WARNING: {orphaned_positions} orphaned positions found")
        else:
            print("  OK: No orphaned positions")

        # Inconsistent trade states
        cur.execute("""
            SELECT COUNT(*) FROM algo_trades
            WHERE status = 'open' AND exit_date IS NOT NULL
        """)
        inconsistent = cur.fetchone()[0]
        if inconsistent > 0:
            issues_found.append(f"Found {inconsistent} open trades with exit_date")
            print(f"  WARNING: {inconsistent} open trades with exit_date set")
        else:
            print("  OK: Trade state consistent")
except Exception as e:
    print(f"  Error checking data integrity: {e}")

# 9. Check configuration consistency
print("\n[9/10] Configuration Consistency...")
try:
    from algo.infrastructure.config.main import AlgoConfig
    config = AlgoConfig()

    critical_keys = [
        "min_win_rate_pct",
        "max_daily_loss_pct",
        "max_weekly_loss_pct",
        "min_signal_quality_score",
        "max_total_risk_pct",
    ]

    missing = []
    for key in critical_keys:
        try:
            val = config.get(key)
            if val is None:
                missing.append(key)
        except KeyError:
            missing.append(key)

    if missing:
        issues_found.append(f"Missing config keys: {missing}")
        print(f"  WARNING: Missing config keys: {missing}")
    else:
        print("  OK: All critical config keys present")
except Exception as e:
    issues_found.append(f"Cannot validate config: {e}")
    print(f"  ERROR: {e}")

# 10. Check for loading/parsing errors in loaders
print("\n[10/10] Recent Loader Errors...")
try:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT action_type, COUNT(*), MAX(action_date)
            FROM algo_audit_log
            WHERE action_type LIKE 'loader_%'
            AND status IN ('error', 'fail', 'halted')
            AND action_date > NOW() - INTERVAL '24 hours'
            GROUP BY action_type
            ORDER BY MAX(action_date) DESC
        """)
        errors = cur.fetchall()
        if errors:
            print(f"  Found {len(errors)} error loaders:")
            for action_type, count, latest in errors:
                print(f"    {action_type}: {count} errors (latest: {latest})")
                issues_found.append(f"Loader errors: {action_type}")
        else:
            print("  OK: No recent loader errors")
except Exception as e:
    print(f"  Note: Could not check loader errors: {e}")

# Summary
print("\n" + "=" * 80)
print(f"SUMMARY: Found {len(issues_found)} issue(s)")
print("=" * 80)
if issues_found:
    print("\nISSUES TO FIX:")
    for i, issue in enumerate(issues_found, 1):
        print(f"  {i}. {issue}")
else:
    print("\n✓ All checks passed - orchestrator appears healthy!")

sys.exit(0 if not issues_found else 1)
