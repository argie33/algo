#!/usr/bin/env python3
"""
Phase 1 Failsafe: Automatic Retry for Incomplete Loaders

Detects loaders that are incomplete (<95% symbol coverage) and triggers automatic
retries to recover. This prevents cascading failures downstream due to incomplete data.

Strategy:
1. After initial Phase 1 freshness check passes, query data_loader_status
2. Find any loaders with INCOMPLETE status or completion_pct < 95%
3. For each incomplete loader:
   - Log diagnostic info (how many symbols missing, last error, etc.)
   - Wait for 90 seconds (allow some time for external API throttling to reset)
   - Trigger a retry of the loader
   - Poll status for completion (up to 15 min timeout)
   - If retry succeeds (>=95%), mark as recovered and proceed
   - If retry fails, log alert and halt if critical, warn if auxiliary
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import psycopg2
from botocore.exceptions import BotoCoreError, ClientError

from utils.data_tiers import is_critical
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

# Loaders that are critical for downstream phases (halt if incomplete after retry)
# These use data_loader_status.table_name values, not logical loader names
# (PriceLoader produces multiple table_name entries: price_daily, price_weekly, etc.)
CRITICAL_INCOMPLETE_LOADERS = {
    # Price tables (any incomplete price table means stock_prices_daily is critical)
    "price_daily",
    "price_weekly",
    "price_monthly",
    "etf_price_daily",
    "etf_price_weekly",
    "etf_price_monthly",
    # Market regime tables (halt if stale — must run on FARGATE, not SPOT)
    "market_health_daily",
    "market_exposure_daily",
    # Other critical loaders
    "stock_scores",
    "technical_data_daily",
    # Metric loaders: essential for stock scoring (FIXED 2026-07-05)
    # CRITICAL: These are no longer auxiliary. stock_scores requires minimum 3/6 metrics
    # per GOVERNANCE.md. Missing metrics cause scores to degrade or fail entirely.
    "growth_metrics",  # Required for growth_score calculation
    "quality_metrics",  # Required for quality_score calculation
    "value_metrics",  # Required for value_score calculation
    "positioning_metrics",  # Required for positioning_score calculation
    "stability_metrics",  # Required for stability_score calculation
}

# Loaders that are auxiliary (warn if incomplete after retry, but allow proceeding)
# NOTE: These loaders are nice-to-have enrichments; failing to load them should NOT
# trigger retry since they don't block trading. Phase 1 only retries CRITICAL loaders.
# UPDATED 2026-07-05: All metric loaders (growth, positioning, quality, stability, value)
# moved to CRITICAL_INCOMPLETE_LOADERS. These are essential for stock scoring per
# GOVERNANCE.md: stock_scores requires minimum 3/6 metrics (50% completeness).
# Incomplete metrics cause scores to degrade or fail entirely. Metric loaders must be
# retried and must complete with sufficient coverage (>70%) before stock_scores publishes.
AUXILIARY_INCOMPLETE_LOADERS = {
    "analyst_sentiment_analysis",
    "sector_ranking",
    "trend_template_data",
}

# Time to wait before retrying. Retries now trigger an independent ECS task
# (see invoke_loader_retry) instead of making API calls in-process, so there's
# no in-process throttling to wait out — this is just a brief settling delay.
RETRY_WAIT_SECONDS = 5

# Timeout for monitoring retry (how long THIS phase blocks waiting to see if the
# retry already completed, before giving up and letting the run proceed/halt on
# current data). Real loaders (positioning_metrics, value_metrics, etc.) can take
# 20-40 minutes on ECS — this Lambda cannot wait that long: its own configured
# timeout is 300s (terraform.tfvars algo_lambda_timeout) shared with phases 2,6,9
# which always run afterward. So this is a short best-effort poll, not a real wait
# for completion: invoke_loader_retry() already fired the ECS task asynchronously;
# if it doesn't finish within this window, status_reason="timeout" is returned,
# the loader is left "still_failing" for this run (existing halt_required handling
# applies), and the NEXT scheduled orchestrator run picks up the by-then-completed
# data. Multiple incomplete critical loaders are retried sequentially in the
# calling loop, so keep this small to bound total Phase 1 time.
RETRY_MONITOR_TIMEOUT_SECONDS = 45


def check_and_retry_incomplete_loaders(dry_run: bool = False) -> dict[str, Any]:
    """Check for incomplete loaders and retry them.

    Args:
        dry_run: If True, don't actually retry, just report what would be retried

    Returns:
        Dict with retry results:
        {
            "incomplete_loaders": [...],  # Loaders that were incomplete
            "retried": [...],              # Loaders that were retried
            "recovered": [...],            # Loaders that recovered successfully
            "still_failing": [...],        # Loaders that still failed after retry
            "halt_required": bool,         # True if critical loaders still failing
        }
    """
    results: dict[str, Any] = {
        "incomplete_loaders": [],
        "retried": [],
        "recovered": [],
        "still_failing": [],
        "halt_required": False,
    }

    try:
        with DatabaseContext("read") as cur:
            # Find loaders with <95% completion in the last 1 hour
            cur.execute("""
                SELECT
                    table_name,
                    status,
                    completion_pct,
                    symbols_loaded,
                    symbol_count,
                    error_message,
                    execution_started,
                    last_updated
                FROM data_loader_status
                WHERE (completion_pct < 95.0 OR status = 'INCOMPLETE')
                    AND last_updated >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
                ORDER BY completion_pct ASC, table_name
            """)

            incomplete_rows = cur.fetchall()

            for (
                table_name,
                _status,
                completion_pct,
                symbols_loaded,
                symbol_count,
                error_msg,
                _exec_started,
                _last_updated,
            ) in incomplete_rows:
                # Fail-fast if symbol counts are invalid. These must be precise for diagnostics.
                if symbol_count is None:
                    raise ValueError(
                        f"[PHASE 1 FAILSAFE] Loader {table_name}: symbol_count is NULL in data_loader_status. "
                        "Cannot determine coverage without valid symbol counts. Data integrity issue."
                    )
                if symbols_loaded is None:
                    raise ValueError(
                        f"[PHASE 1 FAILSAFE] Loader {table_name}: symbols_loaded is NULL in data_loader_status. "
                        "Cannot calculate missing symbols without valid counts. Data integrity issue."
                    )

                symbols_missing = symbol_count - symbols_loaded
                is_crit = is_critical(table_name)

                if completion_pct is None:
                    logger.warning(
                        f"[PHASE 1 FAILSAFE] Incomplete loader detected: {table_name} "
                        f"status unknown ({symbols_loaded}/{symbol_count} symbols, {symbols_missing} missing) — loader may still be running"
                    )
                else:
                    logger.warning(
                        f"[PHASE 1 FAILSAFE] Incomplete loader detected: {table_name} "
                        f"{completion_pct:.1f}% ({symbols_loaded}/{symbol_count} symbols, {symbols_missing} missing)"
                    )

                results["incomplete_loaders"].append(
                    {
                        "loader": table_name,
                        "completion_pct": completion_pct,  # Preserve NULL (unknown) vs 0 (failed)
                        "symbols_missing": symbols_missing,
                        "error": error_msg[:100] if error_msg else None,
                        "is_critical": is_crit,
                    }
                )

                if not dry_run:
                    # Only retry CRITICAL loaders. AUXILIARY loaders are nice-to-have;
                    # don't spend time retrying them since they don't block trading.
                    if not is_crit:
                        logger.warning(
                            f"[PHASE 1 FAILSAFE] AUXILIARY LOADER INCOMPLETE: {table_name} "
                            f"{completion_pct:.1f}% ({symbols_missing} missing). "
                            f"No retry attempted—auxiliary enrichment data is optional. "
                            f"Stock scores will reflect missing data via data_unavailable flags. "
                            f"This is correct behavior per GOVERNANCE (explicit unavailability markers)."
                        )
                        results["still_failing"].append(table_name)
                        continue

                    # Trigger retry — may raise RuntimeError or TimeoutError on failure
                    try:
                        retry_result = retry_loader(table_name, symbols_missing, is_crit)

                        if retry_result["retried"]:
                            results["retried"].append(table_name)

                            if retry_result["recovered"]:
                                results["recovered"].append(table_name)
                                final_pct = retry_result.get("final_completion_pct")
                                pct_str = f"{final_pct:.1f}%" if final_pct is not None else "unknown"
                                logger.info(f"[PHASE 1 FAILSAFE] Loader recovered: {table_name} -> {pct_str}")
                            else:
                                results["still_failing"].append(table_name)
                                final_pct = retry_result.get("final_completion_pct")
                                pct_str = f"{final_pct:.1f}%" if final_pct is not None else "unknown"
                                status_reason = retry_result.get("status_reason", "unknown")

                                if status_reason == "timeout":
                                    reason_msg = "timeout (loader still running after 15 minutes)"
                                elif status_reason == "failed":
                                    reason_msg = f"failed (completed with {pct_str} completion)"
                                else:
                                    reason_msg = f"failed ({pct_str} completion)"

                                logger.error(
                                    f"[PHASE 1 FAILSAFE] Loader still failing after retry: {table_name} — {reason_msg}"
                                )

                                if is_crit:
                                    results["halt_required"] = True

                    except (RuntimeError, TimeoutError, ValueError) as e:
                        logger.critical(
                            f"[PHASE 1 FAILSAFE] CRITICAL: Failed to retry loader {table_name}: {e}. "
                            "Cannot retry critical loader."
                        )
                        results["still_failing"].append(table_name)
                        if is_crit:
                            results["halt_required"] = True
                            # Re-raise to prevent proceeding without recovery of critical loader
                            raise RuntimeError(
                                f"Phase 1 Failsafe: Critical loader {table_name} retry failed. Halting to prevent trading."
                            ) from e

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        # Database errors indicate infrastructure problems. Must halt trading.
        # Cannot safely proceed without being able to check loader status.
        logger.critical(
            f"[PHASE 1 FAILSAFE] CRITICAL: Cannot check loader status due to database error: {e}. "
            "Cannot determine if critical loaders are incomplete. Trading halted."
        )
        raise RuntimeError(
            f"Phase 1 Failsafe: Cannot check loader status due to database error: {e}. "
            "Halting to prevent trading with potentially incomplete data."
        ) from e

    # CRITICAL FIX 2026-07-01: Check if stock_scores has stale upstream dependencies
    # Upstream metric loaders (positioning_metrics, value_metrics, etc.) may update multiple
    # times per day, but stock_scores only gets recomputed if it's marked incomplete.
    # This can leave stock_scores with old data when upstream metrics update.
    try:
        with DatabaseContext("read") as cur:
            # Find the most recent update time among upstream metric tables
            cur.execute("""
                SELECT MAX(updated_at) as latest_metric_update
                FROM (
                    SELECT updated_at FROM positioning_metrics WHERE updated_at IS NOT NULL
                    UNION ALL
                    SELECT updated_at FROM value_metrics WHERE updated_at IS NOT NULL
                    UNION ALL
                    SELECT updated_at FROM stability_metrics WHERE updated_at IS NOT NULL
                    UNION ALL
                    SELECT updated_at FROM quality_metrics WHERE updated_at IS NOT NULL
                    UNION ALL
                    SELECT updated_at FROM growth_metrics WHERE updated_at IS NOT NULL
                ) metric_updates
            """)
            metric_result = cur.fetchone()
            latest_metric_update = metric_result[0] if metric_result and metric_result[0] else None

            if latest_metric_update:
                # Check stock_scores update time
                cur.execute("SELECT MAX(updated_at) FROM stock_scores")
                score_result = cur.fetchone()
                latest_score_update = score_result[0] if score_result and score_result[0] else None

                # If any upstream metric is newer than stock_scores, mark stock_scores as needing update
                if latest_score_update and latest_metric_update > latest_score_update:
                    age_minutes = (latest_metric_update - latest_score_update).total_seconds() / 60
                    logger.warning(
                        f"[PHASE 1 FAILSAFE] stock_scores has stale dependencies: "
                        f"latest metric update {age_minutes:.0f}m ago, latest score update {age_minutes:.0f}m ago. "
                        f"Upstream metrics have newer data. Retriggering stock_scores recomputation."
                    )
                    # Retrigger stock_scores to pick up new metric data
                    if not dry_run:
                        retry_result = retry_loader("stock_scores", symbols_missing=0, is_critical=True)
                        if retry_result.get("recovered"):
                            results["recovered"].append("stock_scores (dependency update)")
                        else:
                            logger.warning(
                                "[PHASE 1 FAILSAFE] stock_scores retry did not recover to 95%. "
                                "May have partial data, but proceeding as auxiliary loader."
                            )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.warning(
            f"[PHASE 1 FAILSAFE] Could not check stock_scores dependencies due to database error: {e}. "
            f"Continuing with existing data; stock_scores may be stale."
        )

    return results


def retry_loader(loader_name: str, symbols_missing: int, is_critical: bool) -> dict[str, Any]:
    """Retry a single incomplete loader.

    Args:
        loader_name: Name of the loader to retry
        symbols_missing: Number of symbols that were missing
        is_critical: True if this is a critical loader

    Returns:
        Dict with retry result:
        {
            "retried": bool,        # True if retry was triggered
            "recovered": bool,      # True if loader reached >=95% after retry
            "final_completion_pct": float | None,  # None if status unknown
            "status_reason": str,   # 'success', 'timeout' (still running), or 'failed'
        }

    Raises:
        RuntimeError: If retry invocation fails
        TimeoutError: If loader retry times out during monitoring
    """
    result: dict[str, bool | float | str | None] = {
        "retried": False,
        "recovered": False,
        "final_completion_pct": None,
        "status_reason": "unknown",
    }

    # Wait for API throttling to reset
    logger.info(f"[PHASE 1 FAILSAFE] Waiting {RETRY_WAIT_SECONDS}s before retry (API reset)")
    time.sleep(RETRY_WAIT_SECONDS)

    # Trigger retry via Lambda invocation or direct call
    logger.info(f"[PHASE 1 FAILSAFE] Triggering retry for {loader_name}")
    result["retried"] = invoke_loader_retry(loader_name, is_critical)

    if result["retried"]:
        # Monitor loader status
        recovered, final_pct, status_reason = monitor_loader_retry(loader_name, RETRY_MONITOR_TIMEOUT_SECONDS)
        result["recovered"] = recovered
        result["final_completion_pct"] = final_pct
        result["status_reason"] = status_reason

    return result


def invoke_loader_retry(loader_name: str, is_critical: bool) -> bool:
    """Invoke loader retry by triggering its ECS Fargate task, asynchronously.

    The orchestrator Lambda package deliberately excludes loaders/ heavy
    dependencies (pandas/numpy — see lambda/algo_orchestrator/requirements.txt)
    so loaders cannot run in-process here. Instead this reuses the same
    "algo-trigger-loaders" Lambda (lambda/trigger-loaders/lambda_function.py)
    that EventBridge uses for the regular schedule: it does ecs:RunTask for
    the named loader and returns immediately — the loader itself runs on its
    own ECS task, independent of this Lambda's lifetime/timeout.

    Args:
        loader_name: Name of loader to retry (matches data_loader_status.table_name,
            which is also the loader_name the trigger-loaders Lambda expects)
        is_critical: True if critical loader (for logging only)

    Returns:
        True if the ECS task was successfully started

    Raises:
        RuntimeError: If the trigger invocation fails or the ECS task didn't start
    """
    logger.info(
        f"[PHASE 1 FAILSAFE] Invoking retry for {loader_name} "
        f"(priority={'critical' if is_critical else 'auxiliary'}) via algo-trigger-loaders"
    )

    trigger_function_name = os.getenv("TRIGGER_LOADERS_FUNCTION_NAME", "algo-trigger-loaders")

    try:
        lambda_client = boto3.client("lambda", region_name=os.getenv("AWS_REGION", "us-east-1"))
        response = lambda_client.invoke(
            FunctionName=trigger_function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps({"loader_name": loader_name}).encode("utf-8"),
        )

        status_code = response.get("StatusCode")
        if response.get("FunctionError"):
            payload = response["Payload"].read().decode("utf-8")
            raise RuntimeError(
                f"[PHASE 1 FAILSAFE] {trigger_function_name} returned FunctionError invoking {loader_name}: {payload}"
            )

        payload_raw = response["Payload"].read().decode("utf-8")
        payload_body = json.loads(payload_raw) if payload_raw else {}
        body = payload_body.get("body")
        body_obj = json.loads(body) if isinstance(body, str) else (body or {})

        if status_code != 200 or payload_body.get("statusCode", status_code) != 200:
            raise RuntimeError(
                f"[PHASE 1 FAILSAFE] {trigger_function_name} failed to start ECS task for {loader_name}: {body_obj}"
            )

        logger.info(f"[PHASE 1 FAILSAFE] ECS task(s) started for {loader_name}: {body_obj.get('tasks')}")
        return True

    except (RuntimeError, ValueError, TypeError, json.JSONDecodeError, ClientError, BotoCoreError) as e:
        raise RuntimeError(
            f"[PHASE 1 FAILSAFE] Failed to invoke retry for {loader_name}: {e}. "
            "Explicit error to prevent silent failure."
        ) from e


def monitor_loader_retry(loader_name: str, timeout_seconds: int) -> tuple[bool, float | None, str]:
    """Monitor loader status during retry.

    Args:
        loader_name: Name of loader being monitored
        timeout_seconds: How long to wait before giving up

    Returns:
        (recovered, final_completion_pct, status_reason):
        - recovered: True if loader reached >=95% completion
        - final_completion_pct: Latest completion percentage, or None if status unknown
        - status_reason: 'success', 'timeout' (still running), or 'failed' (completed low)

    Raises:
        RuntimeError: If database error occurs during monitoring
    """
    deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)

    while datetime.now(timezone.utc) < deadline:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT status, completion_pct FROM data_loader_status WHERE table_name = %s",
                    (loader_name,),
                )

                row = cur.fetchone()
                if row:
                    status, completion_pct = row

                    if completion_pct is None:
                        # Status unknown, likely still running — wait before checking again
                        logger.debug(
                            f"[PHASE 1 FAILSAFE] {loader_name} status unknown, still running (will check again in 10s)"
                        )
                    elif completion_pct >= 95.0:
                        logger.info(f"[PHASE 1 FAILSAFE] Loader recovered: {loader_name} {completion_pct:.1f}%")
                        return True, completion_pct, "success"

                    elif status == "COMPLETED":
                        # Completed but still below 95% (unlikely but handle it)
                        logger.warning(
                            f"[PHASE 1 FAILSAFE] Loader completed but incomplete: {loader_name} {completion_pct:.1f}%"
                        )
                        return False, completion_pct, "failed"

            # Check again in 10 seconds
            time.sleep(10)

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[PHASE 1 FAILSAFE] Database error monitoring retry for {loader_name}: {e}. "
                "Cannot determine loader status without database access."
            ) from e

    # Timeout reached — loader still running, didn't complete within deadline
    logger.error(
        f"[PHASE 1 FAILSAFE] Timeout waiting for retry of {loader_name} (waited {timeout_seconds}s, loader still running)"
    )
    return False, None, "timeout"
