#!/usr/bin/env python3
"""Lambda function to manually trigger data loaders via ECS.

Called when EventBridge fails or for emergency data refresh.
Invoked by: API /api/algo/trigger-loader endpoint or CloudWatch alarm
Uses LambdaHandler base class for standardized pattern.
"""

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

import boto3

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from base_handler import LambdaHandler, LambdaResponse, create_lambda_handler

logger = logging.getLogger()


class TriggerLoadersHandler(LambdaHandler):
    """Triggers ECS loader tasks."""

    def handle(self, event: dict[str, Any], context: Any) -> LambdaResponse:
        """Handle loader trigger request.

        Event params:
          - loader_name: (required) 'stock_prices_daily', 'market_health_daily', etc.
          - task_count: (optional, default 1) how many parallel tasks
        """
        loader_name = event.get("loader_name")
        if not loader_name:
            path_params = event.get("pathParameters")
            loader_name = path_params.get("loader") if path_params is not None and isinstance(path_params, dict) else None

        if not loader_name:
            return LambdaResponse.validation_error("loader_name", "loader_name is required")

        task_count_raw = event.get("task_count")
        if task_count_raw is None:
            task_count = int(os.getenv("DEFAULT_LOADER_TASK_COUNT", "1"))
        else:
            try:
                task_count = int(task_count_raw)
                if task_count < 1:
                    return LambdaResponse.validation_error("task_count", "task_count must be >= 1")
            except (ValueError, TypeError):
                return LambdaResponse.validation_error(
                    "task_count",
                    f"task_count must be numeric, got {task_count_raw!r}",
                )

        project_name = os.getenv("PROJECT_NAME", "algo")
        cluster_arn = os.getenv("ECS_CLUSTER_ARN")

        if not cluster_arn:
            return LambdaResponse.error("ECS_CLUSTER_ARN not configured", status_code=500)

        critical_loaders = {
            "stock_prices_daily",
            "signals_daily",
            "algo_metrics_daily",
            "stock_scores",
            "economic_metrics_daily",
        }
        use_fargate = loader_name in critical_loaders

        task_def = f"{project_name}-{loader_name}-loader"
        logger.info(f"Triggering loader: {loader_name} (task_def={task_def}, count={task_count})")

        run_task_params: dict[str, Any] = {
            "cluster": cluster_arn,
            "taskDefinition": task_def,
            "networkConfiguration": {
                "awsvpcConfiguration": {
                    "subnets": os.getenv("SUBNET_IDS", "").split(","),
                    "securityGroups": [os.getenv("SECURITY_GROUP_ID", "")],
                    "assignPublicIp": "DISABLED",
                }
            },
            "count": task_count,
        }

        if use_fargate:
            run_task_params["launchType"] = "FARGATE"
        else:
            run_task_params["capacityProviderStrategy"] = [
                {"capacityProvider": "FARGATE_SPOT", "weight": 100, "base": 0}
            ]

        ecs = boto3.client("ecs", region_name=os.getenv("AWS_REGION", "us-east-1"))
        response = ecs.run_task(**run_task_params)

        tasks = response.get("tasks", [])
        if not tasks:
            failures = response.get("failures", [])
            error_reasons = []
            if failures:
                for f in failures:
                    if isinstance(f, dict) and "reason" in f:
                        error_reasons.append(f["reason"])
                    else:
                        error_reasons.append(f"Malformed failure object: {f}")
            if not error_reasons:
                error_reasons = ["Unknown error"]
            return LambdaResponse.error(
                f"Failed to start task: {', '.join(error_reasons)}",
                status_code=500,
            )

        task_arns = [t["taskArn"] for t in tasks]
        logger.info(f"✓ Started {len(task_arns)} tasks: {task_arns}")

        return LambdaResponse.success(
            {
                "message": f"Triggered {loader_name} loader",
                "tasks": task_arns,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


lambda_handler = create_lambda_handler(TriggerLoadersHandler)
