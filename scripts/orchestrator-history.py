#!/usr/bin/env python3
"""
CLI tool to view orchestrator execution history.

Usage:
  python scripts/orchestrator-history.py recent [days]         # View recent runs
  python scripts/orchestrator-history.py failed [days]         # View failed/halted runs
  python scripts/orchestrator-history.py patterns [days]       # Analyze halt patterns
  python scripts/orchestrator-history.py stats [days]          # View success statistics
  python scripts/orchestrator-history.py details <RUN_ID>      # View details of a specific run
  python scripts/orchestrator-history.py latest               # Show latest run with all phases

Examples:
  # View last 7 days of runs
  python scripts/orchestrator-history.py recent

  # View failures in the last 30 days
  python scripts/orchestrator-history.py failed 30

  # See which phases halt most often
  python scripts/orchestrator-history.py patterns 30

  # Diagnose a specific run
  python scripts/orchestrator-history.py details RUN-2026-06-07-093045
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.orchestrator_query import (
    get_recent_runs,
    get_failed_runs,
    get_halt_patterns,
    get_success_rate,
    get_run_details,
)


def format_time_delta(start_str, end_str):
    """Format the time delta between two ISO timestamps."""
    try:
        start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        delta = (end - start).total_seconds()
        return f"{delta:.1f}s"
    except:
        return "??"


def cmd_recent(days=7, limit=10):
    """Show recent runs."""
    runs = get_recent_runs(days, limit)
    if not runs:
        print(f"No orchestrator runs found in the past {days} days")
        return

    print(f"\n{'='*130}")
    print(f"Recent Orchestrator Runs (past {days} days) — Latest {len(runs)} runs")
    print(f"{'='*130}\n")
    print(
        f"{'Run ID':<25} {'Date':<12} {'Status':<10} {'Duration':<10} "
        f"{'OK/Halt/Err':<12} {'Summary':<60}"
    )
    print("-" * 130)

    for run in runs:
        ok = run['phases_completed'] or 0
        halt = run['phases_halted'] or 0
        err = run['phases_errored'] or 0
        duration = ""
        if run['started_at'] and run['completed_at']:
            duration = format_time_delta(run['started_at'], run['completed_at'])
        else:
            duration = "running"

        summary = (run['summary'] or '')[:55]
        status_color = {
            'success': '✓ ' + run['status'],
            'halted': '⚠ ' + run['status'],
            'error': '✗ ' + run['status'],
            'skipped': '⊘ ' + run['status'],
        }.get(run['status'], run['status'])

        print(
            f"{run['run_id']:<25} {run['run_date']:<12} {status_color:<12} "
            f"{duration:<10} {ok}/{halt}/{err:<10} {summary:<60}"
        )

    print()


def cmd_failed(days=30):
    """Show failed/halted runs."""
    runs = get_failed_runs(days)
    if not runs:
        print(f"✓ No failed/halted runs found in the past {days} days\n")
        return

    print(f"\n{'='*130}")
    print(f"Failed/Halted Orchestrator Runs (past {days} days) — {len(runs)} failures")
    print(f"{'='*130}\n")
    print(f"{'Run ID':<25} {'Date':<12} {'Status':<10} {'Reason':<75}")
    print("-" * 130)

    for run in runs:
        reason = (run['halt_reason'] or run['summary'] or 'Unknown')[:70]
        status_sym = '✗' if run['status'] == 'error' else '⚠'
        print(
            f"{status_sym} {run['run_id']:<23} {run['run_date']:<12} {run['status']:<10} "
            f"{reason:<75}"
        )

    print()


def cmd_patterns(days=30):
    """Show phase halt patterns."""
    patterns = get_halt_patterns(days)
    if not patterns:
        print(f"✓ No halt patterns found in the past {days} days\n")
        return

    print(f"\n{'='*130}")
    print(f"Phase Halt Patterns (past {days} days) — Which phases halt most often?")
    print(f"{'='*130}\n")

    for pattern in patterns:
        print(f"Phase {pattern['phase']:>2s}: halted {pattern['total_halts']} times")
        if pattern['common_reasons']:
            for reason, count in sorted(
                pattern['common_reasons'].items(), key=lambda x: -int(x[1])
            ):
                print(f"  • {reason[:85]}")
        print()


def cmd_stats(days=7):
    """Show success rate statistics."""
    stats = get_success_rate(days)
    if not stats:
        print("No execution data available\n")
        return

    print(f"\n{'='*130}")
    print(f"Execution Statistics (past {stats['period_days']} days)")
    print(f"{'='*130}\n")
    print(f"  Total runs:    {stats['total_runs']}")
    print(f"  Success rate:  {stats['success_rate']}")
    print(f"  Halt rate:     {stats['halt_rate']}")
    print(f"  Error rate:    {stats['error_rate']}")
    print(f"\n  Breakdown by status:")
    for status, count in sorted(stats['by_status'].items()):
        pct = (count / stats['total_runs'] * 100) if stats['total_runs'] > 0 else 0
        print(f"    {status:10s}: {count:3d} ({pct:5.1f}%)")

    print()


def cmd_details(run_id):
    """Show details of a specific run."""
    details = get_run_details(run_id)
    if not details:
        print(f"✗ Run {run_id} not found\n")
        return

    print(f"\n{'='*130}")
    print(f"Run Details: {run_id}")
    print(f"{'='*130}\n")
    print(f"  Date:           {details['run_date']}")
    print(f"  Status:         {details['status']}")
    print(f"  Started:        {details['started_at']}")
    print(f"  Completed:      {details['completed_at']}")
    if details['completed_at'] and details['started_at']:
        delta = format_time_delta(details['started_at'], details['completed_at'])
        print(f"  Duration:       {delta}")
    print(f"  Summary:        {details['summary']}")
    if details['halt_reason']:
        print(f"  Halt Reason:    {details['halt_reason']}")

    print(f"\n  Phase Results ({details['phases_completed']} OK, {details['phases_halted']} Halted, "
          f"{details['phases_errored']} Errored):")
    print()

    phases = details['phase_results']
    if isinstance(phases, list):
        for phase in phases:
            status_sym = {
                'success': '✓',
                'halt': '⚠',
                'error': '✗',
            }.get(phase.get('status', '?'), '?')

            phase_id = phase.get('phase', '?')
            phase_name = phase.get('name', 'Unknown')[:20]
            summary = phase.get('summary', '')[:80]

            print(f"    {status_sym} Phase {phase_id:<2} ({phase_name:20s}): {summary}")

    print()


def cmd_latest():
    """Show the latest run with all phase details."""
    runs = get_recent_runs(days=7, limit=1)
    if not runs:
        print("No recent runs found\n")
        return

    run_id = runs[0]['run_id']
    cmd_details(run_id)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        cmd_recent()
        cmd_stats()
        return

    cmd = sys.argv[1]

    try:
        if cmd == "recent":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
            cmd_recent(days)
        elif cmd == "failed":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            cmd_failed(days)
        elif cmd == "patterns":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            cmd_patterns(days)
        elif cmd == "stats":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
            cmd_stats(days)
        elif cmd == "details":
            if len(sys.argv) > 2:
                cmd_details(sys.argv[2])
            else:
                print("Usage: python scripts/orchestrator-history.py details <RUN_ID>")
        elif cmd == "latest":
            cmd_latest()
        elif cmd in ("-h", "--help", "help"):
            print(__doc__)
        else:
            print(f"Unknown command: {cmd}")
            print(__doc__)
    except KeyboardInterrupt:
        print("\n")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
