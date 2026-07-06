"""Lambda to trigger data loaders on ECS.

When dashboard detects stale data, it invokes this Lambda to kick off
the stock_scores loader task on ECS (which has proper RDS credentials).
"""

import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ecs = boto3.client("ecs", region_name=os.getenv("AWS_REGION", "us-east-1"))


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle request to trigger loader on ECS."""
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

        tasks = response.get("tasks", [])
        if tasks:
            task_arn = tasks[0]["taskArn"]
            logger.info(f"[TRIGGER] Started ECS task: {task_arn}")
            return {
                "statusCode": 202,
                "message": f"Loader {loader_name} started on ECS",
                "taskArn": task_arn,
            }
        else:
            failures = response.get("failures", [])
            logger.error(f"[TRIGGER] Failed to start task: {failures}")
            return {
                "statusCode": 500,
                "message": "Failed to start loader task",
                "failures": failures,
            }

    except Exception as e:
        logger.error(f"[TRIGGER] Error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "message": f"Error triggering loader: {str(e)}",
        }
