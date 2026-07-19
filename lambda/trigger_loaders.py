"""Lambda to trigger data loaders on ECS.

When dashboard or orchestrator detects stale data, invokes this Lambda to kick off
a loader task on ECS (which has proper RDS credentials).

Response format must have statusCode + body (JSON-encoded) for compatibility with:
  - phase1_failsafe_retry.py (expects status_code 200 + body with tasks array)
  - run-loader.yml workflow (expects status_code + body with message)
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ecs = boto3.client("ecs", region_name=os.getenv("AWS_REGION", "us-east-1"))


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle request to trigger loader on ECS.

    Returns:
        {"statusCode": 200|500, "body": json_string}
        where body is {"statusCode", "message", "tasks", "timestamp"}
    """
    try:
        loader_name = event.get("loader_name", "stock_scores")

        logger.info(f"[TRIGGER] Invoking {loader_name} on ECS...")

        # Start ECS task for the loader
        cluster = "algo-cluster"
        task_definition_family = f"algo-{loader_name}-loader"

        response = ecs.run_task(
            cluster=cluster,
            taskDefinition=task_definition_family,
            launchType="EC2",
            overrides={
                "containerOverrides": [
                    {
                        "name": f"algo-{loader_name}-loader",
                        "environment": [
                            {"name": "LOADER_NAME", "value": loader_name},
                        ],
                    }
                ]
            },
        )

        # FAIL-FAST: ECS run_task response must include both 'tasks' and 'failures' keys
        # Missing keys indicate API error - data pipeline initialization must not silently fail
        if "tasks" not in response or "failures" not in response:
            raise RuntimeError(
                f"[CRITICAL] ECS run_task response malformed. "
                f"Missing required keys: {[k for k in ['tasks', 'failures'] if k not in response]}. "
                f"Response keys: {list(response.keys())}. "
                f"Loader {loader_name} failed to initialize."
            )

        tasks = response["tasks"]
        failures = response["failures"]

        if tasks:
            task_arns = [task["taskArn"] for task in tasks]
            logger.info(f"[TRIGGER] Started {len(task_arns)} ECS task(s): {task_arns}")
            body = {
                "statusCode": 200,
                "message": f"Loader {loader_name} started on ECS ({len(task_arns)} task(s))",
                "tasks": task_arns,
                "timestamp": datetime.utcnow().isoformat(),
            }
            return {
                "statusCode": 200,
                "body": json.dumps(body),
            }
        else:
            logger.error(f"[TRIGGER] Failed to start task: {failures}")
            body = {
                "statusCode": 500,
                "error": f"Failed to start loader task: {failures}",
                "message": "Failed to start loader task",
            }
            return {
                "statusCode": 500,
                "body": json.dumps(body),
            }

    except Exception as e:
        logger.error(f"[TRIGGER] Error: {e}", exc_info=True)
        body = {
            "statusCode": 500,
            "error": str(e),
            "message": f"Error triggering loader: {e!s}",
        }
        return {
            "statusCode": 500,
            "body": json.dumps(body),
        }
