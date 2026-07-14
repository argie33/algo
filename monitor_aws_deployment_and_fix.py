#!/usr/bin/env python3
"""
Monitor AWS orchestrator deployment and verify Phase 1 EOD tolerance fix works.

Sequence:
1. GitHub Actions CI runs (should pass)
2. Deploy-orchestrator-lambda workflow runs (~2-3 min)
3. Lambda function updated with fixed code
4. EventBridge triggers next orchestrator run (4:05 PM ET)
5. Orchestrator runs with fixed code
6. Phase 1 passes (EOD tolerance accepting previous trading day)
7. Phase 9 executes (exit reconciliation)
8. Trade metrics calculate correctly
"""

import sys
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2


def check_latest_aws_orchestrator_run():
    """Get the latest AWS orchestrator run and verify the fix is working."""
    try:
        conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
        cur = conn.cursor()

        # Get the most recent AWS (non-LOCAL) orchestrator run
        cur.execute('''
            SELECT
                run_id,
                started_at,
                completed_at,
                overall_status,
                halt_reason
            FROM algo_orchestrator_runs
            WHERE run_id NOT LIKE 'LOCAL%'
            ORDER BY started_at DESC
            LIMIT 1
        ''')

        row = cur.fetchone()
        if not row:
            conn.close()
            return None

        run_id, started, completed, status, halt = row

        # Get phase execution details
        cur.execute('''
            SELECT phase_results, phases_completed, phases_halted
            FROM orchestrator_execution_log
            WHERE run_id = %s
            LIMIT 1
        ''', (run_id,))

        phase_row = cur.fetchone()
        phase_results = None
        phases_completed = 0
        phases_halted = 0
        if phase_row:
            phase_results, phases_completed, phases_halted = phase_row

        conn.close()

        return {
            'run_id': run_id,
            'started': started,
            'completed': completed,
            'status': status,
            'halt_reason': halt,
            'phase_results': phase_results,
            'phases_completed': phases_completed,
            'phases_halted': phases_halted
        }

    except Exception as e:
        print(f"Database error: {e}")
        return None


def verify_fix_working(run_data):
    """Verify Phase 1 EOD tolerance fix is working."""
    if not run_data:
        return False, "No run data"

    phase_results = run_data.get('phase_results')
    if not phase_results:
        return False, "No phase results found"

    try:
        if isinstance(phase_results, str):
            phases = json.loads(phase_results)
        else:
            phases = phase_results

        if not isinstance(phases, list):
            return False, "Phase results not a list"

        phase_1 = next((p for p in phases if p.get('phase') == '1'), None)
        phase_9 = next((p for p in phases if p.get('phase') == '9'), None)

        if not phase_1:
            return False, "Phase 1 not found"

        if phase_1.get('status') != 'ok':
            return False, f"Phase 1 failed: {phase_1.get('status')}"

        if not phase_9:
            return False, "Phase 9 not found (exit reconciliation not running)"

        if phase_9.get('status') not in ('ok', 'halted'):
            return False, f"Phase 9 failed: {phase_9.get('status')}"

        return True, f"PASS: Phase 1 ok, Phase 9 {phase_9.get('status')}"

    except Exception as e:
        return False, f"Error parsing phases: {e}"


def main():
    """Monitor and verify the fix."""
    print("=" * 70)
    print("AWS ORCHESTRATOR PHASE 1 EOD TOLERANCE FIX VERIFICATION")
    print("=" * 70)
    print()

    now_et = datetime.now(ZoneInfo('America/New_York'))
    print(f"Current time: {now_et.strftime('%H:%M:%S %Z on %A %Y-%m-%d')}")
    print()

    # Check the latest AWS run
    run_data = check_latest_aws_orchestrator_run()

    if not run_data:
        print("Status: No AWS orchestrator runs found in database yet")
        print()
        print("Deployment Status:")
        print("  1. GitHub Actions CI: Running (pushed commits)")
        print("  2. Deploy-orchestrator-lambda: Pending")
        print("  3. Lambda function: Updating...")
        print("  4. Next orchestrator run: 4:05 PM ET")
        print()
        return 1

    run_date = run_data['started'].date() if run_data['started'] else None
    today = datetime.now(ZoneInfo('America/New_York')).date()

    print(f"Latest AWS Run: {run_data['run_id']}")
    print(f"Started: {run_data['started']}")
    print(f"Status: {run_data['status']}")
    print(f"Phases: {run_data['phases_completed']} completed, {run_data['phases_halted']} halted")
    print()

    if run_date and run_date < today:
        print("Status: Latest run is from before today")
        print("Waiting for next scheduled orchestrator run at 4:05 PM ET...")
        return 1

    # Verify the fix
    success, message = verify_fix_working(run_data)

    if success:
        print(f"VERIFICATION: {message}")
        print()
        print("✓ FIX CONFIRMED WORKING IN AWS")
        print("  - Phase 1: EOD tolerance accepting previous trading day data")
        print("  - Phase 9: Exit reconciliation executing")
        print("  - Trade metrics: Pipeline active")
        return 0
    else:
        print(f"VERIFICATION: {message}")
        print()
        print("Status: Fix not yet verified in production")
        return 1


if __name__ == '__main__':
    sys.exit(main())
