#!/usr/bin/env python3
"""Analyze the latest orchestrator run in detail."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ


def analyze_latest_run():
    """Analyze the latest orchestrator run."""
    print("\n" + "="*80)
    print("ANALYZING LATEST ORCHESTRATOR RUN")
    print("="*80 + "\n")

    try:
        with DatabaseContext("read") as cur:
            # Get latest run
            cur.execute(
                """
                SELECT run_id, run_date, overall_status, halt_reason, started_at, completed_at, execution_time_seconds
                FROM algo_orchestrator_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )

            run = cur.fetchone()
            if not run:
                print("No orchestrator runs found!")
                return 1

            run_id, run_date, overall_status, halt_reason, started_at, completed_at, exec_time = run

            print(f"Run ID: {run_id}")
            print(f"Date: {run_date}")
            print(f"Status: {overall_status}")
            if halt_reason:
                print(f"Halt Reason: {halt_reason}")
            print(f"Started: {started_at}")
            print(f"Completed: {completed_at}")
            print(f"Execution time: {exec_time:.2f}s\n")

            # Get all phase logs for this run using JSONB operators
            print("="*80)
            print("PHASE EXECUTION LOG")
            print("="*80 + "\n")

            cur.execute(
                """
                SELECT action_type, status, created_at, details
                FROM algo_audit_log
                WHERE details @> %s
                ORDER BY created_at ASC
                """,
                (json.dumps({"run_id": run_id}),),
            )

            logs = cur.fetchall()

            if logs:
                print(f"Found {len(logs)} log entries for this run:\n")

                # Group by phase
                phases = {}
                for action_type, status, created_at, details in logs:
                    phase_key = action_type.split("_")[1] if "_" in action_type else "unknown"
                    if phase_key not in phases:
                        phases[phase_key] = []
                    phases[phase_key].append({
                        "action": action_type,
                        "status": status,
                        "time": created_at,
                        "details": details,
                    })

                # Print by phase
                for phase_key in sorted(phases.keys(), key=lambda x: (0 if x.isdigit() else 1, x)):
                    phase_logs = phases[phase_key]
                    print(f"\n  PHASE {phase_key}:")
                    for entry in phase_logs:
                        time_str = entry["time"].strftime("%H:%M:%S.%f")[:-3] if entry["time"] else "?"
                        status_icon = "✓" if entry["status"] in ("success", "ok") else "⚠" if entry["status"] == "warn" else "✗"
                        print(f"    {status_icon} [{time_str}] {entry['action']:45s} {entry['status']:10s}")
                        if entry["details"] and "summary" in entry["details"]:
                            summary = entry["details"]["summary"]
                            if len(summary) > 70:
                                summary = summary[:67] + "..."
                            print(f"               {summary}")

            else:
                print(f"No logs found for run {run_id}")

            # Check for warnings or errors in this run
            print("\n\n" + "="*80)
            print("WARNINGS & ERRORS")
            print("="*80 + "\n")

            cur.execute(
                """
                SELECT DISTINCT ON (action_type, status) action_type, status, details
                FROM algo_audit_log
                WHERE details @> %s
                AND status IN ('warn', 'error', 'halt')
                ORDER BY action_type, status, created_at DESC
                """,
                (json.dumps({"run_id": run_id}),),
            )

            warnings = cur.fetchall()
            if warnings:
                print(f"Found {len(warnings)} warnings/errors:\n")
                for action_type, status, details in warnings:
                    print(f"  {action_type:45s} [{status:10s}]")
                    if details and "summary" in details:
                        print(f"    {details['summary']}")
            else:
                print("No warnings or errors found in this run!")

            # Summary analysis
            print("\n\n" + "="*80)
            print("SUMMARY ANALYSIS")
            print("="*80 + "\n")

            # Count by status
            status_counts = {}
            for action_type, status, created_at, details in logs:
                status_counts[status] = status_counts.get(status, 0) + 1

            print("Status distribution:")
            for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
                icon = "✓" if status in ("success", "ok") else "⚠" if status == "warn" else "✗"
                pct = (count / len(logs)) * 100
                print(f"  {icon} {status:10s}: {count:3d} ({pct:5.1f}%)")

            # Check if all 9 phases ran
            print("\nPhase completion check:")
            for phase_num in range(1, 10):
                phase_key = str(phase_num)
                if phase_key in phases:
                    print(f"  ✓ Phase {phase_num}: {len(phases[phase_key])} log entries")
                else:
                    print(f"  ✗ Phase {phase_num}: NO LOG ENTRIES FOUND - MISSING!")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(analyze_latest_run())
