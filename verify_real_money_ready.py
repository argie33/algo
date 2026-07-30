#!/usr/bin/env python
"""Comprehensive verification that system is ready for real-money trading."""

import json
from utils.db.context import DatabaseContext
from datetime import datetime, timedelta

def check_data_integrity():
    """Check for data corruption or NULL values in critical fields."""
    with DatabaseContext(role='read') as db:
        issues = []

        # Check positions
        null_count = db.execute('''
            SELECT COUNT(*) FROM algo_positions
            WHERE entry_price IS NULL OR quantity IS NULL OR current_price IS NULL
        ''').fetchone()[0]
        if null_count > 0:
            issues.append(f"Positions with NULL critical fields: {null_count}")

        # Check trades
        orphan_count = db.execute('''
            SELECT COUNT(*) FROM algo_trades t
            WHERE NOT EXISTS (SELECT 1 FROM algo_positions p WHERE p.id::text = t.position_id)
        ''').fetchone()[0]
        if orphan_count > 0:
            issues.append(f"Orphaned trades: {orphan_count}")

        return len(issues) == 0, issues

def check_orchestrator_health():
    """Check recent orchestrator runs for consistency."""
    with DatabaseContext(role='read') as db:
        # Count runs by status in last 7 days
        rows = db.execute('''
            SELECT overall_status, COUNT(*) FROM orchestrator_execution_log
            WHERE run_date >= CURRENT_DATE - interval '7 days'
            GROUP BY overall_status
        ''').fetchall()

        status_counts = dict(rows)
        halted_count = status_counts.get('halted', 0)
        error_count = len([r for r in rows if r[0] not in ['ok', 'success', 'degraded', 'skipped']])

        issues = []
        if halted_count > 2:  # Allow 1-2 old halts, but more than that is concerning
            issues.append(f"Recent halted runs: {halted_count}")

        return halted_count <= 2 and error_count == 0, issues

def check_phase_execution():
    """Check recent phase execution (last 6 hours) for critical phases."""
    with DatabaseContext(role='read') as db:
        rows = db.execute('''
            SELECT run_id, phase_results
            FROM orchestrator_execution_log
            WHERE started_at > now() - interval '6 hours'
            ORDER BY started_at DESC
            LIMIT 20;
        ''').fetchall()

        issues = []
        phase_stats = {'3': {'ok': 0, 'error': 0}, '6': {'ok': 0, 'error': 0}, '7': {'ok': 0, 'error': 0}}

        for run_id, phase_results_raw in rows:
            if isinstance(phase_results_raw, list):
                for phase_data in phase_results_raw:
                    phase_num = phase_data.get('phase')
                    status = phase_data.get('status')

                    if phase_num in ['3', '6', '7']:
                        if status == 'error':
                            phase_stats[phase_num]['error'] += 1
                            if phase_num in ['3', '6']:  # Critical phases
                                summary = phase_data.get('summary', '')[:80]
                                issues.append(f"Phase {phase_num} ERROR: {summary}")
                        elif status in ['ok', 'success']:
                            phase_stats[phase_num]['ok'] += 1

        # Check error rates
        for phase_num in ['3', '6']:
            total = phase_stats[phase_num]['ok'] + phase_stats[phase_num]['error']
            if total > 0 and phase_stats[phase_num]['error'] > 0:
                error_pct = 100 * phase_stats[phase_num]['error'] / total
                if error_pct > 10:
                    issues.append(f"Phase {phase_num} error rate: {error_pct:.0f}%")

        return len(issues) == 0, issues, phase_stats

def check_position_monitoring():
    """Check if positions are properly monitored and tracked."""
    with DatabaseContext(role='read') as db:
        # Check total open positions
        open_count = db.execute('''
            SELECT COUNT(*) FROM algo_positions WHERE status = 'open'
        ''').fetchone()[0]

        # Check for positions without stop losses or entry prices
        bad_stops = db.execute('''
            SELECT COUNT(*) FROM algo_positions
            WHERE status = 'open' AND (stop_loss_price IS NULL OR stop_loss_price <= 0)
        ''').fetchone()[0]

        bad_entries = db.execute('''
            SELECT COUNT(*) FROM algo_positions
            WHERE status = 'open' AND (entry_price IS NULL OR entry_price <= 0)
        ''').fetchone()[0]

        issues = []
        if bad_stops > 0:
            issues.append(f"Open positions without valid stop losses: {bad_stops}")
        if bad_entries > 0:
            issues.append(f"Open positions without valid entry prices: {bad_entries}")

        return len(issues) == 0, issues, open_count

def main():
    print("=" * 160)
    print("REAL-MONEY TRADING READINESS VERIFICATION")
    print("=" * 160)

    checks = []

    # Data Integrity
    print("\n1. DATA INTEGRITY CHECK")
    print("-" * 160)
    integrity_ok, integrity_issues = check_data_integrity()
    if integrity_ok:
        print("   [PASS] No data corruption detected")
    else:
        print("   [FAIL] Data integrity issues found:")
        for issue in integrity_issues:
            print(f"      - {issue}")
    checks.append(("Data Integrity", integrity_ok))

    # Orchestrator Health
    print("\n2. ORCHESTRATOR HEALTH CHECK (last 7 days)")
    print("-" * 160)
    orch_ok, orch_issues = check_orchestrator_health()
    if orch_ok:
        print("   [PASS] Orchestrator runs are healthy")
    else:
        print("   [FAIL] Orchestrator health issues:")
        for issue in orch_issues:
            print(f"      - {issue}")
    checks.append(("Orchestrator Health", orch_ok))

    # Phase Execution
    print("\n3. PHASE EXECUTION CHECK (last 6 hours)")
    print("-" * 160)
    phase_ok, phase_issues, phase_stats = check_phase_execution()
    if phase_ok:
        print("   [PASS] Phase execution healthy")
        print(f"      Phase 3 (Monitor): {phase_stats['3']['ok']} ok, {phase_stats['3']['error']} errors")
        print(f"      Phase 6 (Exit):    {phase_stats['6']['ok']} ok, {phase_stats['6']['error']} errors")
        print(f"      Phase 7 (Signal):  {phase_stats['7']['ok']} ok, {phase_stats['7']['error']} errors")
    else:
        print("   [FAIL] Phase execution issues:")
        for issue in phase_issues:
            print(f"      - {issue}")
    checks.append(("Phase Execution", phase_ok))

    # Position Monitoring
    print("\n4. POSITION MONITORING CHECK")
    print("-" * 160)
    monitor_ok, monitor_issues, open_count = check_position_monitoring()
    print(f"   Open positions: {open_count}")
    if monitor_ok:
        print("   [PASS] Position monitoring is healthy")
    else:
        print("   [FAIL] Position monitoring issues:")
        for issue in monitor_issues:
            print(f"      - {issue}")
    checks.append(("Position Monitoring", monitor_ok))

    # Final Summary
    print("\n" + "=" * 160)
    print("FINAL VERDICT")
    print("=" * 160)

    pass_count = sum(1 for _, ok in checks if ok)
    total_count = len(checks)

    for check_name, ok in checks:
        status = "[PASS]" if ok else "[FAIL]"
        print(f"{status} {check_name}")

    print()
    if pass_count == total_count:
        print(f"[PASS] SYSTEM READY FOR REAL-MONEY TRADING ({pass_count}/{total_count} checks passed)")
    else:
        print(f"[FAIL] SYSTEM NOT READY ({pass_count}/{total_count} checks passed)")
        print("   Address failing checks before enabling real-money trading")

if __name__ == '__main__':
    main()
