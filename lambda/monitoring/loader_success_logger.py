#!/usr/bin/env python3
"""Log successful loader execution to data_loader_runs table for visibility."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import psycopg2

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    """Log successful loader execution to database."""
    try:
        loader_name = event.get("loader_name", "unknown")
        started_at = event.get("started_at")
        execution_time = event.get("execution_time_seconds", 0)

        # Connect to database
        db_host = os.getenv("DB_HOST", "localhost")
        db_user = os.getenv("DB_USER", "stocks")
        db_password = os.getenv("DB_PASSWORD", "")
        db_name = os.getenv("DB_NAME", "stocks")

        conn = psycopg2.connect(host=db_host, user=db_user, password=db_password, database=db_name)
        cur = conn.cursor()

        # Log execution
        if started_at:
            cur.execute(
                """
                INSERT INTO data_loader_runs
                (loader_name, status, started_at, completed_at, duration_seconds)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (loader_name, "success", started_at, datetime.now(timezone.utc), execution_time),
            )
        else:
            cur.execute(
                """
                INSERT INTO data_loader_runs
                (loader_name, status, completed_at, duration_seconds)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (loader_name, "success", datetime.now(timezone.utc), execution_time),
            )

        conn.commit()
        cur.close()
        conn.close()

        logger.info(f"Logged successful execution: {loader_name} ({execution_time:.1f}s)")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": f"Logged {loader_name} execution",
                    "loader_name": loader_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error logging loader success: {e}", exc_info=True)
        # Don't fail the pipeline if logging fails - just log the error
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
