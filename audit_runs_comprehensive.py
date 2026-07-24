#!/usr/bin/env python3
"""Comprehensive audit of orchestrator runs to find ALL issues."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ


def audit_comprehensive():
    """Comprehensive orchestrator audit."""
    print("\n" + "="*80)
    print("COMPREHENSIVE ORCHESTRATOR AUDIT")
    print("="*80 + "\n")

    try:
        with DatabaseContext("read") as cur:
            # 1. Get run summary statistics
            print("1. RUN STATISTICS (Last 24 hours)")
            print("-" * 80)

            cur.execute(
                """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN overall_status = 'success' THEN 1 ELSE 0 END) as successful,
                       SUM(CASE WHEN overall_status = 'error' THEN 1 ELSE 0 END) as errors,
                       SUM(CASE WHEN overall_status = 'halted' THEN 1 ELSE 0 END) as halts,
                       AVG(execution_time_seconds) as avg_time_seconds
                FROM algo_orchestrator_runs
                WHERE started_at > NOW() - INTERVAL '24 hours'
                """
            )

            stats = cur.fetchone()
            if stats and stats[0]:
                total, successful, errors, halts, avg_time = stats
                success_pct = (successful / total) * 100
                print(f"Total runs: {total}")
                print(f"Successful: {successful} ({success_pct:.1f}%)")
                print(f"Errors: {errors or 0}")
                print(f"Halts: {halts or 0}")
                print(f"Avg execution time: {avg_time:.1f}s\n")

            # 2. Check for errors in recent runs
            print("2. ERROR LOG ANALYSIS (Last 24 hours)")
            print("-" * 80)

            cur.execute(
                """
                SELECT action_type, status, COUNT(*) as count
                FROM algo_audit_log
                WHERE created_at > NOW() - INTERVAL '24 hours'
                AND status IN ('error', 'halt', 'warn')
                GROUP BY action_type, status
                ORDER BY count DESC, status DESC
                LIMIT 20
                """
            )

            error_logs = cur.fetchall()
            if error_logs:
                print(f"Found {len(error_logs)} error/halt/warning patterns:\n")
                for action_type, status, count in error_logs:
                    icon = "✗" if status == "error" else "⊘" if status == "halt" else "⚠"
                    print(f"  {icon} {action_type:45s} [{status:10s}] × {count:3d}")
            else:
                print("No errors, halts, or warnings found in last 24 hours!\n")

            # 3. Look for phase failures
            print("\n3. PHASE FAILURE ANALYSIS")
            print("-" * 80)

            cur.execute(
                """
                SELECT SUBSTRING(action_type, 1, 7) as phase_key,
                       status,
                       COUNT(*) as count
                FROM algo_audit_log
                WHERE created_at > NOW() - INTERVAL '24 hours'
                AND action_type LIKE 'phase_%'
                GROUP BY phase_key, status
                ORDER BY phase_key, status
                """
            )

            phase_stats = cur.fetchall()
            if phase_stats:
                current_phase = None
                for phase_key, status, count in phase_stats:
                    if phase_key != current_phase:
                        if current_phase:
                            print()
                        current_phase = phase_key
                        print(f"  {phase_key}:")

                    icon = "✓" if status in ("success", "ok") else "⚠" if status == "warn" else "✗"
                    print(f"    {icon} {status:10s}: {count:3d}")
            else:
                print("No phase logs found!")

            # 4. Check for specific issues
            print("\n\n4. SPECIFIC ISSUE CHECKS")
            print("-" * 80)

            checks = [
                ("Data freshness issues",
                 "SELECT COUNT(*) FROM algo_audit_log WHERE created_at > NOW() - INTERVAL '24 hours' AND action_type LIKE '%data_freshness%' AND status = 'error'"),
                ("Circuit breaker trips",
                 "SELECT COUNT(*) FROM algo_audit_log WHERE created_at > NOW() - INTERVAL '24 hours' AND action_type LIKE '%circuit%' AND status = 'warn'"),
                ("Position reconciliation failures",
                 "SELECT COUNT(*) FROM algo_audit_log WHERE created_at > NOW() - INTERVAL '24 hours' AND action_type LIKE '%reconciliation%' AND status = 'error'"),
                ("Trade execution failures",
                 "SELECT COUNT(*) FROM algo_audit_log WHERE created_at > NOW() - INTERVAL '24 hours' AND action_type LIKE '%entry_execution%' AND status = 'error'"),
                ("Exit execution failures",
                 "SELECT COUNT(*) FROM algo_audit_log WHERE created_at > NOW() - INTERVAL '24 hours' AND action_type LIKE '%exit_execution%' AND status = 'error'"),
                ("Signal generation issues",
                 "SELECT COUNT(*) FROM algo_audit_log WHERE created_at > NOW() - INTERVAL '24 hours' AND action_type LIKE '%signal%' AND status = 'error'"),
            ]

            for check_name, query in checks:
                try:
                    cur.execute(query)
                    count = cur.fetchone()[0]
                    if count > 0:
                        print(f"  ✗ {check_name}: {count} issues")
                    else:
                        print(f"  ✓ {check_name}: OK")
                except Exception as e:
                    print(f"  ? {check_name}: Query error - {e}")

            # 5. Check for performance issues
            print("\n\n5. PERFORMANCE ANALYSIS")
            print("-" * 80)

            cur.execute(
                """
                SELECT
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY execution_time_seconds) as p50,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY execution_time_seconds) as p75,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY execution_time_seconds) as p95,
                    MAX(execution_time_seconds) as max
                FROM algo_orchestrator_runs
                WHERE started_at > NOW() - INTERVAL '24 hours'
                """
            )

            perf = cur.fetchone()
            if perf and perf[0]:
                p50, p75, p95, max_time = perf
                print(f"Execution time (last 24h):")
                print(f"  Median (p50): {p50:.1f}s")
                print(f"  75th pct: {p75:.1f}s")
                print(f"  95th pct: {p95:.1f}s")
                print(f"  Maximum: {max_time:.1f}s")

                if p95 and p95 > 120:
                    print(f"  ⚠ WARNING: 95th percentile ({p95:.1f}s) exceeds 2 minutes")
                if max_time and max_time > 180:
                    print(f"  ✗ CRITICAL: Maximum execution time ({max_time:.1f}s) exceeds 3 minutes")

            # 6. Recent failures (if any)
            print("\n\n6. MOST RECENT ISSUES")
            print("-" * 80)

            cur.execute(
                """
                SELECT created_at, action_type, status, details->>'summary' as summary
                FROM algo_audit_log
                WHERE created_at > NOW() - INTERVAL '24 hours'
                AND status IN ('error', 'halt')
                ORDER BY created_at DESC
                LIMIT 10
                """
            )

            issues = cur.fetchall()
            if issues:
                print(f"Found {len(issues)} recent issues:\n")
                for created_at, action_type, status, summary in issues:
                    time_str = created_at.strftime("%H:%M:%S")
                    print(f"  [{time_str}] {action_type:45s} [{status:10s}]")
                    if summary:
                        summary_str = summary[:70] if len(summary) > 70 else summary
                        print(f"             {summary_str}")
            else:
                print("No errors or halts in last 24 hours!\n")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(audit_comprehensive())
