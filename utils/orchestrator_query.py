#!/usr/bin/env python3
"""
Query orchestrator execution history.

Provides diagnostic functions to view previous orchestrator runs and identify patterns.
"""

import json
import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any, Optional
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)


def get_recent_runs(days: int = 7, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get recent orchestrator runs.

    Args:
        days: How many days back to look (default 7)
        limit: Max runs to return (default all)

    Returns: List of execution logs, most recent first
    """
    try:
        with DatabaseContext('read') as cur:
            query = """
                SELECT run_id, run_date, started_at, completed_at, overall_status,
                       phases_completed, phases_halted, phases_errored, summary
                FROM orchestrator_execution_log
                WHERE run_date >= CURRENT_DATE - %s
                ORDER BY started_at DESC
            """
            params = [days]

            if limit:
                query += f" LIMIT {limit}"

            cur.execute(query, params)
            rows = cur.fetchall()

            return [
                {
                    'run_id': row[0],
                    'run_date': row[1].isoformat() if row[1] else None,
                    'started_at': row[2].isoformat() if row[2] else None,
                    'completed_at': row[3].isoformat() if row[3] else None,
                    'status': row[4],
                    'phases_completed': row[5],
                    'phases_halted': row[6],
                    'phases_errored': row[7],
                    'summary': row[8],
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error querying recent runs: {e}")
        return []


def get_run_details(run_id: str) -> Optional[Dict[str, Any]]:
    """Get full details of a specific run, including phase-by-phase results.

    Args:
        run_id: The RUN-* ID to fetch

    Returns: Full execution record with phase details, or None if not found
    """
    try:
        with DatabaseContext('read') as cur:
            cur.execute(
                """
                SELECT run_id, run_date, started_at, completed_at, overall_status,
                       phase_results, summary, halt_reason, phases_completed,
                       phases_halted, phases_errored
                FROM orchestrator_execution_log
                WHERE run_id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            phase_results = []
            try:
                phase_results = json.loads(row[5]) if row[5] else []
            except json.JSONDecodeError:
                logger.warning(f"Could not parse phase_results for {run_id}")

            return {
                'run_id': row[0],
                'run_date': row[1].isoformat() if row[1] else None,
                'started_at': row[2].isoformat() if row[2] else None,
                'completed_at': row[3].isoformat() if row[3] else None,
                'status': row[4],
                'phase_results': phase_results,
                'summary': row[6],
                'halt_reason': row[7],
                'phases_completed': row[8],
                'phases_halted': row[9],
                'phases_errored': row[10],
            }
    except Exception as e:
        logger.error(f"Error querying run {run_id}: {e}")
        return None


def get_failed_runs(days: int = 30) -> List[Dict[str, Any]]:
    """Get all failed/halted runs in the past N days.

    Args:
        days: How many days back to look (default 30)

    Returns: List of failed/halted runs, most recent first
    """
    try:
        with DatabaseContext('read') as cur:
            cur.execute(
                """
                SELECT run_id, run_date, started_at, overall_status, summary, halt_reason
                FROM orchestrator_execution_log
                WHERE run_date >= CURRENT_DATE - %s
                  AND overall_status IN ('halted', 'error')
                ORDER BY started_at DESC
                """,
                (days,),
            )
            rows = cur.fetchall()

            return [
                {
                    'run_id': row[0],
                    'run_date': row[1].isoformat() if row[1] else None,
                    'started_at': row[2].isoformat() if row[2] else None,
                    'status': row[3],
                    'summary': row[4],
                    'halt_reason': row[5],
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error querying failed runs: {e}")
        return []


def get_halt_patterns(days: int = 30) -> List[Dict[str, Any]]:
    """Analyze halt patterns — which phases halt most often and why.

    Args:
        days: How many days back to analyze (default 30)

    Returns: Summary of halt patterns
    """
    try:
        with DatabaseContext('read') as cur:
            # Find which phases appear most often in halt patterns
            cur.execute(
                """
                SELECT
                    phase_results->>'name' as phase_name,
                    COUNT(*) as halt_count,
                    json_object_agg(DISTINCT phase_results->>'summary', COUNT(*))::text as reasons
                FROM orchestrator_execution_log,
                     jsonb_array_elements(phase_results) as phase_results
                WHERE run_date >= CURRENT_DATE - %s
                  AND phase_results->>'status' = 'halt'
                GROUP BY phase_results->>'name'
                ORDER BY halt_count DESC
                """,
                (days,),
            )
            rows = cur.fetchall()

            patterns = []
            for row in rows:
                try:
                    reasons = json.loads(row[2]) if row[2] else {}
                except json.JSONDecodeError:
                    reasons = {}

                patterns.append({
                    'phase': row[0],
                    'total_halts': row[1],
                    'common_reasons': reasons,
                })

            return patterns
    except Exception as e:
        logger.error(f"Error analyzing halt patterns: {e}")
        return []


def get_success_rate(days: int = 7) -> Dict[str, Any]:
    """Get success/fail statistics for the past N days.

    Args:
        days: How many days back to analyze

    Returns: Dictionary with success/fail counts and rates
    """
    try:
        with DatabaseContext('read') as cur:
            cur.execute(
                """
                SELECT
                    overall_status,
                    COUNT(*) as count
                FROM orchestrator_execution_log
                WHERE run_date >= CURRENT_DATE - %s
                GROUP BY overall_status
                ORDER BY count DESC
                """,
                (days,),
            )
            rows = cur.fetchall()

            stats = {status: count for status, count in rows}
            total = sum(stats.values())

            return {
                'total_runs': total,
                'by_status': stats,
                'success_rate': f"{(stats.get('success', 0) / total * 100):.1f}%" if total > 0 else "N/A",
                'halt_rate': f"{(stats.get('halted', 0) / total * 100):.1f}%" if total > 0 else "N/A",
                'error_rate': f"{(stats.get('error', 0) / total * 100):.1f}%" if total > 0 else "N/A",
                'period_days': days,
            }
    except Exception as e:
        logger.error(f"Error computing success rate: {e}")
        return {}


def print_recent_runs(days: int = 7, limit: Optional[int] = 10) -> None:
    """Pretty-print recent orchestrator runs."""
    runs = get_recent_runs(days, limit)
    if not runs:
        print(f"No orchestrator runs found in the past {days} days")
        return

    print(f"\nRecent Orchestrator Runs (past {days} days):\n")
    print(f"{'Run ID':<20} {'Date':<12} {'Status':<10} {'OK/Halt/Err':<12} {'Summary':<50}")
    print("-" * 110)

    for run in runs:
        ok = run['phases_completed'] or 0
        halt = run['phases_halted'] or 0
        err = run['phases_errored'] or 0
        summary = (run['summary'] or '')[:45]

        print(
            f"{run['run_id']:<20} {run['run_date']:<12} {run['status']:<10} "
            f"{ok}/{halt}/{err:<10} {summary:<50}"
        )


def print_failed_runs(days: int = 30) -> None:
    """Pretty-print failed/halted runs."""
    runs = get_failed_runs(days)
    if not runs:
        print(f"No failed/halted runs found in the past {days} days")
        return

    print(f"\nFailed/Halted Runs (past {days} days):\n")
    print(f"{'Run ID':<20} {'Date':<12} {'Status':<10} {'Reason':<60}")
    print("-" * 110)

    for run in runs:
        reason = (run['halt_reason'] or run['summary'] or '')[:55]
        print(
            f"{run['run_id']:<20} {run['run_date']:<12} {run['status']:<10} {reason:<60}"
        )


def print_halt_patterns(days: int = 30) -> None:
    """Pretty-print phase halt patterns."""
    patterns = get_halt_patterns(days)
    if not patterns:
        print(f"No halt patterns found in the past {days} days")
        return

    print(f"\nHalt Patterns (past {days} days):\n")
    for pattern in patterns:
        print(f"Phase {pattern['phase']:>2s}: halted {pattern['total_halts']} times")
        for reason, count in pattern['common_reasons'].items():
            print(f"  • {reason[:60]}")
        print()


def print_success_rate(days: int = 7) -> None:
    """Pretty-print success rate stats."""
    stats = get_success_rate(days)
    if not stats:
        print("No execution data available")
        return

    print(f"\nExecution Statistics (past {stats['period_days']} days):\n")
    print(f"  Total runs:    {stats['total_runs']}")
    print(f"  Success rate:  {stats['success_rate']}")
    print(f"  Halt rate:     {stats['halt_rate']}")
    print(f"  Error rate:    {stats['error_rate']}")
    print(f"\n  By status:")
    for status, count in stats['by_status'].items():
        print(f"    {status:10s}: {count}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "recent":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
            print_recent_runs(days)
        elif sys.argv[1] == "failed":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            print_failed_runs(days)
        elif sys.argv[1] == "patterns":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            print_halt_patterns(days)
        elif sys.argv[1] == "stats":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
            print_success_rate(days)
        elif sys.argv[1] == "details":
            if len(sys.argv) > 2:
                details = get_run_details(sys.argv[2])
                if details:
                    print(json.dumps(details, indent=2))
                else:
                    print(f"Run {sys.argv[2]} not found")
            else:
                print("Usage: python orchestrator_query.py details <RUN_ID>")
        else:
            print("Usage:")
            print("  python orchestrator_query.py recent [days]")
            print("  python orchestrator_query.py failed [days]")
            print("  python orchestrator_query.py patterns [days]")
            print("  python orchestrator_query.py stats [days]")
            print("  python orchestrator_query.py details <RUN_ID>")
    else:
        print_recent_runs()
        print_success_rate()
