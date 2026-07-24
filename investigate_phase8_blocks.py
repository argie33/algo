#!/usr/bin/env python3
"""Investigate Phase 8 entry execution blocks and degradation."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext


def investigate_phase8():
    """Investigate Phase 8 blocked and degraded executions."""
    print("\n" + "="*80)
    print("INVESTIGATING PHASE 8 ENTRY EXECUTION BLOCKS")
    print("="*80 + "\n")

    try:
        with DatabaseContext("read") as cur:
            # 1. Get summary of Phase 8 executions
            print("1. PHASE 8 EXECUTION SUMMARY (Last 24 hours)")
            print("-" * 80)

            cur.execute(
                """
                SELECT status, COUNT(*) as count
                FROM algo_audit_log
                WHERE created_at > NOW() - INTERVAL '24 hours'
                AND action_type LIKE 'phase_8%'
                GROUP BY status
                ORDER BY count DESC
                """
            )

            statuses = cur.fetchall()
            total = sum(s[1] for s in statuses)
            print(f"Total Phase 8 log entries: {total}\n")

            for status, count in statuses:
                pct = (count / total) * 100
                icon = "✓" if status == "success" else "⚠" if status == "degraded" else "✗" if status == "blocked" else "?"
                print(f"  {icon} {status:20s}: {count:3d} ({pct:5.1f}%)")

            # 2. Get details of blocked executions
            print("\n2. PHASE 8 BLOCKED EXECUTIONS (reason analysis)")
            print("-" * 80)

            cur.execute(
                """
                SELECT created_at, details->>'summary' as summary, run_id
                FROM algo_audit_log
                WHERE created_at > NOW() - INTERVAL '24 hours'
                AND action_type LIKE 'phase_8%'
                AND status = 'blocked'
                ORDER BY created_at DESC
                LIMIT 10
                """
            )

            blocked = cur.fetchall()
            if blocked:
                print(f"Found {len(blocked)} blocked executions:\n")
                for created_at, summary, run_id in blocked:
                    print(f"  [{created_at}] {run_id}")
                    if summary:
                        summary_str = summary[:70] if len(summary) > 70 else summary
                        print(f"    Reason: {summary_str}")
            else:
                print("No blocked Phase 8 executions found!")

            # 3. Get details of degraded executions
            print("\n3. PHASE 8 DEGRADED EXECUTIONS (reason analysis)")
            print("-" * 80)

            cur.execute(
                """
                SELECT created_at, details->>'summary' as summary, run_id
                FROM algo_audit_log
                WHERE created_at > NOW() - INTERVAL '24 hours'
                AND action_type LIKE 'phase_8%'
                AND status = 'degraded'
                ORDER BY created_at DESC
                LIMIT 10
                """
            )

            degraded = cur.fetchall()
            if degraded:
                print(f"Found {len(degraded)} degraded executions:\n")
                for created_at, summary, run_id in degraded:
                    print(f"  [{created_at}] {run_id}")
                    if summary:
                        summary_str = summary[:70] if len(summary) > 70 else summary
                        print(f"    Reason: {summary_str}")
            else:
                print("No degraded Phase 8 executions found!")

            # 4. Check halt flag impact on Phase 8
            print("\n4. HALT FLAG STATUS & PHASE 8 IMPACT")
            print("-" * 80)

            cur.execute(
                """
                SELECT
                    al.status,
                    COUNT(*) as count,
                    SUM(CASE WHEN details->>'summary' ILIKE '%halt%' THEN 1 ELSE 0 END) as halt_mentions
                FROM algo_audit_log al
                WHERE created_at > NOW() - INTERVAL '24 hours'
                AND al.action_type = 'phase_8_entry_execution'
                GROUP BY al.status
                """
            )

            p8_halt_impact = cur.fetchall()
            if p8_halt_impact:
                print("Phase 8 logs mentioning halt flag:\n")
                for status, count, halt_mentions in p8_halt_impact:
                    print(f"  {status:15s}: {count} entries, {halt_mentions or 0} mention halt")

            # 5. Look at Phase 7 output when Phase 8 is blocked
            print("\n5. PHASE 7 OUTPUT WHEN PHASE 8 IS BLOCKED")
            print("-" * 80)

            cur.execute(
                """
                SELECT
                    al8.run_id,
                    al7.details->>'summary' as phase7_summary,
                    al8.details->>'summary' as phase8_summary
                FROM algo_audit_log al8
                LEFT JOIN algo_audit_log al7
                    ON al8.run_id = al7.run_id
                    AND al7.action_type LIKE 'phase_7%'
                WHERE al8.created_at > NOW() - INTERVAL '24 hours'
                AND al8.action_type = 'phase_8_entry_execution'
                AND al8.status = 'blocked'
                LIMIT 5
                """
            )

            runs_with_phase7 = cur.fetchall()
            if runs_with_phase7:
                print(f"Found {len(runs_with_phase7)} blocked Phase 8 runs with Phase 7 data:\n")
                for run_id, p7_summary, p8_summary in runs_with_phase7:
                    print(f"  {run_id}")
                    if p7_summary:
                        p7_str = p7_summary[:60] if len(p7_summary) > 60 else p7_summary
                        print(f"    Phase 7: {p7_str}")
                    if p8_summary:
                        p8_str = p8_summary[:60] if len(p8_summary) > 60 else p8_summary
                        print(f"    Phase 8: {p8_str}")

            # 6. Check exposure constraints blocking entries
            print("\n6. EXPOSURE CONSTRAINTS & PHASE 5 DATA")
            print("-" * 80)

            cur.execute(
                """
                SELECT
                    al5.details->>'summary' as phase5_summary,
                    COUNT(DISTINCT al8.run_id) as blocked_p8_runs
                FROM algo_audit_log al5
                LEFT JOIN algo_audit_log al8
                    ON al5.run_id = al8.run_id
                    AND al8.action_type = 'phase_8_entry_execution'
                    AND al8.status = 'blocked'
                WHERE al5.created_at > NOW() - INTERVAL '24 hours'
                AND al5.action_type = 'phase_5_exposure_policy'
                GROUP BY al5.details->>'summary'
                ORDER BY blocked_p8_runs DESC
                LIMIT 5
                """
            )

            exposure_impact = cur.fetchall()
            if exposure_impact:
                print("Phase 5 exposure settings when Phase 8 is blocked:\n")
                for p5_summary, blocked_count in exposure_impact:
                    if p5_summary:
                        p5_str = p5_summary[:50] if len(p5_summary) > 50 else p5_summary
                        print(f"  {p5_str}")
                        print(f"    → Blocked {blocked_count} Phase 8 runs")

            # 7. Check halt flag presence
            print("\n7. HALT FLAG CORRELATION")
            print("-" * 80)

            cur.execute(
                """
                SELECT
                    COUNT(DISTINCT run_id) as total_runs,
                    SUM(CASE WHEN halt_reason IS NOT NULL THEN 1 ELSE 0 END) as halted_runs,
                    SUM(CASE WHEN halt_reason IS NULL THEN 1 ELSE 0 END) as non_halted_runs
                FROM algo_orchestrator_runs
                WHERE started_at > NOW() - INTERVAL '24 hours'
                """
            )

            halt_stats = cur.fetchone()
            if halt_stats:
                total, halted, non_halted = halt_stats
                print(f"Halt flag presence in orchestrator runs:")
                print(f"  Total runs: {total}")
                print(f"  Halted: {halted} ({100*halted/max(total,1):.1f}%)")
                print(f"  Not halted: {non_halted} ({100*non_halted/max(total,1):.1f}%)")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(investigate_phase8())
