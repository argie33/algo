#!/usr/bin/env python3
"""Investigate Phase 7 signal quality score error."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext


def investigate_phase7():
    """Investigate Phase 7 signal quality score errors."""
    print("\n" + "="*80)
    print("INVESTIGATING PHASE 7 SIGNAL QUALITY SCORE ERROR")
    print("="*80 + "\n")

    try:
        with DatabaseContext("read") as cur:
            # 1. Get the specific error
            print("1. FINDING THE NOEM ERROR")
            print("-" * 80)

            cur.execute(
                """
                SELECT created_at, details
                FROM algo_audit_log
                WHERE action_type = 'phase_7_SIGNAL GENERATION & RANKING'
                AND status = 'error'
                AND details->>'summary' ILIKE '%NOEM%'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )

            error = cur.fetchone()
            if error:
                created_at, details = error
                print(f"Found error at: {created_at}")
                print(f"\nError details:")
                if isinstance(details, dict):
                    print(json.dumps(details, indent=2))
                else:
                    print(details)
            else:
                print("No NOEM error found. Checking for recent Phase 7 errors...")
                cur.execute(
                    """
                    SELECT created_at, details
                    FROM algo_audit_log
                    WHERE action_type LIKE 'phase_7%'
                    AND status IN ('error', 'halt')
                    ORDER BY created_at DESC
                    LIMIT 5
                    """
                )

                errors = cur.fetchall()
                for created_at, details in errors:
                    print(f"\n[{created_at}]")
                    if isinstance(details, dict):
                        print(json.dumps(details, indent=2)[:200])
                    else:
                        print(str(details)[:200])

            # 2. Check Phase 7 implementation
            print("\n\n2. CHECKING PHASE 7 SOURCE CODE")
            print("-" * 80)

            code_path = Path(__file__).parent / "algo" / "orchestrator" / "phase7_signal_generation.py"
            if code_path.exists():
                with open(code_path) as f:
                    content = f.read()

                    # Look for defensive filter
                    if "None signal_quality_score" in content or "signal_quality_score is None" in content:
                        print("✓ Found defensive filter for None signal_quality_score")
                        # Find the line number
                        for i, line in enumerate(content.split('\n'), 1):
                            if "signal_quality_score is None" in line or "is not None" in line:
                                print(f"  Line {i}: {line.strip()[:80]}")
                    else:
                        print("✗ No defensive filter found for None signal_quality_score!")

                    # Look for inline scorer
                    if "inline" in content.lower() and "score" in content.lower():
                        print("✓ Found inline scorer logic")
                    else:
                        print("✗ No inline scorer found")

                    # Check for validation
                    if "validate" in content.lower() or "assert" in content.lower():
                        print("✓ Found validation logic")
                    else:
                        print("✗ No validation logic found")

            else:
                print(f"✗ Phase 7 source not found at {code_path}")

            # 3. Check signal_quality_scores table
            print("\n\n3. CHECKING SIGNAL_QUALITY_SCORES DATA")
            print("-" * 80)

            cur.execute(
                """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN signal_quality_score IS NULL THEN 1 ELSE 0 END) as null_count,
                       SUM(CASE WHEN signal_quality_score IS NOT NULL THEN 1 ELSE 0 END) as filled_count,
                       MIN(signal_quality_score) as min_score,
                       MAX(signal_quality_score) as max_score,
                       AVG(signal_quality_score) as avg_score
                FROM signal_quality_scores
                WHERE signal_date = CURRENT_DATE
                """
            )

            stats = cur.fetchone()
            if stats:
                total, null_count, filled_count, min_score, max_score, avg_score = stats
                print(f"Total scores today: {total}")
                print(f"  NULL values: {null_count} ({100*null_count/max(total,1):.1f}%)")
                print(f"  Filled values: {filled_count}")
                if filled_count:
                    print(f"  Min score: {min_score:.1f}")
                    print(f"  Max score: {max_score:.1f}")
                    print(f"  Avg score: {avg_score:.1f}")

            # 4. Check for NOEM specifically
            print("\n\n4. CHECKING NOEM SYMBOL")
            print("-" * 80)

            cur.execute(
                """
                SELECT symbol, COUNT(*) as count,
                       SUM(CASE WHEN signal_quality_score IS NULL THEN 1 ELSE 0 END) as null_scores
                FROM signal_quality_scores
                WHERE symbol = 'NOEM'
                GROUP BY symbol
                """
            )

            noem = cur.fetchone()
            if noem:
                symbol, count, null_scores = noem
                print(f"NOEM scores: {count} total, {null_scores} NULL ({100*null_scores/max(count,1):.1f}%)")
            else:
                print("NOEM has no signal quality scores!")

            # 5. Check recent buy_sell_daily for NOEM
            print("\n\n5. CHECKING BUY/SELL SIGNALS FOR NOEM")
            print("-" * 80)

            cur.execute(
                """
                SELECT symbol, signal_date, signal_type, ranking_score
                FROM buy_sell_daily
                WHERE symbol = 'NOEM'
                ORDER BY signal_date DESC
                LIMIT 5
                """
            )

            noem_signals = cur.fetchall()
            if noem_signals:
                print(f"Found {len(noem_signals)} recent NOEM signals:\n")
                for symbol, signal_date, signal_type, ranking_score in noem_signals:
                    print(f"  {signal_date} | {signal_type:6s} | Score: {ranking_score}")
            else:
                print("No NOEM buy/sell signals found!")

            # 6. Check Phase 7 execution for NOEM
            print("\n\n6. CHECKING RECENT ORCHESTRATOR RUNS FOR NOEM")
            print("-" * 80)

            cur.execute(
                """
                SELECT DISTINCT run_id, created_at
                FROM algo_audit_log
                WHERE action_type LIKE 'phase_7%'
                AND details->>'summary' ILIKE '%NOEM%'
                ORDER BY created_at DESC
                LIMIT 5
                """
            )

            runs_with_noem = cur.fetchall()
            if runs_with_noem:
                print(f"Found {len(runs_with_noem)} runs mentioning NOEM:\n")
                for run_id, created_at in runs_with_noem:
                    print(f"  {created_at} | {run_id}")
            else:
                print("No runs mentioning NOEM found!")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(investigate_phase7())
