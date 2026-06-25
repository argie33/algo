#!/usr/bin/env python3
"""Track and analyze loader failure trends to detect chronic issues.

Provides:
- Record loader run results (success/failure)
- Calculate rolling failure rates (7-day, 30-day)
- Alert if failure_rate_7day > 50% (chronic failures)
- Query failure trends for dashboarding
"""

import logging
from datetime import date, timedelta
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


def record_loader_run(loader_name: str, run_date: date, success: bool, error_message: str | None = None) -> None:
    """Record a loader run result (success or failure).

    Args:
        loader_name: Name of the loader (e.g., 'company_profile', 'analyst_sentiment')
        run_date: Date of the run
        success: True if loader succeeded, False if failed
        error_message: Optional error message if failed
    """
    try:
        with DatabaseContext("write") as cur:
            # Check if record for today exists
            cur.execute(
                """
                SELECT id, success_count, failure_count
                FROM loader_failure_trend
                WHERE loader_name = %s AND tracking_date = %s
            """,
                (loader_name, run_date),
            )

            existing = cur.fetchone()

            if existing:
                existing_id, success_count, failure_count = existing
                # Update counts
                new_success_count = success_count + (1 if success else 0)
                new_failure_count = failure_count + (0 if success else 1)

                cur.execute(
                    """
                    UPDATE loader_failure_trend
                    SET success_count = %s,
                        failure_count = %s,
                        last_error_message = %s
                    WHERE id = %s
                """,
                    (new_success_count, new_failure_count, error_message, existing_id),
                )
            else:
                # Create new record
                cur.execute(
                    """
                    INSERT INTO loader_failure_trend
                    (loader_name, tracking_date, success_count, failure_count, last_error_message)
                    VALUES (%s, %s, %s, %s, %s)
                """,
                    (
                        loader_name,
                        run_date,
                        1 if success else 0,
                        0 if success else 1,
                        error_message,
                    ),
                )

            logger.debug(
                f"[FAILURE_TRACKING] Recorded {loader_name} run on {run_date}: {'SUCCESS' if success else 'FAILURE'}"
            )

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.warning(f"[FAILURE_TRACKING] Could not record loader run: {e}")


def calculate_failure_trends(loader_name: str) -> dict[str, Any] | None:
    """Calculate rolling failure rates for a loader (7-day and 30-day).

    Args:
        loader_name: Name of the loader

    Returns:
        Dict with keys: failure_rate_7day, failure_rate_30day, total_runs_7day, failing_days_7day
        Or None if no data available
    """
    try:
        with DatabaseContext("read") as cur:
            today = date.today()

            # Query last 7 days
            cur.execute(
                """
                SELECT
                    COUNT(*) as total_days,
                    SUM(failure_count) as total_failures,
                    SUM(success_count + failure_count) as total_runs
                FROM loader_failure_trend
                WHERE loader_name = %s
                  AND tracking_date >= %s
                  AND tracking_date <= %s
            """,
                (loader_name, today - timedelta(days=7), today),
            )

            row_7d = cur.fetchone()
            failure_rate_7d = 0.0
            failing_days_7d = 0
            if row_7d and row_7d[2]:  # total_runs
                total_failures = row_7d[1] if row_7d[1] is not None else 0
                total_runs = row_7d[2]
                failure_rate_7d = round((total_failures / total_runs) * 100, 2)
                failing_days_7d = row_7d[0] if row_7d[0] is not None else 0

            # Query last 30 days
            cur.execute(
                """
                SELECT
                    COUNT(*) as total_days,
                    SUM(failure_count) as total_failures,
                    SUM(success_count + failure_count) as total_runs
                FROM loader_failure_trend
                WHERE loader_name = %s
                  AND tracking_date >= %s
                  AND tracking_date <= %s
            """,
                (loader_name, today - timedelta(days=30), today),
            )

            row_30d = cur.fetchone()
            failure_rate_30d = 0.0
            if row_30d and row_30d[2]:  # total_runs
                total_failures = row_30d[1] if row_30d[1] is not None else 0
                total_runs = row_30d[2]
                failure_rate_30d = round((total_failures / total_runs) * 100, 2)

            return {
                "loader_name": loader_name,
                "failure_rate_7day": failure_rate_7d,
                "failure_rate_30day": failure_rate_30d,
                "failing_days_7day": failing_days_7d,
                "total_runs_7day": row_7d[2] if row_7d else 0,
            }

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Operation failed: {e}") from e


def check_chronic_failures(
    threshold_pct: float = 50.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Check all loaders for chronic failures (failure_rate_7day > threshold).

    Args:
        threshold_pct: Failure rate threshold (default 50%)

    Returns:
        Tuple of (chronic_loaders, all_trends)
        - chronic_loaders: List of loader names with high 7-day failure rates
        - all_trends: Dict of all loader failure trends
    """
    try:
        with DatabaseContext("read") as cur:
            # Get unique loaders from last 7 days
            cur.execute(
                """
                SELECT DISTINCT loader_name
                FROM loader_failure_trend
                WHERE tracking_date >= %s
                ORDER BY loader_name
            """,
                (date.today() - timedelta(days=7),),
            )

            loaders = [row[0] for row in cur.fetchall()]

        chronic_loaders = []
        all_trends = {}

        for loader_name in loaders:
            trends = calculate_failure_trends(loader_name)
            if trends:
                all_trends[loader_name] = trends
                if trends["failure_rate_7day"] > threshold_pct:
                    chronic_loaders.append(
                        {
                            "loader_name": loader_name,
                            "failure_rate": trends["failure_rate_7day"],
                            "failing_days": trends["failing_days_7day"],
                            "total_runs": trends["total_runs_7day"],
                        }
                    )

        # Sort by failure rate
        chronic_loaders.sort(key=lambda x: x["failure_rate"], reverse=True)

        return chronic_loaders, all_trends

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.warning(f"[FAILURE_TRACKING] Could not check chronic failures: {e}")
        return [], {}


def get_failure_alert_summary() -> str:
    """Generate a summary of loader failure trends for alerting.

    Returns: Formatted string summarizing chronic failures, or empty string if all healthy
    """
    chronic, _ = check_chronic_failures()

    if not chronic:
        return ""

    summary_lines = ["⚠️  CHRONIC LOADER FAILURES DETECTED (7-day window):"]
    for item in chronic:
        summary_lines.append(
            f"  • {item['loader_name']}: {item['failure_rate']:.0f}% failure rate "
            f"({item['failing_days']}/{item['total_runs']} runs failed)"
        )

    summary_lines.append(f"\nTotal: {len(chronic)} loader(s) above 50% failure threshold")
    return "\n".join(summary_lines)
