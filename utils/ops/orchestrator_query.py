#!/usr/bin/env python3
"""
Query orchestrator execution history.

Provides diagnostic functions to view previous orchestrator runs and identify patterns.
"""

import json
import logging
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


def get_recent_runs(days: int = 7, limit: int | None = None) -> list[dict[str, Any]]:
    """Get recent orchestrator runs.

    Args:
        days: How many days back to look (default 7)
        limit: Max runs to return (default all)

    Returns: List of execution logs, most recent first
    """
    try:
        with DatabaseContext("read") as cur:
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
                    "run_id": row[0],
                    "run_date": row[1].isoformat() if row[1] is not None else None,
                    "started_at": row[2].isoformat() if row[2] is not None else None,
                    "completed_at": row[3].isoformat() if row[3] is not None else None,
                    "status": row[4],
                    "phases_completed": row[5],
                    "phases_halted": row[6],
                    "phases_errored": row[7],
                    "summary": row[8],
                }
                for row in rows
            ]
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Error querying recent runs: {e}")
        return []


def get_run_details(run_id: str) -> dict[str, Any] | None:
    """Get full details of a specific run, including phase-by-phase results.

    Args:
        run_id: The RUN-* ID to fetch

    Returns: Full execution record with phase details, or None if not found
    """
    try:
        with DatabaseContext("read") as cur:
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

            phase_results: list[Any] = []
            try:
                phase_results = json.loads(row[5]) if row[5] is not None else []
            except json.JSONDecodeError:
                logger.warning(f"Could not parse phase_results for {run_id}")

            return {
                "run_id": row[0],
                "run_date": row[1].isoformat() if row[1] is not None else None,
                "started_at": row[2].isoformat() if row[2] is not None else None,
                "completed_at": row[3].isoformat() if row[3] is not None else None,
                "status": row[4],
                "phase_results": phase_results,
                "summary": row[6],
                "halt_reason": row[7],
                "phases_completed": row[8],
                "phases_halted": row[9],
                "phases_errored": row[10],
            }
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Operation failed: {e}") from e


def get_failed_runs(days: int = 30) -> list[dict[str, Any]]:
    """Get all failed/halted runs in the past N days.

    Args:
        days: How many days back to look (default 30)

    Returns: List of failed/halted runs, most recent first
    """
    try:
        with DatabaseContext("read") as cur:
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
                    "run_id": row[0],
                    "run_date": row[1].isoformat() if row[1] else None,
                    "started_at": row[2].isoformat() if row[2] else None,
                    "status": row[3],
                    "summary": row[4],
                    "halt_reason": row[5],
                }
                for row in rows
            ]
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Error querying failed runs: {e}")
        return []


def get_halt_patterns(days: int = 30) -> list[dict[str, Any]]:
    """Analyze halt patterns — which phases halt most often and why.

    Args:
        days: How many days back to analyze (default 30)

    Returns: Summary of halt patterns
    """
    try:
        with DatabaseContext("read") as cur:
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

                patterns.append(
                    {
                        "phase": row[0],
                        "total_halts": row[1],
                        "common_reasons": reasons,
                    }
                )

            return patterns
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Error analyzing halt patterns: {e}")
        return []


def get_success_rate(days: int = 7) -> dict[str, Any]:
    """Get success/fail statistics for the past N days.

    Args:
        days: How many days back to analyze

    Returns: Dictionary with success/fail counts and rates
    """
    try:
        with DatabaseContext("read") as cur:
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

            stats = dict(rows)
            total = sum(stats.values())

            if total == 0:
                return {
                    "total_runs": 0,
                    "by_status": {},
                    "success_rate": "N/A",
                    "halt_rate": "N/A",
                    "error_rate": "N/A",
                    "period_days": days,
                }

            for status_key in ['success', 'halted', 'error']:
                if status_key not in stats:
                    raise ValueError(f"Missing '{status_key}' count in orchestrator stats — data incomplete")

            return {
                "total_runs": total,
                "by_status": stats,
                "success_rate": f"{(stats['success'] / total * 100):.1f}%",
                "halt_rate": f"{(stats['halted'] / total * 100):.1f}%",
                "error_rate": f"{(stats['error'] / total * 100):.1f}%",
                "period_days": days,
            }
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Error computing success rate: {e}")
        raise


def print_recent_runs(days: int = 7, limit: int | None = 10) -> None:
    """Log recent orchestrator runs."""
    runs = get_recent_runs(days, limit)
    if not runs:
        logger.info(f"No orchestrator runs found in the past {days} days")
        return

    logger.info(f"Recent Orchestrator Runs (past {days} days):")
    logger.info(f"{'Run ID':<20} {'Date':<12} {'Status':<10} {'OK/Halt/Err':<12} {'Summary':<50}")
    logger.info("-" * 110)

    for run in runs:
        ok = run.get("phases_completed")
        halt = run.get("phases_halted")
        err = run.get("phases_errored")
        if ok is None or halt is None or err is None:
            logger.warning(
                f"Orchestrator run {run.get('run_id')} has missing phase counts: "
                f"completed={ok}, halted={halt}, errored={err}. Skipping display."
            )
            continue
        summary = (run.get("summary") or "")[:45]

        logger.info(
            f"{run['run_id']:<20} {run['run_date']:<12} {run['status']:<10} {ok}/{halt}/{err:<10} {summary:<50}"
        )


def print_failed_runs(days: int = 30) -> None:
    """Log failed/halted runs."""
    runs = get_failed_runs(days)
    if not runs:
        logger.info(f"No failed/halted runs found in the past {days} days")
        return

    logger.info(f"Failed/Halted Runs (past {days} days):")
    logger.info(f"{'Run ID':<20} {'Date':<12} {'Status':<10} {'Reason':<60}")
    logger.info("-" * 110)

    for run in runs:
        reason = (run["halt_reason"] or run["summary"] or "")[:55]
        logger.info(f"{run['run_id']:<20} {run['run_date']:<12} {run['status']:<10} {reason:<60}")


def print_halt_patterns(days: int = 30) -> None:
    """Log phase halt patterns."""
    patterns = get_halt_patterns(days)
    if not patterns:
        logger.info(f"No halt patterns found in the past {days} days")
        return

    logger.info(f"Halt Patterns (past {days} days):")
    for pattern in patterns:
        logger.info(f"Phase {pattern['phase']:>2s}: halted {pattern['total_halts']} times")
        for reason, _count in pattern["common_reasons"].items():
            logger.info(f"  • {reason[:60]}")
        logger.info("")


def print_success_rate(days: int = 7) -> None:
    """Log success rate stats."""
    stats = get_success_rate(days)
    if not stats:
        logger.info("No execution data available")
        return

    logger.info(f"Execution Statistics (past {stats['period_days']} days):")
    logger.info(f"  Total runs:    {stats['total_runs']}")
    logger.info(f"  Success rate:  {stats['success_rate']}")
    logger.info(f"  Halt rate:     {stats['halt_rate']}")
    logger.info(f"  Error rate:    {stats['error_rate']}")
    logger.info("  By status:")
    for status, count in stats["by_status"].items():
        logger.info(f"    {status:10s}: {count}")


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

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
                    logger.info(json.dumps(details, indent=2))
                else:
                    logger.info(f"Run {sys.argv[2]} not found")
            else:
                logger.info("Usage: python orchestrator_query.py details <RUN_ID>")
        else:
            logger.info("Usage:")
            logger.info("  python orchestrator_query.py recent [days]")
            logger.info("  python orchestrator_query.py failed [days]")
            logger.info("  python orchestrator_query.py patterns [days]")
            logger.info("  python orchestrator_query.py stats [days]")
            logger.info("  python orchestrator_query.py details <RUN_ID>")
    else:
        print_recent_runs()
        print_success_rate()
