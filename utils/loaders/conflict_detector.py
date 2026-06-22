#!/usr/bin/env python3
"""Loader Conflict Detection — Prevents concurrent loader conflicts during intraday updates.

Monitors:
- Lock timeouts in data_loader_status table
- Concurrent runs of same loader (detects conflicts)
- Long-running loaders that might block subsequent pipelines
"""

import logging
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class LoaderConflictDetector:
    """Detect and alert on loader conflicts during concurrent pipeline runs."""

    def __init__(self):
        self.table_name = "data_loader_status"

    def check_concurrent_loaders(self) -> dict[str, Any]:
        """Check for concurrent loader runs that might conflict.

        Returns:
            {
                'conflicts_detected': bool,
                'concurrent_loaders': [
                    {
                        'table_name': 'swing_trader_scores',
                        'start_time': datetime,
                        'duration_sec': 120,
                        'status': 'RUNNING'
                    },
                    ...
                ],
                'stuck_loaders': [
                    {
                        'table_name': 'price_daily',
                        'status': 'RUNNING',
                        'duration_sec': 3600,  # Running for 1 hour
                        'started_at': datetime
                    },
                    ...
                ]
            }
        """
        try:
            with DatabaseContext("read") as cur:
                # Check 1: Find all currently RUNNING loaders (based on execution_started/completed)
                cur.execute("""
                    SELECT
                        table_name,
                        status,
                        execution_started,
                        EXTRACT(EPOCH FROM (NOW() - execution_started)) as duration_sec
                    FROM data_loader_status
                    WHERE status = 'RUNNING'
                    AND execution_started IS NOT NULL
                    ORDER BY execution_started ASC
                """)

                running_loaders = []
                stuck_loaders = []

                for row in cur.fetchall():
                    table_name, status, execution_started, duration_sec = row
                    duration_sec = float(duration_sec) if duration_sec else 0

                    loader_info = {
                        "table_name": table_name,
                        "status": status,
                        "duration_sec": round(duration_sec, 1),
                        "execution_started": (execution_started.isoformat() if execution_started else None),
                    }

                    running_loaders.append(loader_info)

                    # Check for stuck loaders (running >30 min)
                    if duration_sec > 1800:  # 30 minutes
                        stuck_loaders.append(
                            {
                                **loader_info,
                                "timeout_threshold_sec": 1800,
                                "is_overdue": True,
                            }
                        )

                # Check 2: Detect concurrent runs of SAME table (shouldn't happen)
                table_counts: dict[str, int] = {}
                for loader in running_loaders:
                    name = loader["table_name"]
                    table_counts[name] = table_counts.get(name, 0) + 1

                conflicts = [name for name, count in table_counts.items() if count > 1]

                has_conflicts = len(conflicts) > 0 or len(stuck_loaders) > 0

                result = {
                    "conflicts_detected": has_conflicts,
                    "concurrent_loaders": running_loaders,
                    "stuck_loaders": stuck_loaders,
                    "duplicate_loader_runs": conflicts,
                }

                if has_conflicts:
                    logger.warning(
                        "[CONFLICT] Detected loader conflicts: "
                        f"{len(running_loaders)} running, "
                        f"{len(stuck_loaders)} stuck, "
                        f"{len(conflicts)} duplicates"
                    )

                return result

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"Failed to check loader conflicts: {e}", exc_info=True)
            return {
                "conflicts_detected": False,
                "concurrent_loaders": [],
                "stuck_loaders": [],
                "error": str(e),
            }

    def check_intraday_pipeline_readiness(self) -> dict[str, Any]:
        """Check if intraday pipelines can safely run without conflicts.

        Specifically validates the afternoon (12:50 PM) and pre-close (2:50 PM) windows.

        Returns:
            {
                'ready_for_afternoon_update': bool,
                'ready_for_preclose_update': bool,
                'morning_pipeline_done': bool,
                'morning_completion_time': datetime or None,
                'last_morning_status': 'COMPLETED' | 'RUNNING' | 'FAILED' | None,
                'recommendations': [str]
            }
        """
        try:
            with DatabaseContext("read") as cur:
                # Check morning pipeline status
                cur.execute("""
                    SELECT status, last_updated
                    FROM data_loader_status
                    WHERE table_name = 'swing_trader_scores'
                    ORDER BY last_updated DESC
                    LIMIT 1
                """)

                last_morning = cur.fetchone()
                morning_status = last_morning[0] if last_morning else None
                morning_time = last_morning[1] if last_morning else None

                recommendations = []

                # Check if morning pipeline completed
                morning_done = morning_status == "COMPLETED"

                if not morning_done and morning_status == "RUNNING":
                    recommendations.append(
                        "Morning pipeline still running - wait for completion before afternoon update"
                    )

                if morning_status == "FAILED":
                    recommendations.append("Morning pipeline failed - afternoon update may use stale scores")

                # Check for any RUNNING loaders that would block intraday updates
                cur.execute("""
                    SELECT COUNT(*) FROM data_loader_status
                    WHERE status = 'RUNNING'
                    AND table_name NOT IN ('swing_trader_scores', 'technical_data_daily')
                """)

                other_running = cur.fetchone()[0]

                if other_running > 0:
                    recommendations.append(
                        f"{other_running} other loaders running - may impact RDS connections for intraday updates"
                    )

                return {
                    "ready_for_afternoon_update": morning_done and other_running == 0,
                    "ready_for_preclose_update": morning_done and other_running == 0,
                    "morning_pipeline_done": morning_done,
                    "morning_completion_time": (morning_time.isoformat() if morning_time else None),
                    "last_morning_status": morning_status,
                    "other_loaders_running": other_running,
                    "recommendations": recommendations,
                }

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Failed to check intraday readiness: {e}", exc_info=True)
            return {
                "ready_for_afternoon_update": False,
                "ready_for_preclose_update": False,
                "error": str(e),
            }

    def log_conflict_status(self):
        """Log current conflict status (for debugging/monitoring)."""
        conflicts = self.check_concurrent_loaders()

        if conflicts["conflicts_detected"]:
            logger.warning(
                f"[LOADER-STATUS] {len(conflicts['concurrent_loaders'])} loaders running, "
                f"{len(conflicts['stuck_loaders'])} stuck, "
                f"{len(conflicts['duplicate_loader_runs'])} duplicates: {conflicts['duplicate_loader_runs']}"
            )
        else:
            logger.debug(f"[LOADER-STATUS] {len(conflicts['concurrent_loaders'])} loaders running (OK)")

        intraday = self.check_intraday_pipeline_readiness()
        if not intraday.get("ready_for_afternoon_update"):
            logger.warning(f"[INTRADAY-READINESS] Not ready: {intraday.get('recommendations')}")
