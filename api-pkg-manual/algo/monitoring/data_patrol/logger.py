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
        """Log all check results to database."""
        if results:
            try:
                cur.executemany(
                    """
                    INSERT INTO data_patrol_log
                      (patrol_run_id, check_name, severity, target_table, message, details)
                    VALUES (%s, %s, %s, %s, %s, %s)
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
            raise RuntimeError(f"Failed to log patrol performance metrics — execution metrics lost: {e}") from e
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Failed to log patrol performance — health check metrics not recorded: {e}") from e

    def update_completion_status(self, ready: bool, elapsed_seconds: float | None = None) -> None:
        """Update DynamoDB with patrol completion status."""
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
                f"Orchestrator cannot track patrol completion — monitoring is blind to patrol state."
            )
