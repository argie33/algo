"""
Loader Timeout Guardian Lambda

Kills ECS loader tasks that have been running longer than their own configured
timeout. Runs every 5 minutes via EventBridge.

Fargate has no built-in per-task execution time limit -- only the loader script's
own code can stop itself (e.g. loaders/load_prices.py's SIGALRM self-timeout). Any
loader that doesn't implement that (which, before this file existed, was every
loader) can hang indefinitely and keep burning Fargate compute cost until a human
notices. This is the external backstop for that gap.

Threshold source of truth: each loader's own LOADER_TIMEOUT env var, baked into its
task definition by terraform/modules/loaders/main.tf (`each.value.timeout`). Reading
it directly from the task definition (rather than keeping a second hardcoded
per-loader timeout map here) avoids the exact class of bug this guardian exists to
catch -- two independent copies of the same number drifting apart.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ecs = boto3.client("ecs")
cloudwatch = boto3.client("cloudwatch")

# Safety multiplier on top of each loader's own LOADER_TIMEOUT before killing it --
# gives room for container startup / DB connection overhead beyond the script's own
# internal deadline, so this never races the loader's own graceful self-timeout.
TIMEOUT_SAFETY_MULTIPLIER = 1.5
# Only used if a task definition has no LOADER_TIMEOUT env var at all.
DEFAULT_LOADER_TIMEOUT_SECONDS = 3600


def _cluster_name() -> str:
    cluster = os.environ.get("ECS_CLUSTER_NAME")
    if not cluster:
        raise ValueError("ECS_CLUSTER_NAME environment variable not set")
    return cluster


def _loader_name_from_family(family: str) -> str:
    """algo-stock_prices_daily-loader -> stock_prices_daily."""
    name = family
    if name.startswith("algo-"):
        name = name[len("algo-") :]
    if name.endswith("-loader"):
        name = name[: -len("-loader")]
    return name


def _get_configured_timeout(task_def_arn: str) -> int:
    """Read the LOADER_TIMEOUT env var from the task's own task definition."""
    task_def = ecs.describe_task_definition(taskDefinition=task_def_arn)["taskDefinition"]
    for container in task_def.get("containerDefinitions", []):
        for env in container.get("environment", []):
            if env.get("name") == "LOADER_TIMEOUT":
                try:
                    return int(env["value"])
                except (TypeError, ValueError):
                    logger.warning(f"Invalid LOADER_TIMEOUT in {task_def_arn}: {env.get('value')!r}")
    return DEFAULT_LOADER_TIMEOUT_SECONDS


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    """Stop ECS loader tasks that have exceeded their own configured timeout."""
    cluster = _cluster_name()
    task_arns = ecs.list_tasks(cluster=cluster, desiredStatus="RUNNING").get("taskArns", [])
    tasks = ecs.describe_tasks(cluster=cluster, tasks=task_arns).get("tasks", []) if task_arns else []

    now = datetime.now(timezone.utc)
    killed = []

    for task in tasks:
        started = task.get("startedAt")
        if started is None:
            continue  # still provisioning, nothing to measure yet

        family = task["taskDefinitionArn"].split("/")[-1].split(":")[0]
        loader_name = _loader_name_from_family(family)
        runtime_sec = (now - started).total_seconds()
        max_allowed = _get_configured_timeout(task["taskDefinitionArn"]) * TIMEOUT_SAFETY_MULTIPLIER

        if runtime_sec <= max_allowed:
            continue

        task_id = task["taskArn"].split("/")[-1]
        logger.warning(
            f"Killing hung task {task_id} ({loader_name}): running {runtime_sec / 3600:.1f}h, "
            f"max allowed {max_allowed / 3600:.1f}h"
        )
        ecs.stop_task(
            cluster=cluster,
            task=task["taskArn"],
            reason=f"loader_timeout_guardian: {loader_name} exceeded {max_allowed:.0f}s (ran {runtime_sec:.0f}s)",
        )
        killed.append({"loader": loader_name, "task_id": task_id, "runtime_sec": runtime_sec})
        cloudwatch.put_metric_data(
            Namespace="AlgoLoaders",
            MetricData=[
                {
                    "MetricName": "LoaderTimeoutKilled",
                    "Value": 1,
                    "Unit": "Count",
                    "Dimensions": [{"Name": "LoaderName", "Value": loader_name}],
                }
            ],
        )

    return {
        "statusCode": 200,
        "body": f"Checked {len(tasks)} running task(s), killed {len(killed)} hung loader(s): "
        f"{[k['loader'] for k in killed]}",
    }
