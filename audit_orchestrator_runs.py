#!/usr/bin/env python3
"""Comprehensive audit of recent orchestrator runs to find patterns and issues."""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ


def audit_recent_runs(limit: int = 50):
    """Audit recent orchestrator runs for patterns and issues."""
    print(f"\n{'='*80}")
    print(f"ORCHESTRATOR RUNS AUDIT (Last {limit} runs)")
    print(f"{'='*80}\n")

    try:
        with DatabaseContext("read") as cur:
            # Get recent runs
            cur.execute(
                """
                SELECT
                    run_id, started_at, overall_status,
                    phase_1_status, phase_2_status, phase_3_status, phase_4_status,
                    phase_5_status, phase_6_status, phase_7_status, phase_8_status,
                    phase_9_status, execution_mode, notes
                FROM algo_orchestrator_runs
                WHERE started_at > NOW() - INTERVAL '7 days'
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (limit,),
            )

            runs = cur.fetchall()
            if not runs:
                print("No recent orchestrator runs found")
                return

            print(f"Found {len(runs)} runs in last 7 days\n")

            # Analyze overall status distribution
            status_counts = {}
            phase_failure_counts = {}
            for run in runs:
                overall_status = run[2]
                status_counts[overall_status] = status_counts.get(overall_status, 0) + 1

                # Track phase failures
                for phase_num in range(1, 10):
                    phase_status_idx = 2 + phase_num  # phase_1_status is at index 3
                    if phase_status_idx < len(run):
                        phase_status = run[phase_status_idx]
                        if phase_status and phase_status != "success":
                            phase_key = f"Phase {phase_num}"
                            phase_failure_counts[phase_key] = phase_failure_counts.get(phase_key, 0) + 1

            print("OVERALL STATUS DISTRIBUTION:")
            for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
                pct = (count / len(runs)) * 100
                print(f"  {status:20s}: {count:3d} runs ({pct:5.1f}%)")

            print("\nPHASE FAILURE RATES (non-success statuses):")
            if phase_failure_counts:
                for phase, count in sorted(phase_failure_counts.items(), key=lambda x: -x[1]):
                    pct = (count / len(runs)) * 100
                    print(f"  {phase:10s}: {count:3d} failures ({pct:5.1f}%)")
            else:
                print("  No phase failures detected!")

            # Show recent failures in detail
            failures = [r for r in runs if r[2] != "success"]
            if failures:
                print(f"\nRECENT FAILURES ({len(failures)} total):")
                for run in failures[:10]:  # Show last 10 failures
                    run_id, started_at, overall_status = run[0], run[1], run[2]
                    phase_statuses = {
                        f"P{i}": run[2+i]
                        for i in range(1, 10)
                        if 2+i < len(run)
                    }

                    # Find which phases failed
                    failed_phases = [k for k, v in phase_statuses.items() if v and v != "success"]

                    print(f"\n  {run_id}")
                    print(f"    Time: {started_at} ({(datetime.now(timezone.utc) - started_at).total_seconds() / 3600:.1f}h ago)")
                    print(f"    Overall: {overall_status}")
                    if failed_phases:
                        print(f"    Failed phases: {', '.join(failed_phases)}")
                        # Show specific phase statuses
                        for phase in failed_phases:
                            phase_num = int(phase[1:])
                            phase_status_idx = 2 + phase_num
                            if phase_status_idx < len(run):
                                print(f"      {phase}: {run[phase_status_idx]}")

                    # Show notes if present
                    if run[13]:  # notes field
                        print(f"    Notes: {run[13][:100]}")

            # Check for recent success/skip transitions
            print("\n\nRECENT RUN TIMELINE (Last 20 runs):")
            for i, run in enumerate(runs[:20]):
                run_id, started_at, overall_status = run[0], run[1], run[2]
                started_et = started_at.astimezone(EASTERN_TZ) if started_at.tzinfo else started_at

                # Simplified phase status
                phase_statuses = [run[3+j] if 3+j < len(run) else None for j in range(9)]
                phase_summary = "".join([
                    ("✓" if s == "success" else "✗" if s == "error" else "⊘" if s in ("skip", "graceful_skip") else "?" if s else "-")
                    for s in phase_statuses
                ])

                print(f"  [{i+1:2d}] {started_et.strftime('%Y-%m-%d %H:%M')} | {overall_status:10s} | Phases: {phase_summary} | {run_id}")

            # Check for data anomalies
            print("\n\nDATA ANOMALY CHECK:")
            cur.execute(
                """
                SELECT COUNT(*) as total_runs,
                       SUM(CASE WHEN overall_status = 'success' THEN 1 ELSE 0 END) as successful,
                       SUM(CASE WHEN overall_status = 'error' THEN 1 ELSE 0 END) as errors,
                       SUM(CASE WHEN overall_status = 'halted' THEN 1 ELSE 0 END) as halts,
                       SUM(CASE WHEN overall_status = 'skipped' THEN 1 ELSE 0 END) as skips
                FROM algo_orchestrator_runs
                WHERE started_at > NOW() - INTERVAL '24 hours'
                """
            )

            stats = cur.fetchone()
            if stats:
                print(f"  Last 24 hours:")
                print(f"    Total runs: {stats[0]}")
                print(f"    Successful: {stats[1]} ({100*stats[1]/max(stats[0],1):.1f}%)")
                print(f"    Errors: {stats[2]}")
                print(f"    Halts: {stats[3]}")
                print(f"    Skips: {stats[4]}")

            # Look for per-phase error patterns
            print("\n\nPHASE-BY-PHASE ERROR ANALYSIS:")
            for phase_num in range(1, 10):
                phase_col = f"phase_{phase_num}_status"
                cur.execute(
                    f"""
                    SELECT {phase_col}, COUNT(*) as count
                    FROM algo_orchestrator_runs
                    WHERE started_at > NOW() - INTERVAL '7 days'
                    AND {phase_col} IS NOT NULL
                    GROUP BY {phase_col}
                    ORDER BY count DESC
                    """
                )

                statuses = cur.fetchall()
                if statuses and any(s[0] != "success" for s in statuses):
                    print(f"\n  Phase {phase_num}:")
                    for status, count in statuses:
                        pct = (count / sum(s[1] for s in statuses)) * 100
                        icon = "✓" if status == "success" else "✗"
                        print(f"    {icon} {status:20s}: {count:3d} ({pct:5.1f}%)")

    except Exception as e:
        print(f"ERROR during audit: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(audit_recent_runs())
