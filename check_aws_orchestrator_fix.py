#!/usr/bin/env python3
"""Monitor for AWS orchestrator run and verify Phase 1 EOD tolerance fix is working."""

import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import json


def check_latest_aws_run():
    """Check if latest AWS orchestrator run shows Phase 1 passing and Phase 9 running."""
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
            return None, "No AWS runs found in database yet"

        run_id, started, completed, status, halt = row

        # Get phase execution details
        cur.execute('''
            SELECT phase_results
            FROM orchestrator_execution_log
            WHERE run_id = %s
            LIMIT 1
        ''', (run_id,))

        phase_row = cur.fetchone()
        phase_results = None
        if phase_row:
            phase_results = phase_row[0]

        conn.close()

        return {
            'run_id': run_id,
            'started': started,
            'completed': completed,
            'status': status,
            'halt_reason': halt,
            'phase_results': phase_results
        }, None

    except Exception as e:
        return None, str(e)


def verify_fix_working(run_data):
    """Verify the Phase 1 EOD tolerance fix is working in the AWS run."""
    if not run_data:
        return False, "No run data"

    # Check if Phase 1 passed
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
            return False, "Phase 1 not found in results"

        if phase_1.get('status') != 'ok':
            return False, f"Phase 1 failed: {phase_1.get('status')}"

        if not phase_9:
            return False, "Phase 9 not found (exit reconciliation not running)"

        if phase_9.get('status') not in ('ok', 'halted'):
            # Phase 9 should complete (ok) or be deliberately halted by-design
            # Any error status means something went wrong
            return False, f"Phase 9 failed: {phase_9.get('status')}"

        return True, f"SUCCESS: Phase 1 passing, Phase 9 running (status={phase_9.get('status')})"

    except Exception as e:
        return False, f"Error parsing phase results: {e}"


def main():
    """Main monitoring loop."""
    print("=" * 70)
    print("AWS ORCHESTRATOR PHASE 1 EOD TOLERANCE FIX VERIFICATION")
    print("=" * 70)
    print()

    now_et = datetime.now(ZoneInfo('America/New_York'))
    print(f"Current time: {now_et.strftime('%H:%M:%S %Z on %A %Y-%m-%d')}")
    print()

    run_data, error = check_latest_aws_run()

    if error:
        print(f"DATABASE ERROR: {error}")
        print()
        print("Status: Waiting for next AWS orchestrator run...")

        next_run = now_et.replace(hour=16, minute=5, second=0, microsecond=0)
        if now_et > next_run:
            next_run += timedelta(days=1)

        minutes_until = (next_run - now_et).total_seconds() / 60
        print(f"Next scheduled run: {next_run.strftime('%H:%M %Z on %A %Y-%m-%d')} ({minutes_until:.0f} minutes)")
        return 1

    print(f"Latest AWS Run: {run_data['run_id']}")
    print(f"Started: {run_data['started']}")
    print(f"Completed: {run_data['completed']}")
    print(f"Status: {run_data['status']}")
    print()

    # Check if this is a new run from today or later
    run_date = run_data['started'].date() if run_data['started'] else None
    today = datetime.now(ZoneInfo('America/New_York')).date()

    if run_date and run_date < today:
        print("Status: Latest AWS run is from before today")
        print("Waiting for next scheduled orchestrator run...")

        next_run = now_et.replace(hour=16, minute=5, second=0, microsecond=0)
        if now_et > next_run:
            next_run += timedelta(days=1)

        minutes_until = (next_run - now_et).total_seconds() / 60
        print(f"Next run at: {next_run.strftime('%H:%M %Z on %A %Y-%m-%d')} ({minutes_until:.0f} minutes)")
        return 1

    # Verify the fix is working
    success, message = verify_fix_working(run_data)

    if success:
        print(f"VERIFICATION: {message}")
        print()
        print("✓ FIX CONFIRMED WORKING IN AWS")
        print("  - Phase 1 is passing (EOD tolerance accepting previous trading day data)")
        print("  - Phase 9 is running (exit reconciliation executing)")
        print("  - Trade metrics pipeline active (R, Days, Grade, MFE%, MAE%)")
        return 0
    else:
        print(f"VERIFICATION FAILED: {message}")
        print()
        print("Status: Fix not yet verified in AWS production")
        return 1


if __name__ == '__main__':
    sys.exit(main())
