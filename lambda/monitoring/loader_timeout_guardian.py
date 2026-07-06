#!/usr/bin/env python3
"""
CloudWatch Lambda: Monitor and kill loaders stuck in RUNNING state.

Runs every 5 minutes via EventBridge. Kills ECS tasks and updates DB
if a loader has been RUNNING for longer than allowed.

MAX DURATIONS (HARD LIMITS):
- Price loaders: 4 hours (yfinance can be slow)
- Technical/score loaders: 2 hours
- Other loaders: 1 hour
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
import psycopg2

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ecs = boto3.client("ecs")
cloudwatch = boto3.client("cloudwatch")

# Maximum allowed runtime before killing
MAX_RUNTIME_SECONDS = {
    "stock_prices_daily": 4 * 3600,  # 4 hours max
    "etf_price_daily": 4 * 3600,
    "technical_data_daily": 2 * 3600,  # 2 hours max
    "signal_quality_scores": 2 * 3600,
    "buy_sell_daily": 2 * 3600,
    # Default for all others
    "DEFAULT": 1 * 3600,  # 1 hour max
}


def get_max_runtime(loader_name: str) -> int:
    return MAX_RUNTIME_SECONDS.get(loader_name, MAX_RUNTIME_SECONDS["DEFAULT"])


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    """Monitor and kill indefinitely-running loaders."""
    try:
        # Validate database configuration
        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT", "5432")
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")
        db_name = os.getenv("DB_NAME")

        if not all([db_host, db_user, db_password, db_name]):
            raise ValueError("Missing required database configuration (host, user, password, database)")

        # Connect to database
        conn = psycopg2.connect(
            host=db_host,
            port=int(db_port),
            user=db_user,
            password=db_password,
            database=db_name,
        )

        with conn.cursor() as cur:
            # Find loaders in RUNNING state
            cur.execute("""
                SELECT table_name, execution_started
                FROM data_loader_status
                WHERE status = 'RUNNING' AND execution_started IS NOT NULL
            """)

            hung_loaders = []
            now = datetime.now(timezone.utc)

            for loader_name, started in cur.fetchall():
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)

                runtime_sec = (now - started).total_seconds()
                max_allowed = get_max_runtime(loader_name)

                if runtime_sec > max_allowed:
                    hung_loaders.append(
                        {
                            "name": loader_name,
                            "runtime_sec": runtime_sec,
                            "max_allowed": max_allowed,
                        }
                    )

            if hung_loaders:
                logger.warning(f"Found {len(hung_loaders)} indefinitely-running loaders:")
                for loader in hung_loaders:
                    logger.warning(
                        f"  {loader['name']}: running {loader['runtime_sec'] / 3600:.1f}h "
                        f"(max {loader['max_allowed'] / 3600:.1f}h)"
                    )

                    # Kill the ECS task
                    kill_loader_task(loader["name"])

                    # Mark as TIMEOUT in database
                    cur.execute(
                        """
                        UPDATE data_loader_status
                        SET status = 'TIMEOUT',
                            error_message = 'Killed by timeout guardian after ' ||
                                            ROUND(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - execution_started))/3600) || 'h',
                            execution_completed = CURRENT_TIMESTAMP
                        WHERE table_name = %s AND status = 'RUNNING'
                    """,
                        (loader["name"],),
                    )

                    # Alert via CloudWatch
                    cloudwatch.put_metric_data(
                        Namespace="AlgoLoaders",
                        MetricData=[
                            {
                                "MetricName": "LoaderTimeout",
                                "Value": 1,
                                "Unit": "Count",
                                "Dimensions": [{"Name": "LoaderName", "Value": loader["name"]}],
                            }
                        ],
                    )

            conn.commit()
            conn.close()

            return {
                "statusCode": 200,
                "body": f"Checked loaders. Found {len(hung_loaders)} hung (killed and logged)",
            }

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Guardian check failed: {e}", exc_info=True)
        return {"statusCode": 500, "body": str(e)}


def kill_loader_task(loader_name: str) -> bool:
    """Find and kill ECS task running this loader."""
    try:
        # List tasks in algo cluster
        response = ecs.list_tasks(cluster="algo-dev", desiredStatus="RUNNING")
        task_arns = response.get("taskArns")

        if not task_arns:
            logger.warning("No running tasks found for cluster algo-dev")
            return False

        # Try to match by task name/label - this is heuristic
        # In real deployment, tasks should have loader_name as label or environment variable
        for arn in task_arns:
            try:
                task_detail = ecs.describe_tasks(cluster="algo-dev", tasks=[arn])
                tasks = task_detail.get("tasks")

                if not tasks:
                    logger.warning(f"No task details returned for {arn}")
                    continue

                task = tasks[0]
                containers = task.get("containers")

                if not containers:
                    logger.debug(f"No containers found in task {arn.split('/')[-1]}")
                    continue

                # Check task definition or environment variables for loader_name
                # This depends on how tasks are launched
                container_env = containers[0].get("environment")

                if not container_env:
                    logger.debug(f"No environment variables in container for task {arn.split('/')[-1]}")
                    continue

                for env_var in container_env:
                    if env_var.get("name") == "LOADER_NAME" and env_var.get("value") == loader_name:
                        # Found it - stop the task
                        ecs.stop_task(
                            cluster="algo-dev",
                            task=arn,
                            reason=f"Killed by timeout guardian: {loader_name} exceeded max runtime",
                        )
                        logger.info(f"Stopped ECS task {arn.split('/')[-1]}")
                        return True
            except Exception as e:
                logger.warning(f"Could not check task {arn}: {e}")

        logger.warning(f"Could not find ECS task for {loader_name}")
        return False

    except Exception as e:
        raise RuntimeError(f"Operation failed: {e}") from e
