#!/usr/bin/env python3
"""Analyze recent orchestrator runs to find patterns and issues."""

from utils.db import DatabaseContext
from datetime import datetime, timedelta

print("=" * 90)
print("ANALYZING RECENT ORCHESTRATOR RUNS FOR ISSUES")
print("=" * 90)

# Get recent runs
try:
    with DatabaseContext('read') as cur:
        cur.execute('''
            SELECT run_id, overall_status, started_at, ended_at, is_dry_run
            FROM orchestrator_execution_log
            WHERE started_at > NOW() - INTERVAL '7 days'
            ORDER BY started_at DESC
            LIMIT 20
        ''')
        runs = cur.fetchall()
        print(f"\nRecent Runs (last 7 days): {len(runs)}")

        for i, run in enumerate(runs):
            run_id, status, started, ended, dry_run = run
            duration = (ended - started).total_seconds() if ended else None
            print(f"\n{i+1}. {run_id}")
            print(f"   Status: {status} | Dry-run: {dry_run} | Duration: {duration}s")
            print(f"   Started: {started}")

except Exception as e:
    print(f"ERROR fetching runs: {e}")

# Check for any phase failures
try:
    with DatabaseContext('read') as cur:
        cur.execute('''
            SELECT phase_number, phase_name, COUNT(*) as count,
                   SUM(CASE WHEN phase_status != 'ok' THEN 1 ELSE 0 END) as failures
            FROM orchestrator_phase_log
            WHERE run_date >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY phase_number, phase_name
            ORDER BY phase_number
        ''')

        print("\n" + "=" * 90)
        print("PHASE EXECUTION SUMMARY (last 7 days)")
        print("=" * 90)

        for phase_num, phase_name, count, failures in cur.fetchall():
            failures = failures or 0
            fail_rate = (failures / count * 100) if count > 0 else 0
            status = "✓ OK" if fail_rate == 0 else f"⚠ {failures}/{count} ({fail_rate:.1f}%)"
            print(f"Phase {phase_num}: {phase_name:30} | {status}")

except Exception as e:
    print(f"ERROR analyzing phases: {e}")

# Check for any critical warnings
try:
    with DatabaseContext('read') as cur:
        cur.execute('''
            SELECT COUNT(*) as cnt FROM orchestrator_phase_log
            WHERE run_date >= CURRENT_DATE - INTERVAL '7 days'
            AND (phase_status = 'skipped' OR phase_status = 'blocked' OR phase_status = 'degraded')
        ''')
        result = cur.fetchone()
        if result and result[0] > 0:
            print(f"\n⚠️  Found {result[0]} phases with non-success status")
        else:
            print("\n✓ All phases either OK or not applicable")

except Exception as e:
    print(f"ERROR checking non-success phases: {e}")

print("\n" + "=" * 90)
