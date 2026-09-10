#!/usr/bin/env python3
"""Patrol logging - writes results to data_patrol_log table."""

import json
import logging
from decimal import Decimal
from typing import Any

import psycopg2

from .base import CheckResult

logger = logging.getLogger(__name__)


class PatrolLogger:
    """Log patrol results to data_patrol_log table."""

    def __init__(self, run_id: str):
        self.run_id = run_id

    def log_configuration(self, cur: Any, config: dict[str, Any]) -> None:
        """Log patrol configuration snapshot at start of run."""
        try:
            cur.execute(
                """
                INSERT INTO data_patrol_log
                  (patrol_run_id, check_name, severity, target_table, message, details)
                VALUES (%s, %s, %s, %s, %s, %s)
            """,
                (
                    self.run_id,
                    "configuration_audit",
                    "info",
                    "patrol_config",
                    "Patrol configuration snapshot",
                    json.dumps(config),
                ),
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Failed to log patrol configuration - health check data unavailable: {e}") from e

    def log_results(self, cur: Any, results: list[CheckResult]) -> None:
        """Log all check results to database.

        Added 2026-09-09 (goal session: "is our XBRL/tie-out validation actually working").
        `status` existed as a column (added out-of-band, itself an undocumented-drift instance
        fixed in schema.sql alongside this) but no code ever wrote to it - it was 100% NULL
        across all 7,208 live rows, oldest unresolved back to 2026-06-27, with the same ~77
        (check_name, target_table) combos re-logged on effectively every run since (e.g.
        revenue_yoy_magnitude_jump/total_assets_yoy_magnitude_jump: 55 occurrences each since
        2026-09-07). Findings were being detected every run but were functionally invisible -
        indistinguishable from "not checked" to a human scanning the log.

        This checker's granularity is one row per (check_name, target_table) per run, not one
        row per symbol/fiscal_year - unlike xbrl_concept_coverage_scan.py's stable per-concept
        `--dismiss` list, a manual dismiss-list is the wrong shape here (the underlying
        symbol/fiscal_year population drifts as new filings land and extraction bugs get fixed,
        so a static allowlist would silently go stale or wrong). Instead: superseding-on-reinsert
        - when a (check_name, target_table) fires again, the prior 'open' row(s) for that same
        key are marked 'resolved' before the new one is inserted as 'open'. This collapses the
        history to "what's true as of the latest run" per check/table, so `status = 'open'`
        always reflects current state instead of an ever-growing unfiltered feed. A combo that
        stops firing entirely (the rarer case - none currently in the live population) simply
        keeps its last 'open' row, which a backlog report can flag via staleness of created_at
        rather than requiring this write path to know every check's full historical registry.
        """
        if not results:
            return
        try:
            keys = {(r.check_name, r.target_table) for r in results}
            if keys:
                cur.executemany(
                    """
                    UPDATE data_patrol_log
                    SET status = 'resolved'
                    WHERE status = 'open' AND check_name = %s AND target_table = %s
                    """,
                    list(keys),
                )
            cur.executemany(
                """
                INSERT INTO data_patrol_log
                  (patrol_run_id, check_name, severity, target_table, message, details, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'open')
            """,
                [
                    (
                        self.run_id,
                        result.check_name,
                        result.severity,
                        result.target_table,
                        result.message,
                        (json.dumps(result.details, default=str) if result.details else None),
                    )
                    for result in results
                ],
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Failed to log patrol results - health check results not recorded: {e}") from e

    def log_performance(self, cur: Any, elapsed_seconds: float, status: str) -> None:
        """Log patrol execution performance metrics."""
        try:
            cur.execute(
                """
                INSERT INTO data_patrol_log
                  (patrol_run_id, check_name, severity, target_table, message, details)
                VALUES (%s, %s, %s, %s, %s, %s)
            """,
                (
                    self.run_id,
                    "patrol_performance",
                    "info",
                    "patrol_metrics",
                    f"Patrol execution time: {elapsed_seconds:.1f}s",
                    json.dumps(
                        {
                            "seconds": round(elapsed_seconds, 2),
                            "status": "SLOW" if elapsed_seconds > 120 else "OK",
                        }
                    ),
                ),
            )
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"Failed to log patrol performance metrics - execution metrics lost: {e}") from e
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Failed to log patrol performance - health check metrics not recorded: {e}") from e

    def update_completion_status(self, ready: bool, elapsed_seconds: float | None = None) -> None:
        import os
        import time

        import boto3

        try:
            dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
            state_table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
            state_table = dynamodb.Table(state_table_name)

            state_table.update_item(
                Key={"key": "patrol_trigger_log"},
                UpdateExpression="SET last_success_at = :now, #ts = :ts, last_completion_status = :status",
                ExpressionAttributeNames={"#ts": "ttl"},
                ExpressionAttributeValues={
                    ":now": Decimal(str(time.time())),
                    ":ts": int(time.time()) + 3600,  # 1-hour TTL
                    ":status": "ready" if ready else "completed_with_findings",
                },
            )
            status = "ready" if ready else "completed_with_findings"
            logger.info(f"[PATROL] [OK] Completed successfully. Updated DynamoDB (status={status})")
        except Exception as e:
            logger.critical(
                f"[PATROL] FAILED to update DynamoDB completion status: {type(e).__name__}: {e}. "
                f"Orchestrator cannot track patrol completion - monitoring is blind to patrol state."
            )
