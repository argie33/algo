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
   - Trigger a retry by starting the loader's ECS task (via algo-trigger-loaders,
     the same mechanism the regular schedule uses) - runs independently of this Lambda
   - Briefly poll status (up to RETRY_MONITOR_TIMEOUT_SECONDS) in case it finishes fast
   - If retry succeeds (>=95%) within that short window, mark as recovered and proceed
   - Otherwise mark as still incomplete for THIS run (halt if critical, warn if
     auxiliary) - the ECS task keeps running in the background and the next
     scheduled orchestrator run will see the completed data
"""

import json
import logging
import os
import time
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import psycopg2
from botocore.exceptions import BotoCoreError, ClientError

from utils.data_tiers import is_critical
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

# Critical vs. auxiliary classification for retry decisions below comes from
# utils.data_tiers.is_critical() (backed by CRITICAL_DATA/AUXILIARY_DATA there) - this
# module previously duplicated that classification in two local sets
# (CRITICAL_INCOMPLETE_LOADERS/AUXILIARY_INCOMPLETE_LOADERS) that were never actually
# read by any retry logic here (is_critical(table_name) at the actual decision point
# below has always been the live source), had already drifted from data_tiers.py (e.g.
# listed a stale "economic_metrics_daily" name that has never matched the real loader's
# table_name, "economic_data"), and were only referenced by one test asserting their own
# static content. Removed 2026-07-21 (loader-review audit); see
# tests/integration/test_complete_aws_deployment.py::test_growth_metrics_marked_enrichment,
# repointed at the real utils.data_tiers.CRITICAL_DATA set.

# Time to wait before retrying. Retries now trigger an independent ECS task
# (see invoke_loader_retry) instead of making API calls in-process, so there's
# no in-process throttling to wait out - this is just a brief settling delay.
RETRY_WAIT_SECONDS = 5

# Timeout for monitoring retry (how long THIS phase blocks waiting to see if the
# retry already completed, before giving up and letting the run proceed/halt on
# current data). Real loaders (positioning_metrics, value_metrics, etc.) can take
# 20-40 minutes on ECS - this Lambda cannot wait that long: its own configured
# timeout is 300s (terraform.tfvars algo_lambda_timeout) shared with phases 2,6,9
# which always run afterward. So this is a short best-effort poll, not a real wait
# for completion: invoke_loader_retry() already fired the ECS task asynchronously;
# if it doesn't finish within this window, status_reason="timeout" is returned,
# the loader is left "still_failing" for this run (existing halt_required handling
# applies), and the NEXT scheduled orchestrator run picks up the by-then-completed
# data. Multiple incomplete critical loaders are retried sequentially in the
# calling loop, so keep this small to bound total Phase 1 time.
RETRY_MONITOR_TIMEOUT_SECONDS = 45


def _get_expected_data_date() -> tuple[_date, str]:
    """Calculate expected data date based on market hours (trading hours aware).

    Returns:
        Tuple of (expected_data_date, freshness_context_str)
    """
    from datetime import timedelta as td
    from zoneinfo import ZoneInfo

    from algo.infrastructure import MarketCalendar

    now_et = datetime.now(ZoneInfo("America/New_York"))
    run_date_et = now_et.date()

    if now_et.hour < 16:  # INTRADAY: before market close
        prev_date = run_date_et - td(days=1)
        expected_data_date = prev_date
        while expected_data_date > run_date_et - td(days=10):
            if MarketCalendar.is_trading_day(expected_data_date):
                break
            expected_data_date -= td(days=1)
        context = f"INTRADAY - expecting previous trading day ({expected_data_date})"
    else:  # After market close
        if MarketCalendar.is_trading_day(run_date_et):
            expected_data_date = run_date_et
        else:
            expected_data_date = run_date_et - td(days=1)
            while expected_data_date > run_date_et - td(days=10):
                if MarketCalendar.is_trading_day(expected_data_date):
                    break
                expected_data_date -= td(days=1)
        context = f"EOD - expecting same/recent trading day ({expected_data_date})"

    return expected_data_date, context


def _check_and_refresh_local(dry_run: bool = False) -> dict[str, Any]:
    """In LOCAL_MODE, check for stale DATA and refresh loaders locally.

    Runs loaders directly using Python imports instead of AWS Lambda/ECS.
    Checks actual data freshness (MAX(date) in tables), not loader status timestamps.
    This catches cases where the loader ran recently but produced stale data.

    Uses MARKET-AWARE freshness checks (same logic as phase1_data_freshness.py):
    - During intraday (before 4 PM ET): previous trading day's data is CORRECT
    - After market close (4 PM+ ET): same-day data is CORRECT
    Does NOT use naive 24-hour checks which fail at market holidays/weekends.

    Args:
        dry_run: If True, don't actually run loaders, just report what would run

    Returns:
        Dict with refresh results (same format as AWS retry)
    """
    results: dict[str, Any] = {
        "incomplete_loaders": [],
        "retried": [],
        "recovered": [],
        "still_failing": [],
        "halt_required": False,
    }

    # Critical loaders to refresh in local mode (table_name: loader_script_key)
    # Only core trading data - enrichment metrics no longer critical (Session 221)
    loaders_to_refresh = {
        "price_daily": "prices",
        "technical_data_daily": "technical",
        "stock_scores": "scores",
        "market_health_daily": "market_status",
    }

    try:
        # Check actual data freshness (MAX(date) in each table), not loader status
        # This catches when loader ran recently but data is stale
        stale_loaders = []

        # Market-aware freshness check: determine expected data date based on trading hours
        expected_data_date, freshness_context = _get_expected_data_date()
        logger.info(f"[PHASE 1 FAILSAFE LOCAL] {freshness_context}")

        with DatabaseContext("read") as cur:
            for table_name, loader_key in loaders_to_refresh.items():
                try:
                    if table_name == "stock_scores":
                        # stock_scores doesn't have a date column, use updated_at instead
                        cur.execute("SELECT MAX(updated_at) FROM stock_scores")
                    else:
                        cur.execute(f"SELECT MAX(date) FROM {table_name}")

                    row = cur.fetchone()
                    if row and row[0]:
                        max_date = row[0]
                        # Convert date/datetime to date for comparison
                        from datetime import date as date_type

                        if isinstance(max_date, date_type) and not isinstance(max_date, datetime):
                            table_max_date = max_date
                        elif isinstance(max_date, datetime):
                            table_max_date = max_date.date()
                        else:
                            logger.warning(
                                f"[PHASE 1 FAILSAFE LOCAL] Unexpected date type for {table_name}: {type(max_date)}"
                            )
                            continue

                        # Market-aware staleness check: allow up to 10 days behind (covers weekends/holidays)
                        # Don't use naive hours checks which fail at multi-day gaps
                        days_behind = (expected_data_date - table_max_date).days
                        is_stale = days_behind > 0  # Stale if behind expected date

                        if is_stale:
                            stale_loaders.append((table_name, loader_key, days_behind))
                            results["incomplete_loaders"].append(table_name)
                            logger.warning(
                                f"[PHASE 1 FAILSAFE LOCAL] {table_name} data stale: "
                                f"{table_max_date} vs expected {expected_data_date} "
                                f"({days_behind} day(s) behind)"
                            )
                        else:
                            logger.info(f"[PHASE 1 FAILSAFE LOCAL] {table_name} fresh: {table_max_date}")
                    else:
                        # No data at all
                        stale_loaders.append((table_name, loader_key, 999))
                        results["incomplete_loaders"].append(table_name)
                        logger.warning(f"[PHASE 1 FAILSAFE LOCAL] {table_name} has no data")

                except Exception as e:
                    logger.warning(f"[PHASE 1 FAILSAFE LOCAL] Could not check {table_name}: {e}")

        if not stale_loaders:
            logger.info("[PHASE 1 FAILSAFE LOCAL] All data current (market-aware check) - no refresh needed")
            return results

        logger.info(f"[PHASE 1 FAILSAFE LOCAL] Found {len(stale_loaders)} stale loaders to refresh")

        if dry_run:
            logger.info(f"[PHASE 1 FAILSAFE LOCAL] DRY RUN: Would refresh {[t[0] for t in stale_loaders]}")
            return results

        # Run each stale loader locally
        for table_name, loader_key, age_hours in stale_loaders:
            try:
                logger.info(f"[PHASE 1 FAILSAFE LOCAL] Refreshing {table_name} ({age_hours:.1f}h old)")
                results["retried"].append(table_name)

                # Run loader with force-refresh to bypass watermarks
                import subprocess

                env = os.environ.copy()
                env["TECH_FULL_REFRESH"] = "true"  # Bypass watermark filters

                result = subprocess.run(
                    ["python3", "scripts/run_loader.py", loader_key, "--force-refresh"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=env,
                    cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # Go to repo root
                )

                if result.returncode == 0:
                    logger.info(f"[PHASE 1 FAILSAFE LOCAL] ✓ {table_name} refreshed successfully")
                    results["recovered"].append(table_name)
                else:
                    logger.error(f"[PHASE 1 FAILSAFE LOCAL] ✗ {table_name} refresh failed: {result.stderr}")
                    results["still_failing"].append(table_name)
                    if table_name in {"price_daily", "technical_data_daily", "stock_scores"}:
                        results["halt_required"] = True

            except subprocess.TimeoutExpired:
                logger.error(f"[PHASE 1 FAILSAFE LOCAL] Timeout refreshing {table_name}")
                results["still_failing"].append(table_name)
                if table_name in {"price_daily", "technical_data_daily", "stock_scores"}:
                    results["halt_required"] = True
            except Exception as e:
                logger.error(f"[PHASE 1 FAILSAFE LOCAL] Error refreshing {table_name}: {e}")
                results["still_failing"].append(table_name)
                if table_name in {"price_daily", "technical_data_daily", "stock_scores"}:
                    results["halt_required"] = True

    except Exception as e:
        logger.error(f"[PHASE 1 FAILSAFE LOCAL] Fatal error in local refresh: {e}", exc_info=True)
        results["halt_required"] = True

    return results


def check_and_retry_incomplete_loaders(dry_run: bool = False) -> dict[str, Any]:  # noqa: C901
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

    # In LOCAL_MODE: run loaders locally instead of via AWS Lambda/ECS
    if os.getenv("LOCAL_MODE", "").lower() in ("1", "true", "yes"):
        logger.info("[PHASE 1 FAILSAFE] LOCAL_MODE enabled - triggering local loader refresh for stale data")
        results = _check_and_refresh_local(dry_run)
        return results

    try:
        with DatabaseContext("read") as cur:
            # Find loaders with <95% completion or error/failed status in the last 1 hour.
            # data_loader_status.status is written by multiple sources that don't share one
            # casing convention - utils/loader_infrastructure.py's update_loader_status()
            # writes canonical uppercase (RUNNING/COMPLETED/FAILED per utils/loaders/
            # status_enum.py), while other writers still use lowercase ("error"/"failed").
            # A plain `status IN ('error', 'failed')` only matches the lowercase writers -
            # any loader reporting canonical "FAILED" would be invisible to this OR clause
            # and only caught via the completion_pct threshold, silently narrowing failsafe
            # retry coverage. Compare case-insensitively so both vocabularies are caught.
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
                WHERE (completion_pct < 90.0 OR UPPER(status) IN ('ERROR', 'FAILED'))
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
                is_crit = is_critical(table_name)

                # Fail-fast if symbol counts are invalid for CRITICAL loaders only.
                # Non-critical loaders (aaii_sentiment, analyst_sentiment, etc.) may not track
                # symbol counts and should just be skipped/warned, not halted.
                if symbol_count is None:
                    if is_crit:
                        raise ValueError(
                            f"[PHASE 1 FAILSAFE] CRITICAL Loader {table_name}: symbol_count is NULL. "
                            "Cannot proceed with critical data. Data integrity issue."
                        )
                    else:
                        logger.debug(
                            f"[PHASE 1 FAILSAFE] Non-critical loader {table_name}: symbol_count is NULL, skipping"
                        )
                        continue

                if symbols_loaded is None:
                    if is_crit:
                        raise ValueError(
                            f"[PHASE 1 FAILSAFE] CRITICAL Loader {table_name}: symbols_loaded is NULL. "
                            "Data integrity issue."
                        )
                    else:
                        logger.debug(
                            f"[PHASE 1 FAILSAFE] Non-critical loader {table_name}: symbols_loaded is NULL, skipping"
                        )
                        continue

                symbols_missing = symbol_count - symbols_loaded

                if completion_pct is None:
                    logger.warning(
                        f"[PHASE 1 FAILSAFE] Incomplete loader detected: {table_name} "
                        f"status unknown ({symbols_loaded}/{symbol_count} symbols, {symbols_missing} missing) - loader may still be running"
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
                            f"No retry attempted-auxiliary enrichment data is optional. "
                            f"Stock scores will reflect missing data via data_unavailable flags. "
                            f"This is correct behavior per GOVERNANCE (explicit unavailability markers)."
                        )
                        results["still_failing"].append(table_name)
                        continue

                    # Trigger retry - may raise RuntimeError or TimeoutError on failure
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
                                    reason_msg = (
                                        f"not yet confirmed recovered after {RETRY_MONITOR_TIMEOUT_SECONDS}s poll "
                                        "(ECS task still running in background - next scheduled run will re-check)"
                                    )
                                elif status_reason == "failed":
                                    reason_msg = f"failed (completed with {pct_str} completion)"
                                else:
                                    reason_msg = f"failed ({pct_str} completion)"

                                logger.error(
                                    f"[PHASE 1 FAILSAFE] Loader still failing after retry: {table_name} - {reason_msg}"
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
    dependencies (pandas/numpy - see lambda/algo_orchestrator/requirements.txt)
    so loaders cannot run in-process here. Instead this reuses the same
    "algo-trigger-loaders" Lambda (lambda/trigger-loaders/lambda_function.py)
    that EventBridge uses for the regular schedule: it does ecs:RunTask for
    the named loader and returns immediately - the loader itself runs on its
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

    # In local mode, skip Lambda invocation (no AWS credentials available)
    if os.getenv("LOCAL_MODE", "").lower() in ("true", "1", "yes"):
        logger.info(
            f"[PHASE 1 FAILSAFE] LOCAL_MODE enabled - skipping Lambda invocation for {loader_name}. "
            f"Loader retry would normally happen on AWS ECS. In local dev, data updates must be triggered manually."
        )
        return False

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
        if not payload_raw:
            raise ValueError("[PHASE 1 FAILSAFE] Lambda response body is empty")
        payload_body = json.loads(payload_raw)
        if "body" not in payload_body:
            raise ValueError("[PHASE 1 FAILSAFE] Lambda response missing 'body' field")
        body = payload_body["body"]
        if body is None:
            raise ValueError("[PHASE 1 FAILSAFE] Lambda body is None")
        body_obj = json.loads(body) if isinstance(body, str) else body

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
                        # Status unknown, likely still running - wait before checking again
                        logger.debug(
                            f"[PHASE 1 FAILSAFE] {loader_name} status unknown, still running (will check again in 10s)"
                        )
                    elif completion_pct >= 90.0:
                        logger.info(f"[PHASE 1 FAILSAFE] Loader recovered: {loader_name} {completion_pct:.1f}%")
                        return True, completion_pct, "success"

                    elif status == "COMPLETED":
                        # Completed but still below 90% (unlikely but handle it)
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

    # Timeout reached - loader still running, didn't complete within deadline
    logger.error(
        f"[PHASE 1 FAILSAFE] Timeout waiting for retry of {loader_name} (waited {timeout_seconds}s, loader still running)"
    )
    return False, None, "timeout"
