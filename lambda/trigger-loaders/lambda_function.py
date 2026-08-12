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

# Import the canonical loader registry (single source of truth)
# Add repo root to path so we can import loaders module
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, repo_root)
from loaders.loader_registry import get_table_names

# VALID_LOADER_NAMES is auto-generated from loaders/loader_registry.py, so it stays
# in sync with terraform's loader_file_map keys automatically. Without this allowlist,
# an arbitrary/misremembered loader_name (e.g. the retired "stock_symbols" alias for
# what's now "market_constituents") silently launches whatever stale/orphaned ECS
# task definition still happens to exist by that name instead of failing with a clear error.
VALID_LOADER_NAMES = get_table_names()

# CRITICAL: Loader dependencies (must match terraform computed_metrics_pipeline Step Function ordering)
# Session 82 fix: enforce these in AWS to prevent silent NULL degradation when upstream loaders fail
# Prevents manual/ad-hoc loader invocations from bypassing required dependencies
# (The Step Function already enforces these, but this guards against out-of-band loader triggers)
LOADER_DEPENDENCIES = {
    "growth_metrics": ["analyst_earnings_estimates"],  # value_quality_growth_metrics needs analyst data for forward_pe
}


class TriggerLoadersHandler(LambdaHandler):
    """Triggers ECS loader tasks."""

    @staticmethod
    def _check_loader_dependencies(loader_name: str) -> tuple[bool, str | None]:
        """Check if a loader's dependencies have been completed.

        Returns:
            (satisfied, error_message) - True if all dependencies met, False + error message if not
        """
        dependencies = LOADER_DEPENDENCIES.get(loader_name, [])
        if not dependencies:
            return True, None

        try:
            import psycopg2
            import psycopg2.extras

            from utils.db.config import get_db_config

            db_config = get_db_config()
            with psycopg2.connect(**db_config) as conn:
                with conn.cursor() as cur:
                    for dep in dependencies:
                        cur.execute(
                            "SELECT status, completion_pct FROM data_loader_status WHERE table_name = %s", (dep,)
                        )
                        result = cur.fetchone()
                        if not result:
                            return False, f"Dependency {dep} has no loader status record"
                        status, completion_pct = result
                        if status != "COMPLETED" or (completion_pct or 0) < 95:
                            return (
                                False,
                                f"Dependency {dep} not completed: status={status}, completion_pct={completion_pct}%",
                            )
            return True, None
        except Exception as e:
            # On DB error, log and allow the loader to run (fail-open: prioritize running over blocking)
            logger.error(f"[DEPENDENCY_CHECK] Error checking dependencies for {loader_name}: {e}")
            return True, None

    @staticmethod
    def _parse_task_count(task_count_raw: Any) -> int | LambdaResponse:
        """Parse and validate task_count, returning either the int or a validation-error response."""
        if task_count_raw is None:
            return int(os.getenv("DEFAULT_LOADER_TASK_COUNT", "1"))
        try:
            task_count = int(task_count_raw)
        except (ValueError, TypeError):
            return LambdaResponse.validation_error(
                "task_count",
                f"task_count must be numeric, got {task_count_raw!r}",
            )
        if task_count < 1:
            return LambdaResponse.validation_error("task_count", "task_count must be >= 1")
        return task_count

    @staticmethod
    def _parse_backfill_days(backfill_days_raw: Any) -> int | LambdaResponse | None:
        """Parse and validate backfill_days, returning the int, None, or a validation-error response."""
        if backfill_days_raw is None:
            return None
        try:
            backfill_days = int(backfill_days_raw)
        except (ValueError, TypeError):
            return LambdaResponse.validation_error(
                "backfill_days",
                f"backfill_days must be numeric, got {backfill_days_raw!r}",
            )
        if backfill_days < 1:
            return LambdaResponse.validation_error("backfill_days", "backfill_days must be >= 1")
        return backfill_days

    @staticmethod
    def _already_running_tasks(ecs: Any, cluster_arn: str, task_def_family: str) -> list[str]:
        """Mutual exclusion: check for tasks already running for this loader family.

        Without this, repeated triggers (manual retries, overlapping schedules,
        concurrent callers) pile up multiple instances of the same loader racing
        each other against the same DB/API rate limits -- observed in production
        as 5 simultaneous stock_prices_daily tasks plus a 3h+ stuck yfinance_snapshot
        task, which starved Phase 1's price-coverage check and halted the orchestrator.
        """
        existing = ecs.list_tasks(cluster=cluster_arn, family=task_def_family, desiredStatus="RUNNING")
        task_arns = existing.get("taskArns")
        if task_arns is None:
            raise RuntimeError(
                f"[ECS] list_tasks returned response without 'taskArns' key (CRITICAL AWS API error). "
                f"Response keys: {list(existing.keys())}. This indicates AWS SDK/API protocol change "
                f"or permission issue. Cannot safely determine if tasks are already running."
            )
        return list(task_arns)

    def handle(self, event: dict[str, Any], context: Any) -> LambdaResponse:
        """Handle loader trigger request.

        Event params:
          - loader_name: (required) 'stock_prices_daily', 'market_health_daily', etc.
          - task_count: (optional, default 1) how many parallel tasks
          - backfill_days: (optional) forces the loader's --backfill-days flag, which
            bypasses the per-symbol watermark and refetches the last N days/years of
            history instead of only what's newer than the last loaded value. Needed for
            recovery when a symbol's history is stuck incomplete (the watermark won't
            re-fetch years already "passed" on a normal incremental run).
        """
        loader_name = event.get("loader_name")
        if not loader_name:
            path_params = event.get("pathParameters")
            loader_name = (
                path_params.get("loader") if path_params is not None and isinstance(path_params, dict) else None
            )

        if not loader_name:
            return LambdaResponse.validation_error("loader_name", "loader_name is required")

        if loader_name not in VALID_LOADER_NAMES:
            return LambdaResponse.validation_error(
                "loader_name",
                f"Unknown loader_name {loader_name!r}. Must be one of the loaders defined in "
                f"terraform/modules/loaders/main.tf's loader_file_map: {sorted(VALID_LOADER_NAMES)}",
            )

        # CRITICAL FIX (Session 82): Check loader dependencies before running
        # Prevents silent NULL degradation if upstream loaders fail or haven't completed
        deps_satisfied, dep_error = self._check_loader_dependencies(loader_name)
        if not deps_satisfied:
            logger.error(f"[DEPENDENCY_CHECK] {loader_name}: {dep_error}")
            return LambdaResponse.validation_error(
                "dependencies",
                f"Cannot run {loader_name}: {dep_error}. Trigger dependencies first.",
            )

        task_count = self._parse_task_count(event.get("task_count"))
        if isinstance(task_count, LambdaResponse):
            return task_count

        backfill_days = self._parse_backfill_days(event.get("backfill_days"))
        if isinstance(backfill_days, LambdaResponse):
            return backfill_days

        project_name = os.getenv("PROJECT_NAME", "algo")
        cluster_arn = os.getenv("ECS_CLUSTER_ARN")

        if not cluster_arn:
            return LambdaResponse.error("ECS_CLUSTER_ARN not configured", status_code=500)

        critical_loaders = {
            # SEC financial statements (consolidated into single task - Phase 5 optimization)
            # FIXED (2026-07-13): Replaced 8 individual financials_*_* tasks with single "financials_all"
            "financials_all",
            # Metric loaders (required before stock_scores; depend on financials_all above)
            "quality_metrics",
            "growth_metrics",
            "value_metrics",
            "positioning_metrics",
            "stability_metrics",
            # Price data (fundamental for downstream processing)
            "stock_prices_daily",
            # Market and regime (trading decisions)
            "market_health_daily",
            "market_exposure_daily",
            # Economic data (consolidated FRED + DXY into single task)
            # FIXED (2026-07-13): dxy_index merged into "economic_data"
            "economic_data",
            # Signals and scoring (position sizing)
            "stock_scores",
            "technical_data_daily",
            # Portfolio and risk metrics
            "algo_metrics_daily",
            # Industry and sector analysis (consolidated into sector_industry_daily - Session 273)
            # DEPRECATED: industry_ranking, sector_ranking, sector_performance consolidated
            "sector_industry_daily",
            "market_sentiment",  # Re-enabled daily (was weekly)
            "buy_sell_daily",  # Signal generation
            "trend_template_data",  # Minervini/Weinstein setup/teardown
        }
        # Use FARGATE for critical loaders (higher timeout, guaranteed resources)
        use_fargate = loader_name in critical_loaders

        # Set environment variables for ECS task
        # Use centralized loader-specific timeout config (in seconds, matching loaders/runner.py expectation)
        # ENV VAR CRITICAL FIX: Changed from LOADER_TIMEOUT_SEC to LOADER_TIMEOUT for consistency
        # with loaders/runner.py which reads LOADER_TIMEOUT (without _SEC suffix)
        loader_timeout_sec = self._get_loader_timeout(loader_name)
        environment_overrides = {
            # Use centralized loader-specific timeout config
            "LOADER_TIMEOUT": str(loader_timeout_sec),
            # Reduce batch size in AWS to avoid yfinance rate limiting
            "LOADER_CHUNK_SIZE": "100",
            # Increase memory limit flag for batch processing
            "ECS_TASK_MEMORY_LIMIT": "1024" if loader_name in critical_loaders else "512",
        }
        if backfill_days is not None:
            # Read by loaders/runner.py as a fallback default for --backfill-days. Using an
            # env var (rather than a command override) means we don't need to know or
            # reconstruct each loader's script filename/full command here.
            environment_overrides["BACKFILL_DAYS"] = str(backfill_days)

        task_def = f"{project_name}-{loader_name}-loader"
        logger.info(f"Triggering loader: {loader_name} (task_def={task_def}, count={task_count})")

        # Container name is "{project}-{loader}" (no -loader suffix) per Terraform task definition
        container_overrides = [
            {
                "name": f"{project_name}-{loader_name}",
                "environment": [{"name": k, "value": v} for k, v in environment_overrides.items()],
            }
        ]

        subnet_ids = os.getenv("SUBNET_IDS")
        if not subnet_ids:
            return LambdaResponse.error("SUBNET_IDS not configured", status_code=500)

        security_group_id = os.getenv("SECURITY_GROUP_ID")
        if not security_group_id:
            return LambdaResponse.error("SECURITY_GROUP_ID not configured", status_code=500)

        run_task_params: dict[str, Any] = {
            "cluster": cluster_arn,
            "taskDefinition": task_def,
            "networkConfiguration": {
                "awsvpcConfiguration": {
                    "subnets": subnet_ids.split(","),
                    "securityGroups": [security_group_id],
                    "assignPublicIp": "DISABLED",
                }
            },
            "count": task_count,
            "overrides": {
                "containerOverrides": container_overrides,
            },
        }

        if use_fargate:
            run_task_params["launchType"] = "FARGATE"
        else:
            run_task_params["capacityProviderStrategy"] = [
                {"capacityProvider": "FARGATE_SPOT", "weight": 100, "base": 0}
            ]

        ecs = boto3.client("ecs", region_name=os.getenv("AWS_REGION", "us-east-1"))

        already_running = self._already_running_tasks(ecs, cluster_arn, task_def)
        if already_running:
            logger.warning(
                f"[TRIGGER_LOADER] Skipping {loader_name}: {len(already_running)} task(s) already running "
                f"for family {task_def}: {already_running}"
            )
            return LambdaResponse.success(
                {
                    "message": f"Skipped triggering {loader_name}: already running",
                    "tasks": already_running,
                    "already_running": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        response = ecs.run_task(**run_task_params)

        # CRITICAL: Never silently default task/failure lists from ECS response
        # If "tasks" field missing, ECS returned error response but we need to see it
        tasks = response.get("tasks")
        if tasks is None:
            logger.error(
                f"[TRIGGER_LOADER] ECS run_task response missing 'tasks' field. "
                f"Response structure: {response.keys()}. This indicates ECS API error."
            )
            return LambdaResponse.error(
                "ECS API error: missing 'tasks' field in response. Check AWS credentials and permissions.",
                status_code=500,
            )

        if not tasks:  # tasks is empty list (no tasks started)
            failures = response.get("failures")
            if failures is None:
                logger.error(
                    f"[TRIGGER_LOADER] ECS run_task failed (empty tasks) but 'failures' field missing. "
                    f"Response structure: {response.keys()}. Cannot determine failure reason."
                )
                return LambdaResponse.error(
                    "ECS returned empty tasks list but no failure details. Check AWS CloudWatch logs.",
                    status_code=500,
                )

            error_reasons = []
            for f in failures:
                if isinstance(f, dict) and "reason" in f:
                    error_reasons.append(f["reason"])
                else:
                    error_reasons.append(f"Malformed failure object: {f}")

            if not error_reasons:
                error_reasons = ["Unknown error - empty failures list"]

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
