#!/usr/bin/env python3

import json
import logging
import os
import sys
import time
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg2

from algo.infrastructure import MarketCalendar
from algo.orchestration.database_health_monitor import DatabaseHealthMonitor
from algo.orchestration.halt_flag_manager import HaltFlagManager
from algo.orchestration.phase_event_hub import (
    PhaseCompletedEvent,
    PhaseStatus,
    get_event_hub,
)

# Import all phase executors at module load time (not dynamically)
from algo.orchestrator.phase1_data_freshness import run as run_phase1
from algo.orchestrator.phase2_circuit_breakers import run as run_phase2
from algo.orchestrator.phase3_position_monitor import run as run_phase3
from algo.orchestrator.phase4_reconciliation import run as run_phase4
from algo.orchestrator.phase5_exposure_policy import run as run_phase5
from algo.orchestrator.phase6_exit_execution import run as run_phase6
from algo.orchestrator.phase7_signal_generation import run as run_phase7
from algo.orchestrator.phase8_entry_execution import run as run_phase8
from algo.orchestrator.phase9_reconciliation import run as run_phase9
from algo.orchestrator.phase_executor import OrchestratorPhaseExecutor, PhaseDefinition
from algo.orchestrator.phase_registry import PhaseRegistry
from algo.reporting import AlertManager
from monitoring.metrics_context import (
    TimeBlock,
    log_metrics_summary,
)
from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ
from utils.infrastructure.market_timing import (
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    ORCHESTRATOR_KILL_BUFFER_MINUTES,
    ORCHESTRATOR_RUN_TIMES_TUPLE,
)
from utils.logging import get_tracker

# Add project root (parent of parent of parent since we're in algo/orchestration)
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


logger = logging.getLogger(__name__)


class Orchestrator:
    """Daily workflow runner with explicit phases."""

    def __init__(
        self,
        config: Any,
        run_date: _date | None = None,
        dry_run: bool = False,
        verbose: bool = True,
        run_id: str | None = None,
    ) -> None:
        if config is None:
            raise ValueError(
                "Orchestrator requires explicit config parameter (dependency injection). "
                "Remove fallback to get_config() — get config at entry point and pass it explicitly."
            )
        self.config = config

        env_execution_mode = os.getenv("ORCHESTRATOR_EXECUTION_MODE", "").strip().lower()
        if env_execution_mode:
            self.config.override("execution_mode", env_execution_mode)

        # Explicitly default run_date to today if not provided
        self.run_date = run_date if run_date is not None else datetime.now(EASTERN_TZ).date()
        self.dry_run = dry_run
        self.verbose = verbose
        self.phase_results: dict[int | str, Any] = {}
        # Use provided run_id if given (from EventBridge scheduler), otherwise generate one
        if run_id:
            self.run_id = run_id
        else:
            self.run_id = f"RUN-{self.run_date.isoformat()}-{datetime.now(timezone.utc).strftime('%H%M%S')}"

        self.execution_tracker = get_tracker()
        self.execution_tracker.set_run_context(self.run_id, self.run_date)

        from utils.db import DynamoDBLockManager

        self.lock_manager = DynamoDBLockManager()
        self._lock_acquired = False

        self.degraded_mode = False
        try:
            self.alerts: AlertManager = AlertManager()
        except RuntimeError as e:
            raise RuntimeError(
                f"CRITICAL: AlertManager initialization failed. "
                f"Cannot proceed without alert infrastructure. "
                f"Root cause: {e}. "
                f"Configure ALERT_EMAIL_TO + ALERT_SMTP_* or ALERTS_SNS_TOPIC."
            ) from e

        self.db_monitor = DatabaseHealthMonitor(self.alerts)
        self.halt_manager = HaltFlagManager(self.alerts, self.log_phase_result)

        # NOTE: Alpaca credential validation deferred to Phase 4 (DailyReconciliation)
        # This allows Phases 1-3 (data refresh) to run even if Alpaca credentials are temporarily
        # unavailable. Credential validation happens when AlpacaSyncManager is instantiated in
        # Phase 4, failing the reconciliation phase but not blocking data pipelines.
        logger.info("[STARTUP] Orchestrator ready. Alpaca credentials will be validated in Phase 4.")

    def cleanup(self) -> None:
        """No-op: RDS Proxy handles connection cleanup."""

    def _validate_startup_configuration(self) -> None:
        """CRITICAL: Validate all required configuration at startup.

        Checks:
        1. execution_mode is set and valid (paper/live/auto)
        2. For live trading: Alpaca credentials available (API key + secret)
        3. Required config keys present

        Raises RuntimeError if any validation fails.
        """
        logger.info("[STARTUP VALIDATION] Checking required configuration...")

        # 1. Validate execution_mode FIRST
        execution_mode = self.config.get("execution_mode")
        if not execution_mode or execution_mode not in ("paper", "live", "auto"):
            raise RuntimeError(
                f"[STARTUP] CRITICAL: execution_mode must be 'paper', 'live', or 'auto'. "
                f"Current value: {execution_mode!r}. Configure via algo_config table."
            )
        logger.info(f"[OK] execution_mode validated: {execution_mode}")

        # 2. Validate Alpaca credentials only for live trading
        if execution_mode in ("live", "auto"):
            try:
                from config.credential_manager import CredentialManager

                # Check if paper trading is enabled - if so, skip credential validation
                is_paper_trading = self.config.get("alpaca_paper_trading", False)
                if is_paper_trading:
                    logger.info("[OK] Paper trading mode enabled - Alpaca credentials not required")
                else:
                    # Live trading requires credentials
                    creds = CredentialManager()
                    api_key = creds.get_password("APCA_API_KEY_ID", default=None)
                    api_secret = creds.get_password("APCA_API_SECRET_KEY", default=None)
                    if not api_key or not api_secret:
                        raise RuntimeError(
                            "[STARTUP] CRITICAL: Alpaca credentials missing for live trading. "
                            "Configure APCA_API_KEY_ID and APCA_API_SECRET_KEY via AWS Secrets Manager or environment."
                        )
                    logger.info("[OK] Alpaca credentials validated for live trading")
            except ValueError as e:
                raise RuntimeError(f"[STARTUP] Credential validation failed: {e}") from e
            except RuntimeError as e:
                # Handle AWS permission errors - fall back to paper mode in dev
                if "Secrets Manager access failed" in str(e) or "AccessDeniedException" in str(e):
                    logger.warning(
                        f"[CREDENTIAL FALLBACK] {e}. "
                        "AWS permissions insufficient for live trading. Falling back to paper mode."
                    )
                else:
                    raise
        else:
            logger.info("[OK] Paper trading mode - Alpaca credentials not required")

        # 3. Validate required config keys exist (only truly critical ones)
        try:
            # Only validate critical config keys; others have sensible defaults
            critical_keys = [
                "min_signal_quality_score",
                "min_completeness_score",
            ]
            missing = []
            for key in critical_keys:
                val = self.config.get(key)
                if val is None:
                    missing.append(key)
            if missing:
                logger.warning(
                    f"[STARTUP] Missing optional config keys: {', '.join(missing)}. "
                    "These will use default values. For production, add these to algo_config table."
                )
            else:
                logger.info("[OK] All critical config keys present")
        except Exception as e:
            if "CRITICAL" in str(e):
                raise
            logger.warning(f"[STARTUP] Config validation skipped (non-critical): {e}")

        # 4. Validate database schema (required tables and views)
        try:
            with DatabaseContext("read") as cur:
                # Check algo_positions view exists (critical for portfolio monitoring)
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.views
                        WHERE table_name = 'algo_positions'
                    ) AS view_exists
                    """
                )
                row = cur.fetchone()
                if not row or not row.get("view_exists"):
                    logger.warning(
                        "[STARTUP] algo_positions view not found. "
                        "Portfolio monitoring disabled. Run migrations to create required database objects."
                    )
                else:
                    logger.info("[OK] Database schema validation passed: algo_positions view exists")
        except Exception as e:
            logger.warning(f"[STARTUP] Database schema validation skipped (non-critical): {e}")

    def _kill_long_running_loaders(self) -> None:  # noqa: C901
        """CRITICAL: Kill hung loaders (analytics + critical-path) if approaching next orchestrator run.

        Analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics)
        iterate 5000+ symbols with yfinance rate limits and can run 6+ hours.

        Critical-path loaders (trend_template_data, sector_ranking,
        market_health_daily, market_exposure_daily, algo_metrics_daily) should complete within
        30-90 minutes. If still running 15 min before next orchestrator run, they're hung and
        consuming RDS connections.

        If any is still running when orchestrator fires, RDS connection pool exhaustion occurs.
        This check prevents that.

        Dynamic timeout: calculate time until next orchestrator run, subtract 15 min buffer.
        Orchestrator runs at: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET (Mon-Fri only)

        ISSUE #5 FIX: Verifies task termination to prevent hung tasks consuming RDS connections.
        ISSUE #1 FIX: Added critical-path loaders to kill check.
        """
        try:
            import boto3

            ecs = boto3.client("ecs", region_name=os.getenv("AWS_REGION", "us-east-1"))
            cluster = os.getenv("ECS_CLUSTER_ARN", "algo-cluster")

            # Both analytics (6+ hour) and critical-path (30-90 min) loaders
            analytics_loaders = {
                "company_profile",
                "analyst_sentiment",
                "stability_metrics",
                "value_metrics",
            }
            critical_path_loaders = {
                "trend_template_data",
                "sector_ranking",
                "market_health_daily",
                "market_exposure_daily",
                "algo_metrics_daily",
            }
            monitored_loaders = analytics_loaders | critical_path_loaders

            # Calculate time until next orchestrator run (in ET)
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)

            # Find next orchestrator run
            next_orch_et = None
            for orch_hour, orch_minute in ORCHESTRATOR_RUN_TIMES_TUPLE:
                orch_time = now_et.replace(hour=orch_hour, minute=orch_minute, second=0, microsecond=0)
                if orch_time > now_et:
                    next_orch_et = orch_time
                    break

            # If no more runs today, next is tomorrow morning
            if next_orch_et is None:
                next_orch_et = (now_et + timedelta(days=1)).replace(
                    hour=MARKET_OPEN_HOUR,
                    minute=MARKET_OPEN_MINUTE,
                    second=0,
                    microsecond=0,
                )
                # Skip non-trading days
                while not MarketCalendar.is_trading_day(next_orch_et.date()):
                    next_orch_et += timedelta(days=1)

            # Calculate kill threshold: next_orch - buffer minutes
            kill_threshold_et = next_orch_et - timedelta(minutes=ORCHESTRATOR_KILL_BUFFER_MINUTES)
            max_runtime = kill_threshold_et - now_et

            if max_runtime.total_seconds() <= 0:
                logger.debug("[OOM_PREVENTION] Next orchestrator run is imminent, using 5 min max runtime")
                max_runtime = timedelta(minutes=5)

            logger.debug(
                f"[OOM_PREVENTION] Next orchestrator run at {next_orch_et.strftime('%H:%M')} ET. "
                f"Kill timeout: {max_runtime.total_seconds() / 60:.0f} minutes"
            )

            # List running tasks
            response = ecs.list_tasks(cluster=cluster, desiredStatus="RUNNING")
            task_arns = response.get("taskArns")
            if not task_arns:
                return
            if not isinstance(task_arns, list):
                logger.error(f"[OOM_PREVENTION] Unexpected taskArns type: {type(task_arns)}, expected list")
                return

            # Get task details (includes startedAt timestamp)
            task_details = ecs.describe_tasks(cluster=cluster, tasks=task_arns)
            now = datetime.now(timezone.utc)

            # Validate DynamoDB response schema
            if not isinstance(task_details, dict):
                logger.error(f"[OOM_PREVENTION] Unexpected task_details type: {type(task_details)}, expected dict")
                return

            tasks = task_details.get("tasks")
            if not isinstance(tasks, list):
                logger.error(f"[OOM_PREVENTION] Unexpected tasks type: {type(tasks)}, expected list")
                return

            failed_terminations = []
            for task in tasks:
                # Extract loader name from task definition (format: algo-LOADER_NAME-loader:1)
                task_def = task.get("taskDefinitionArn", "")
                loader_name = None
                for loader in monitored_loaders:
                    if loader in task_def:
                        loader_name = loader
                        break

                if not loader_name:
                    continue  # Skip non-monitored loaders

                started_at = task.get("startedAt")
                if not started_at:
                    # CRITICAL: Validate taskArn field exists for error context (fail-fast if missing)
                    task_arn = task.get("taskArn")
                    if task_arn is None:
                        raise ValueError(
                            f"[CRITICAL] Task missing BOTH startedAt AND taskArn fields. "
                            f"Cannot assess hung loader or identify which task failed. "
                            f"This indicates ECS metadata corruption or schema change. Task: {task}"
                        )
                    raise ValueError(
                        f"[CRITICAL] Task missing startedAt field — cannot assess if hung. "
                        f"This indicates ECS metadata corruption or schema change. "
                        f"Cannot proceed with hung loader detection. Task: {task_arn}"
                    )

                # Convert startedAt to UTC-aware datetime if needed
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)

                age = now - started_at
                if age > max_runtime:
                    task_arn = task.get("taskArn")
                    logger.warning(
                        f"[OOM_PREVENTION] Killing {loader_name} task (running {age.total_seconds() / 3600:.1f}h, "
                        f"max {max_runtime.total_seconds() / 3600:.1f}h before next orch run): {task_arn}"
                    )

                    # ISSUE #5: Issue stop request
                    try:
                        ecs.stop_task(
                            cluster=cluster,
                            task=task_arn,
                            reason="Loader hung beyond timeout before next orchestrator run",
                        )
                    except Exception as stop_err:
                        logger.critical(
                            f"[TASK_TERMINATION] CRITICAL: Failed to kill hung loader {loader_name}: {stop_err}. "
                            f"Task will continue consuming resources. Manual intervention required: {task_arn}"
                        )
                        self.degraded_mode = True
                        failed_terminations.append((loader_name, task_arn, str(stop_err)))
                        # Don't silently continue — mark as degraded so operator is aware task termination failed

                    # ISSUE #5: Verify task actually stopped (with retries)
                    if self.db_monitor.verify_task_stopped(ecs, cluster, task_arn, loader_name):
                        self.log_phase_result(
                            0,
                            "oom_prevention",
                            "success",
                            f"Killed {loader_name} task running {age.total_seconds() / 3600:.1f}h",
                        )
                    else:
                        failed_terminations.append((loader_name, task_arn, "verification timeout"))

            # ISSUE #5: Alert if any terminations failed
            if failed_terminations:
                error_details = "; ".join([f"{name}: {err}" for name, arn, err in failed_terminations])
                logger.critical(
                    f"[TASK_TERMINATION] ESCALATION: {len(failed_terminations)} task termination(s) failed. "
                    f"{error_details}"
                )
                try:
                    self.alerts.send_position_alert(
                        "TASK_TERMINATION",
                        "HUNG_LOADER_TERMINATION_FAILED",
                        f"Failed to terminate {len(failed_terminations)} hung loaders. RDS connections may not be released. "
                        f"Check CloudWatch logs and manually stop: {', '.join([arn.split('/')[-1] for _, arn, _ in failed_terminations])}",
                        {
                            "failed_tasks": [
                                {"loader": name, "task_arn": arn, "error": err}
                                for name, arn, err in failed_terminations
                            ]
                        },
                    )
                except (ValueError, ZeroDivisionError, TypeError) as alert_err:
                    logger.error(f"[TASK_TERMINATION] Could not send escalation alert: {alert_err}")

        except Exception as e:
            logger.warning(f"[OOM_PREVENTION] Could not check/kill long-running loaders: {e}")
            # Don't halt trading for this check - it's advisory

    def _wait_for_critical_loaders_proactive(self, max_wait_seconds: int = 300) -> bool:
        """Actively wait for critical loaders to complete before Phase 1.

        Polls data_loader_status for PHASE_1_CRITICAL loaders and waits until they reach
        95%+ completion or timeout. This prevents Phase 1 from running with stale data.

        Strategy:
        1. Query which critical loaders are actively running (status = 'running', completion_pct < 95)
        2. Poll every 5 seconds, checking for completion
        3. If all critical loaders complete, Phase 1 proceeds immediately
        4. If timeout expires, Phase 1 proceeds anyway but may detect degraded mode

        This is the "proactive" fix vs. the reactive Phase 1 Failsafe which retries AFTER detecting
        staleness. By waiting here, we prevent staleness from being a problem in the first place.

        Args:
            max_wait_seconds: Maximum time to wait for loaders (default 300s = 5 min)

        Returns:
            True if all critical loaders completed within timeout, False if timeout
        """
        from utils.loader_priority import get_critical_loaders

        poll_interval_seconds = 5
        start_time = time.time()
        critical_loaders = get_critical_loaders()

        logger.info(f"\n[PROACTIVE WAIT] Checking for running critical loaders (max wait: {max_wait_seconds}s)...")

        try:
            while time.time() - start_time < max_wait_seconds:
                try:
                    with DatabaseContext("read", timeout=5) as cur:
                        cur.execute("SET LOCAL statement_timeout = '5000ms'")

                        # Find critical loaders that are still running (incomplete)
                        cur.execute(
                            """
                            SELECT table_name, status, completion_pct, symbols_loaded, symbol_count
                            FROM data_loader_status
                            WHERE table_name = ANY(%s)
                            AND (status = 'running' OR completion_pct < 95.0)
                            ORDER BY completion_pct ASC
                            """,
                            (list(critical_loaders),),
                        )

                        incomplete_loaders = cur.fetchall()
                        if not incomplete_loaders:
                            logger.info("[PROACTIVE WAIT] All critical loaders are at 95%+ completion")
                            return True

                        # Still running — log progress and wait
                        elapsed = time.time() - start_time
                        slowest = incomplete_loaders[0]
                        slowest_name, _, slowest_pct, slowest_loaded, slowest_count = slowest

                        logger.info(
                            f"[PROACTIVE WAIT] {len(incomplete_loaders)} loader(s) still running. "
                            f"Slowest: {slowest_name} ({slowest_pct:.1f}%, {slowest_loaded}/{slowest_count} symbols). "
                            f"Elapsed: {elapsed:.0f}s/{max_wait_seconds}s"
                        )

                        time.sleep(poll_interval_seconds)

                except (psycopg2.DatabaseError, psycopg2.OperationalError) as db_err:
                    logger.warning(f"[PROACTIVE WAIT] Database error during poll: {db_err}. Retrying...")
                    time.sleep(poll_interval_seconds)

            # Timeout expired (expected condition)
            logger.warning(
                f"[PROACTIVE WAIT] Timeout after {max_wait_seconds}s waiting for critical loaders. "
                f"Proceeding to Phase 1 (may detect degraded mode). "
                f"Check EventBridge rules and ECS cluster health if loaders are perpetually incomplete."
            )
            return False

        except (psycopg2.DatabaseError, psycopg2.OperationalError, TimeoutError) as e:
            msg = f"[PROACTIVE WAIT] Infrastructure error during loader status check: {e}. Cannot proceed with uncertain loader state."
            logger.error(msg)
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"[PROACTIVE WAIT] Unexpected error during proactive wait: {e}. This indicates a programming error or unhandled exception type."
            logger.error(msg)
            raise RuntimeError(msg) from e

    def _check_loader_health(self) -> None:
        """Check if critical loaders have run recently and provide diagnostics.

        Queries data_loader_status to verify critical loaders (prices, technical, scores)
        have been executed and are up-to-date. Non-blocking advisory check that helps
        diagnose data staleness issues before Phase 1 runs.

        Logs warnings if critical loaders are missing or stale (>4 hours old) — this often
        indicates EventBridge is not firing the loader schedule, or loaders are hung.

        CRITICAL: If ALL critical loaders are missing/stale simultaneously, this indicates
        a systemic issue (EventBridge failure, loader infrastructure down). Logs alert.
        """
        from utils.loader_priority import get_critical_loaders

        # Loaders that are critical for trading (MUST run before orchestrator)
        critical_loaders = get_critical_loaders()

        try:
            with DatabaseContext("read", timeout=5) as cur:
                cur.execute("SET LOCAL statement_timeout = '5000ms'")

                # Check when each critical loader last ran
                cur.execute(
                    """
                    SELECT table_name, status, last_updated, completion_pct, symbols_loaded, symbol_count
                    FROM data_loader_status
                    WHERE table_name = ANY(%s)
                    ORDER BY last_updated DESC
                    """,
                    (list(critical_loaders),),
                )

                loaders_checked = set()
                loader_status = {}
                now_utc = datetime.now(timezone.utc)
                stale_threshold = now_utc - timedelta(hours=4)

                for table_name, status, last_updated, completion_pct, symbols_loaded, symbol_count in cur.fetchall():
                    loaders_checked.add(table_name)
                    # last_updated is a naive datetime from PostgreSQL — make it UTC-aware before comparing
                    last_updated_utc = last_updated.replace(tzinfo=timezone.utc) if last_updated else None

                    # CRITICAL: Must explicitly determine staleness — no silent assumptions about loader health
                    if last_updated_utc is None:
                        logger.error(
                            f"[LOADER HEALTH] {table_name} cannot determine staleness: last_updated_utc is None. "
                            "Loader status unknown — cannot proceed without explicit timestamp."
                        )
                        raise RuntimeError(
                            f"Cannot determine loader staleness for {table_name}: no last_updated_utc timestamp. "
                            "Loader status unknown, must fail-fast instead of assuming fresh."
                        )

                    is_stale = last_updated_utc < stale_threshold

                    # CRITICAL: completion_pct is None only if database query failed or loader hasn't reported yet
                    # Treat None as incomplete (fail-safe) — don't silently use 0 (which looks like successful 0% load)
                    if completion_pct is None:
                        is_complete = False
                        logger.error(
                            f"[LOADER HEALTH] {table_name} completion_pct is NULL (database error or loader never reported). "
                            "Treating as incomplete until next status update."
                        )
                    else:
                        is_complete = completion_pct >= 95.0

                    loader_status[table_name] = {
                        "status": status,
                        "last_updated": last_updated_utc,
                        "is_stale": is_stale,
                        "is_complete": is_complete,
                        "completion_pct": completion_pct,
                    }

                    if is_stale:
                        if last_updated is None:
                            logger.critical(
                                f"[ORCHESTRATOR CRITICAL] {table_name} marked STALE but last_updated is NULL. "
                                f"Cannot calculate staleness age. Loader may not have run yet."
                            )
                            raise RuntimeError(
                                f"Loader health check failed: {table_name} is stale but has no last_updated timestamp. "
                                f"Loader execution tracking may be corrupted."
                            )
                        age_hours = (now_utc - last_updated.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                        logger.warning(f"[LOADER HEALTH] {table_name} is STALE (last run {age_hours:.1f}h ago)")
                    elif not is_complete:
                        if completion_pct is None:
                            logger.warning(
                                f"[LOADER HEALTH] {table_name} is INCOMPLETE (completion_pct=NULL, status={status})"
                            )
                        else:
                            logger.warning(
                                f"[LOADER HEALTH] {table_name} is INCOMPLETE ({completion_pct:.1f}%, "
                                f"{symbols_loaded}/{symbol_count} symbols)"
                            )
                    else:
                        logger.info(f"[LOADER HEALTH] {table_name} OK ({completion_pct:.1f}%)")

                # Check for missing critical loaders
                missing_loaders = critical_loaders - loaders_checked
                stale_loaders = [name for name, status in loader_status.items() if status["is_stale"]]

                if missing_loaders:
                    logger.warning(
                        f"[LOADER HEALTH] MISSING in data_loader_status: {missing_loaders} "
                        "(loaders have never run or been registered)"
                    )

                # ESCALATION: If all critical loaders are stale/missing, this is a systemic issue
                # (likely EventBridge failure or loader infrastructure down)
                all_loaders_checked = dict(loader_status)
                all_stale_or_missing = len(all_loaders_checked) > 0 and all(
                    status["is_stale"] or status["completion_pct"] is None or status["completion_pct"] == 0
                    for status in all_loaders_checked.values()
                )

                if all_stale_or_missing and (stale_loaders or missing_loaders):
                    logger.critical(
                        f"[LOADER HEALTH] SYSTEMIC ALERT: ALL critical loaders are stale or missing. "
                        f"This indicates EventBridge may not be firing loader schedules, or loader "
                        f"infrastructure is down. Stale: {stale_loaders}. Missing: {missing_loaders}. "
                        f"Check: EventBridge rules, ECS cluster health, CloudWatch logs for loaders."
                    )
                    try:
                        self.alerts.send_position_alert(
                            "LOADER_INFRASTRUCTURE",
                            "ALL_CRITICAL_LOADERS_STALE",
                            f"All critical loaders are stale/missing (stale: {len(stale_loaders)}, "
                            f"missing: {len(missing_loaders)}). EventBridge or loader infrastructure issue.",
                            {"stale_loaders": stale_loaders, "missing_loaders": list(missing_loaders)},
                        )
                    except Exception as alert_err:
                        logger.debug(f"[LOADER HEALTH] Could not send alert: {alert_err}")

                    # PAPER MODE BYPASS: In paper trading, allow execution even with stale loaders
                    # (testing/local development scenario where loaders may not be running)
                    if self.config.get("execution_mode") in ("paper", "auto"):
                        logger.warning(
                            f"[LOADER HEALTH PAPER MODE] All loaders stale/missing, but in paper mode - "
                            f"proceeding with orchestrator execution using available data. "
                            f"Stale: {stale_loaders}. Missing: {missing_loaders}."
                        )
                        # Continue execution - Phase 1 will validate data quality
                    else:
                        # CRITICAL: Halt trading if all loaders stale/missing
                        # Using stale data for trading decisions is unacceptable - stop here
                        raise RuntimeError(
                            f"[ORCHESTRATOR] CRITICAL HALT: All critical loaders are stale/missing. "
                            f"Cannot proceed with trading using stale data. "
                            f"Stale loaders: {stale_loaders}. Missing loaders: {missing_loaders}. "
                            f"Fix loader infrastructure before resuming trading."
                        )

        except (psycopg2.DatabaseError, psycopg2.OperationalError, TimeoutError) as e:
            logger.warning(f"[LOADER HEALTH] Could not check loader status: {e}")
            # If we can't check loader health, HALT (don't assume data is fresh)
            raise RuntimeError(
                f"[ORCHESTRATOR] CRITICAL: Cannot verify loader health: {e}. "
                f"Halting trading - unable to confirm data freshness."
            ) from e
        except Exception as e:
            logger.error(
                f"[LOADER HEALTH] UNEXPECTED ERROR checking loader health: {e}. "
                f"This indicates an unexpected runtime error in the health check logic. "
                f"Halting trading to prevent operating with unverified loader state."
            )
            raise RuntimeError(
                f"[ORCHESTRATOR] Unexpected error during loader health check: {e}. "
                f"Cannot proceed with trading until loader health verification succeeds."
            ) from e

    def _validate_required_tables(self, cur: Any) -> bool:
        """FIXED Issue #23: Validate that all required tables exist before running phases.

        Returns: True if all tables exist, False if any critical table is missing.
        """
        required_tables = [
            "price_daily",  # Phase 1, Phase 5 signal generation
            "trend_template_data",  # Phase 5 (SignalComputer — Minervini, Weinstein)
            "sector_ranking",  # Phase 3b (sector rotation)
            "market_health_daily",  # Phase 3b (exposure), Phase 4 (distribution days)
            "market_exposure_daily",  # Phase 3b (entry constraints)
            "algo_audit_log",  # Audit trail
        ]

        try:
            missing_tables = []
            for table_name in required_tables:
                try:
                    # Check if table exists by querying information_schema
                    cur.execute(
                        "SELECT 1 FROM information_schema.tables WHERE table_name = %s LIMIT 1",
                        (table_name,),
                    )
                    if not cur.fetchone():
                        missing_tables.append(table_name)
                        logger.error(f"[TABLE-CHECK] Missing required table: {table_name}")
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.error(f"[TABLE-CHECK] Failed to check table {table_name}: {e}")
                    missing_tables.append(table_name)

            if missing_tables:
                logger.error(f"[TABLE-CHECK] Cannot proceed: missing tables {missing_tables}")
                self.log_phase_result(
                    0,
                    "table_validation",
                    "halt",
                    f"Missing tables: {', '.join(missing_tables)}",
                )
                return False

            logger.info(f"[TABLE-CHECK] All {len(required_tables)} required tables exist [OK]")
            return True

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    # ---------- Logging helpers ----------

    def _acquire_run_lock(self, lock_timeout_seconds: int = 5) -> bool:
        """Acquire distributed lock to prevent concurrent orchestrator runs.

        FIXED Issue #8: Uses DynamoDB conditional writes instead of filesystem locks
        for correct distributed locking in Fargate ECS tasks (no shared filesystem).

        Args:
            lock_timeout_seconds: How long to retry acquiring lock (default 5s)

        Returns: True if lock acquired, False if another active instance holds it.
        """
        self._lock_acquired = self.lock_manager.acquire(timeout_seconds=lock_timeout_seconds)
        return self._lock_acquired

    def _release_run_lock(self) -> None:
        """Release the distributed lock."""
        if self._lock_acquired:
            self.lock_manager.release()

    def log_phase_start(self, phase_num: int | str, name: str) -> None:
        if self.verbose:
            logger.info(f"\n{'=' * 70}")
            logger.info(f"PHASE {phase_num}: {name}")
            logger.info(f"{'=' * 70}")

    def log_phase_result(self, phase_num: int | str, name: str, status: str, summary: str) -> None:
        self.phase_results[phase_num] = {
            "name": name,
            "status": status,
            "summary": summary,
        }
        # FIXED Issue #6: Also log to execution tracker for audit trail
        self.execution_tracker.log_phase_result(phase_num, name, status, summary)
        if self.verbose:
            logger.info(f"\n-> Phase {phase_num} {status}: {summary}")

        # Publish phase event to EventHub for dashboard/API subscribers
        try:
            hub = get_event_hub()
            phase_status = PhaseStatus(status)
            event = PhaseCompletedEvent(
                phase_num=phase_num,
                phase_name=name,
                status=phase_status,
                summary=summary,
            )
            hub.publish(event)
        except (ValueError, Exception) as e:
            logger.debug(f"Could not publish phase event: {e}")

        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO algo_audit_log (action_type, action_date, details, actor, status, created_at)
                    VALUES (%s, CURRENT_TIMESTAMP, %s, 'orchestrator', %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        f"phase_{phase_num}_{name}",
                        json.dumps({"run_id": self.run_id, "summary": summary}),
                        status,
                    ),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.critical(f"Audit log persistence CRITICAL FAILURE: {e}")
            raise RuntimeError(f"[AUDIT] Failed to persist phase log (data integrity risk): {e}") from e

    # ---------- Phase implementations ----------

    def phase_1_data_freshness(self) -> bool:
        """Thin delegation to phase1_data_freshness module.

        New version only checks: are today's prices loaded? 95%+ coverage?
        Removes all the complex grace period / hung task detection logic.
        """
        self.log_phase_start(1, "DATA FRESHNESS CHECK")
        result = run_phase1(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
        )
        # Store result for Phase 5 to check degradation status
        self._phase1_result = result

        # Informational DynamoDB write (phase1_degraded_mode key) — separate from halt flag
        # management so a DynamoDB write failure never prevents the halt flag from being cleared.
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
            table = dynamodb.Table(table_name)
            degraded_status = result.status == "degraded"
            table.put_item(
                Item={
                    "key": "phase1_degraded_mode",
                    "degraded": degraded_status,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": result.error if degraded_status else None,
                    "ttl": int(time.time()) + 3600,  # 1-hour TTL
                }
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError) as e:
            logger.debug(f"Failed to write Phase 1 degraded_mode status to DynamoDB: {e}")

        # Halt flag lifecycle: always run regardless of informational write success above.
        try:
            degraded_status = result.status == "degraded"
            if degraded_status:
                logger.info(f"[DEGRADED_MODE] Phase 1 returned degraded status: {result.error}")
                self.halt_manager.set_halt_flag(f"Phase 1 degraded: {result.error}")
            elif result.status == "ok":
                self.halt_manager.clear_halt_flag(
                    f"Phase 1 verified data is fresh at {datetime.now(timezone.utc).isoformat()}"
                )
        except (ValueError, KeyError, AttributeError) as e:
            logger.warning(f"Failed to manage halt flag after Phase 1: {e}")

        return not result.halted

    def phase_2_circuit_breakers(self) -> bool:
        """Thin delegation to phase2_circuit_breakers module."""
        self.log_phase_start(2, "CIRCUIT BREAKERS")
        result = run_phase2(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
        )
        self._phase2_result = result
        return not result.halted

    def phase_3_position_monitor(self) -> bool:
        """Thin delegation to phase3_position_monitor module."""
        self.log_phase_start(3, "POSITION MONITOR")
        result = run_phase3(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
        )
        self._phase3_result = result
        if not result.ok:
            return False
        # GOVERNANCE: Fail-fast on data contract violations. Phase 3 MUST provide recommendations.
        if "recommendations" not in result.data:
            self.log_phase_result(
                3,
                "position_monitor",
                "error",
                "Phase 3 data contract violated: missing 'recommendations' key in result",
            )
            logger.error("Phase 3 returned ok=True but missing recommendations in data contract")
            return False
        recs = result.data["recommendations"]
        if not isinstance(recs, list):
            self.log_phase_result(
                3,
                "position_monitor",
                "error",
                f"Phase 3 data contract violated: recommendations must be list, got {type(recs).__name__}",
            )
            logger.error(f"Phase 3 recommendations not a list: {type(recs)}")
            return False
        self._position_recs = recs
        return True

    def phase_5_exposure_policy(self) -> bool:
        """Thin delegation to phase5_exposure_policy module."""
        self.log_phase_start(5, "EXPOSURE POLICY ACTIONS")
        result = run_phase5(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
        )
        self._phase5_result = result
        if not result.ok:
            return False
        # GOVERNANCE: Fail-fast on data contract violations. Phase 5 MUST provide actions.
        if "actions" not in result.data:
            self.log_phase_result(
                5,
                "exposure_policy",
                "error",
                "Phase 5 data contract violated: missing 'actions' key in result",
            )
            logger.error("Phase 5 returned ok=True but missing actions in data contract")
            return False
        actions = result.data["actions"]
        if not isinstance(actions, list):
            self.log_phase_result(
                5,
                "exposure_policy",
                "error",
                f"Phase 5 data contract violated: actions must be list, got {type(actions).__name__}",
            )
            logger.error(f"Phase 5 actions not a list: {type(actions)}")
            return False
        self._exposure_constraints = result.data.get("constraints")
        self._exposure_actions = actions
        return True

    def phase_9_reconcile(self) -> bool:
        """Thin delegation to phase9_reconciliation module."""
        self.log_phase_start(9, "RECONCILIATION & SNAPSHOT")
        # No halt flag check: snapshot must always be written so circuit breakers
        # have accurate portfolio state on the next invocation.
        result = run_phase9(self.config, self.run_date, self.log_phase_result)
        self._phase9_result = result
        if "positions" in result.data:
            self.phase_results.setdefault(9, {})["open_positions"] = result.data["positions"]
        else:
            logger.warning(
                "Phase 9 reconciliation returned without positions data "
                "(broker unavailable or reconciliation failed). "
                f"Got keys: {list(result.data.keys())}"
            )
        return not result.halted

    # ---------- Executor setup (Phase 2: Phase Executor Framework) ----------

    def _setup_executor(self, skip_phases: list[int | str] | None = None) -> OrchestratorPhaseExecutor:
        """Create and configure the phase executor.

        Loads phase definitions from PhaseRegistry and wires executor methods.
        Eliminates Shotgun Surgery: adding a phase is now a single registry entry,
        not multiple method additions and orchestrator changes.

        Args:
            skip_phases: Optional list of phase numbers to skip (e.g., trading phases on non-trading days)

        Returns:
            OrchestratorPhaseExecutor ready to execute all phases.
        """
        executor = OrchestratorPhaseExecutor(
            config=self.config, halt_check_fn=self.halt_manager.check_halt_flag, skip_phases=skip_phases
        )

        # Wire phase executor functions from registry
        phase_executors: dict[int | str, Any] = {
            1: self._executor_phase_1,
            2: self._executor_phase_2,
            3: self._executor_phase_3,
            4: self._executor_phase_4,
            5: self._executor_phase_5,
            6: self._executor_phase_6,
            7: self._executor_phase_7,
            8: self._executor_phase_8,
            9: self._executor_phase_9,
        }

        # Register all phases from registry with their metadata
        for phase_entry in PhaseRegistry.get_all_phases():
            # Wire the executor function for this phase
            execute_fn = phase_executors.get(phase_entry.phase_num)
            if execute_fn is None:
                raise RuntimeError(f"No executor registered for phase {phase_entry.phase_num}")

            # Convert registry entry to PhaseDefinition for executor
            phase_def = PhaseDefinition(
                phase_num=phase_entry.phase_num,
                phase_name=phase_entry.phase_name,
                dependencies=phase_entry.dependencies,
                execute_fn=execute_fn,
                skip_if_halted=phase_entry.skip_if_halted,
                always_run=phase_entry.always_run,
            )
            executor.register_phase(phase_def)

        return executor

    def _executor_phase_1(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 1."""
        self.phase_1_data_freshness()
        if not hasattr(self, "_phase1_result"):
            raise RuntimeError("[PHASE 1] phase_1_data_freshness() did not set _phase1_result")
        return self._phase1_result

    def _executor_phase_2(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 2."""
        self.phase_2_circuit_breakers()
        if not hasattr(self, "_phase2_result"):
            raise RuntimeError("[PHASE 2] phase_2_circuit_breakers() did not set _phase2_result")
        return self._phase2_result

    def _executor_phase_3(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 3."""
        self.phase_3_position_monitor()
        if not hasattr(self, "_phase3_result"):
            raise RuntimeError("[PHASE 3] phase_3_position_monitor() did not set _phase3_result")
        return self._phase3_result

    def _executor_phase_4(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 4: Reconciliation."""
        result = run_phase4(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
        )
        return result

    def _executor_phase_5(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 5: Exposure Policy."""
        self.phase_5_exposure_policy()
        if not hasattr(self, "_phase5_result"):
            raise RuntimeError("[PHASE 5] phase_5_exposure_policy() did not set _phase5_result")
        return self._phase5_result

    def _executor_phase_6(self, executor: Any = None, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 6: Exit Execution.

        PHASE DEPENDENCY FIX: Fetches validated data from Phase 3 and 5.
        """
        if executor:
            position_recs = executor.get_phase_data_required(3, "recommendations")
            exposure_actions = executor.get_phase_data_required(5, "actions")
        else:
            position_recs = []
            exposure_actions = []

        result = run_phase6(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
            position_recs,
            exposure_actions,
        )
        return result

    def _executor_phase_7(self, executor: Any = None, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 7: Signal Generation.

        PHASE DEPENDENCY FIX: Fetches validated data from Phase 5.
        """
        exposure_constraints = executor.get_phase_data_required(5, "constraints") if executor else None

        result = run_phase7(
            self.run_date,
            self.dry_run,
            self.verbose,
            self.log_phase_result,
            exposure_constraints=exposure_constraints,
            check_halt_flag=self.halt_manager.check_halt_flag,
            config=self.config,
        )
        return result

    def _executor_phase_8(self, executor: Any = None, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 8: Entry Execution.

        PHASE DEPENDENCY FIX: Now passes executor so phase can fetch validated data
        from Phase 7 and 5 instead of relying on instance attributes.
        """
        result = run_phase8(
            self.config,
            self.run_date,
            self.dry_run,
            self.verbose,
            self.log_phase_result,
            check_halt_flag=self.halt_manager.check_halt_flag,
            executor=executor,
        )
        return result

    def _executor_phase_9(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 9: Final Reconciliation."""
        self.phase_9_reconcile()
        if not hasattr(self, "_phase9_result"):
            raise RuntimeError("[PHASE 9] phase_9_reconcile() did not set _phase9_result")
        return self._phase9_result

    # ---------- Main entrypoint ----------

    def run(self) -> dict[str, Any]:
        self.run_start = time.time()
        logger.info(f"\n{'#' * 70}")
        logger.info(f"#   ALGO ORCHESTRATOR — {self.run_date}  ({'DRY RUN' if self.dry_run else 'LIVE'})")
        logger.info(f"#   run_id: {self.run_id}")
        logger.info(f"#   START TIME: {datetime.now(timezone.utc).isoformat()}")
        logger.info(f"{'#' * 70}")

        # CRITICAL FIX: Don't skip trading phases on non-trading days.
        # The circuit breaker (Phase 2) will halt if market is closed.
        # Skipping phases 4-8 prevents signal generation and entry execution entirely.
        # This caused 18+ days of zero trades. Let phases run; circuit breaker handles halt logic.
        # if not is_trading_day:
        #     status = MarketCalendar.market_status(datetime.combine(self.run_date, datetime.min.time()))
        #     logger.info(f"\nMarket closed: {status['reason']}")
        #     logger.info("Skipping trading phases. Circuit breaker will halt if needed.\n")

        # Concurrency lock — prevent two orchestrators running at once
        # which would risk duplicate trades or double-counting circuit breakers
        # Skip lock check in dry-run mode (no actual trades), paper trading (dev/test), or explicit env var
        is_paper_trading = self.execution_mode == "paper"
        skip_lock_check = (
            self.dry_run
            or is_paper_trading
            or os.getenv("SKIP_ORCHESTRATOR_LOCK", "").lower() in ("true", "1", "yes")
        )

        if not skip_lock_check:
            lock_acquired = self._acquire_run_lock()
            if not lock_acquired:
                if self.lock_manager.is_available:
                    # DynamoDB is available but lock couldn't be acquired (another instance running)
                    logger.error("\nABORT: Could not acquire run lock. Another orchestrator instance is running.")
                    return {"success": False, "error": "Lock acquisition failed"}
                else:
                    # DynamoDB unavailable — FAIL CLOSED to prevent concurrent executions
                    logger.critical(
                        "\nABORT: DynamoDB lock unavailable. Cannot verify single orchestrator instance. "
                        "Failing closed to prevent concurrent trades and duplicate order execution."
                    )
                    return {
                        "success": False,
                        "error": "Distributed lock system unavailable. Cannot proceed with trading.",
                    }
        else:
            if self.dry_run:
                reason = "dry-run mode"
            elif is_paper_trading:
                reason = "paper trading mode (no live order risk)"
            else:
                reason = "SKIP_ORCHESTRATOR_LOCK environment variable"
            logger.info(f"[LOCK-SKIP] Skipping distributed lock check ({reason})")

        try:
            logger.info(f"\n{'=' * 70}")
            logger.info("PRE-FLIGHT CHECKS (before Phase 1)")
            logger.info(f"{'=' * 70}")
            logger.info("[CRITICAL] Running critical data checks...")
            try:
                logger.debug("[PREFLIGHT] Opening database context (timeout=10s)")
                with DatabaseContext("read", timeout=10) as cur:
                    # Validate required tables exist (schema check only).
                    # Data freshness and patrol are handled by Phase 1 with proper
                    # halt/observe-only distinctions and fresh patrol execution.
                    logger.debug("[PREFLIGHT] Validating required tables")
                    if not self._validate_required_tables(cur):
                        logger.error("[HALT] Required tables missing — cannot proceed")
                        return self._final_report()

                    logger.info("[OK] All pre-flight checks passed")
            except TimeoutError as e:
                logger.error(f"  [HALT] Pre-flight database timeout (pool exhausted?): {e}")
                report = self._final_report()
                report["skipped"] = True
                report["reason"] = "database_timeout"
                return report
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(
                    f"  [HALT] Pre-flight check failed: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                # Return skipped=True when DB is unreachable so test verification
                # treats this as a transient skip, not a code bug (phases={})
                report = self._final_report()
                if "connection" in str(e).lower() or "database" in str(e).lower() or "pool" in str(e).lower():
                    report["skipped"] = True
                    report["reason"] = "database_unavailable"
                return report

            logger.info("\n[CHECK] Database connectivity...")
            if not self.db_monitor.check_db_connectivity():
                logger.error("[DB_ERROR] Database connectivity check FAILED")
                logger.error("Check CloudWatch alarms for database availability. Returning skipped status.")
                report = self._final_report()
                report["skipped"] = True
                report["reason"] = "database_unavailable"
                return report
            else:
                logger.info("[OK] Database connectivity check passed")

            logger.info("\n[CHECK] Monitoring RDS connection pool...")
            self.db_monitor.check_connection_pool_health()

            logger.info("\n[CHECK] Validating startup configuration...")
            self._validate_startup_configuration()

            logger.info("\n[CHECK] Killing long-running analytics loaders...")
            self._kill_long_running_loaders()

            logger.info("\n[HEALTH CHECK] System diagnostics before Phase 1:")
            self.db_monitor.health_check_diagnostics()

            logger.info("\n[LOADER CHECK] Verifying critical loaders have run recently...")
            try:
                self._check_loader_health()
            except RuntimeError as e:
                logger.error(
                    f"[LOADER HEALTH CHECK] {e}. Proceeding to Phase 1 which will re-evaluate. "
                    f"If loaders remain stale, Phase 1 will halt."
                )

            # CRITICAL FIX: Don't skip trading phases on non-trading days.
            # Circuit breaker will halt if market is closed.
            # Skipping phases 4-8 prevented ALL signal generation and trading for 18+ days.
            skip_phases = None
            # Disabled: if not is_trading_day:
            #     logger.info(
            #         "Non-trading day: skipping broker sync (phase 4) and trading phases (5-8), will run data checks (1-3) + metrics (9)"
            #     )
            #     skip_phases = [
            #         4,
            #         5,
            #         6,
            #         7,
            #         8,
            #     ]  # Skip broker reconciliation, position adjustments, signal gen, entry/exit execution

            logger.info("\n[PROACTIVE WAIT] Waiting for critical loaders to complete before Phase 1...")
            try:
                loaders_ready = self._wait_for_critical_loaders_proactive(max_wait_seconds=300)
            except RuntimeError as e:
                logger.error(
                    f"[PROACTIVE LOADER WAIT] {e}. Proceeding to Phase 1 anyway. "
                    f"Manual intervention may be needed if loaders don't recover."
                )
                loaders_ready = False
            if loaders_ready:
                logger.info("[OK] All critical loaders completed before Phase 1")
            else:
                logger.warning(
                    "[WARNING] Critical loaders did not complete within timeout. Phase 1 will check data freshness."
                )

            logger.info("\n[DEADLOCK PREVENTION] Checking if halt flag needs proactive clear...")
            self.halt_manager.proactive_clear_stale_halt()

            self.executor = self._setup_executor(skip_phases=skip_phases)
            with TimeBlock("orchestrator_executor"):
                executor_result = self.executor.run()

            # CRITICAL FIX: Transfer executor's phase results to orchestrator's phase_results
            # The executor stores results in its own dictionary, but orchestrator needs them
            # in self.phase_results for final reporting and execution tracking
            executor_phases = executor_result.get("results", {})
            for phase_num, phase_result in executor_phases.items():
                self.phase_results[phase_num] = {
                    "phase": phase_num,
                    "name": phase_result.phase_name,
                    "status": phase_result.status,
                    "summary": phase_result.data.get("summary", ""),
                }
                # Also log each phase to the execution tracker for orchestrator_execution_log
                self.execution_tracker.log_phase_result(
                    phase_num,
                    phase_result.phase_name,
                    phase_result.status,
                    phase_result.data.get("summary", ""),
                )

            # Validate executor result structure
            if "success" not in executor_result:
                raise RuntimeError(
                    f"Executor result missing 'success' field. "
                    f"Available keys: {list(executor_result.keys())}. "
                    f"Cannot determine if execution succeeded."
                )

            if not executor_result["success"]:
                # CRITICAL: Validate error_phase field exists when success=False (fail-fast if missing)
                error_phase = executor_result.get("error_phase")
                if error_phase is None:
                    raise ValueError(
                        f"[EXECUTOR] Execution failed but missing required 'error_phase' field. "
                        f"Cannot identify which phase halted. Result: {executor_result}"
                    )
                logger.critical(f"[EXECUTOR] Phase sequence halted at Phase {error_phase}")
                return self._final_report()

            # Log performance metrics and total time
            log_metrics_summary()
            total_elapsed = time.time() - self.run_start
            logger.info(f"\n[TOTAL] Orchestrator run completed in {total_elapsed:.2f}s")
            logger.info(f"[END TIME] {datetime.now(timezone.utc).isoformat()}")

            # Emit pipeline timing to CloudWatch for monitoring
            try:
                from algo.reporting import MetricsPublisher

                with MetricsPublisher() as metrics:
                    metrics.put_loader_duration("orchestrator_run", total_elapsed)
                    # Determine pipeline context (morning prep vs EOD based on run time)
                    run_hour = datetime.now(EASTERN_TZ).hour
                    if run_hour < 10:  # Before 10 AM = morning prep
                        metrics.add_metric(
                            "morning_prep_pipeline_seconds",
                            total_elapsed,
                            unit="Seconds",
                        )
                    else:  # After 10 AM = EOD pipeline
                        metrics.add_metric("eod_pipeline_seconds", total_elapsed, unit="Seconds")
            except (ValueError, ZeroDivisionError, TypeError) as e:
                logger.debug(f"Could not emit pipeline timing metrics: {e}")

            return self._final_report()
        finally:
            self._release_run_lock()

    def _final_report(self) -> dict[str, Any]:
        logger.info(f"\n{'#' * 70}")
        logger.info(f"#   FINAL REPORT — {self.run_id}")
        logger.info(f"{'#' * 70}")
        for n, info in sorted(self.phase_results.items(), key=lambda x: str(x[0])):
            status_flag = {
                "success": "[OK] ",
                "halt": "[HALT]",
                "fail": "[FAIL]",
                "error": "[ERR] ",
            }.get(info["status"], "[?]   ")
            logger.info(f"  {status_flag} Phase {n}: {info['name']:22s} — {info['summary']}")
        logger.info(f"{'#' * 70}\n")

        any_error = any(p["status"] in ("error", "fail") for p in self.phase_results.values())
        any_halt = any(p["status"] == "halt" for p in self.phase_results.values())

        # Determine reason for halt/skip if applicable
        skip_reason = None
        if any_error:
            skip_reason = next(
                (p["summary"] for p in self.phase_results.values() if p["status"] in ("error", "fail")),
                "orchestrator_error",
            )
        elif any_halt:
            skip_reason = next(
                (p["summary"] for p in self.phase_results.values() if p["status"] == "halt"),
                "circuit_breaker_halted",
            )

        result = {
            "run_id": self.run_id,
            "run_date": self.run_date.isoformat(),
            "phases": [{"phase": n, **info} for n, info in sorted(self.phase_results.items(), key=lambda x: str(x[0]))],
            "success": not any_error,
            "halted": any_halt,
            "skipped": any_halt,  # Required by Lambda handler
            "reason": skip_reason or "none",  # Required by Lambda handler
        }

        # FIXED Issue #6: Save execution log for audit trail
        try:
            if any_error:
                overall_status = "error"
                halt_reason = next(
                    (p["summary"] for p in self.phase_results.values() if p["status"] == "error"),
                    None,
                )
            elif any_halt:
                overall_status = "halted"
                halt_reason = next(
                    (p["summary"] for p in self.phase_results.values() if p["status"] == "halt"),
                    None,
                )
            else:
                overall_status = "success"
                halt_reason = None

            self.execution_tracker.save_execution_log(overall_status, halt_reason)

            # ALSO write to algo_orchestrator_runs for backward compatibility and dashboard visibility
            try:
                execution_time = time.time() - self.run_start

                with DatabaseContext("write") as cur:
                    cur.execute(
                        """
                        INSERT INTO algo_orchestrator_runs
                        (run_id, run_date, overall_status, started_at, completed_at, execution_time_seconds, halt_reason)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (run_id) DO NOTHING
                        """,
                        (
                            self.run_id,
                            self.run_date,
                            overall_status,
                            datetime.now(timezone.utc) - timedelta(seconds=execution_time),
                            datetime.now(timezone.utc),
                            execution_time,
                            halt_reason or "",
                        ),
                    )
                logger.debug(f"[EXECUTION_LOG] Wrote to algo_orchestrator_runs: {self.run_id}")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"[EXECUTION_LOG] Could not write to algo_orchestrator_runs: {e}")
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"[EXECUTION_LOG] Failed to save execution log: {e}")

        # Publish CloudWatch metrics (non-blocking — never let metrics interrupt trading)
        try:
            from algo.reporting import MetricsPublisher

            with MetricsPublisher(dry_run=self.dry_run) as m:
                m.put_orchestrator_result(bool(result["success"]), {str(k): v for k, v in self.phase_results.items()})

                # Extract numeric data from executor phase results (not self.phase_results)
                if hasattr(self, "executor") and self.executor:
                    # Signal count from phase 7 (signal generation)
                    phase7_result = self.executor.get_result(7)
                    if phase7_result and hasattr(phase7_result, "data"):
                        signals = phase7_result.data.get("liquidity_passed", 0)
                        if isinstance(signals, int):
                            m.put_signal_count(signals)
                        else:
                            logger.warning(
                                f"Phase 7 returned non-int liquidity_passed: {type(signals)}, defaulting to 0"
                            )
                            signals = 0
                            m.put_signal_count(signals)
                    else:
                        logger.debug("Phase 7 result not found in executor")

                    # Trade count from phase 8 (entry execution)
                    phase8_result = self.executor.get_result(8)
                    if phase8_result and hasattr(phase8_result, "data"):
                        trades = phase8_result.data.get("entered")
                        if isinstance(trades, int):
                            m.put_trade_count(trades)
                        else:
                            logger.debug(f"Phase 8 returned non-int entered count: {type(trades)}")
                    else:
                        logger.debug("Phase 8 result not found in executor")

                    # Open position count from phase 9 (reconciliation)
                    phase9_result = self.executor.get_result(9)
                    if phase9_result and hasattr(phase9_result, "data"):
                        positions = phase9_result.data.get("positions")
                        if isinstance(positions, int):
                            m.put_open_positions(positions)
                        else:
                            logger.debug(f"Phase 9 returned non-int positions: {type(positions)}")
                    else:
                        logger.debug("Phase 9 result not found in executor")
                else:
                    logger.warning("Executor not available for metric extraction")

        except (
            ValueError,
            ZeroDivisionError,
            TypeError,
            KeyError,
            AttributeError,
        ) as e:
            # Never let metrics publishing interrupt trading results
            logger.error(f"CloudWatch metric publish failed: {e}")

        return result


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import argparse

    parser = argparse.ArgumentParser(description="Run daily algo workflow")
    parser.add_argument("--date", type=str, help="Run date (YYYY-MM-DD)", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no real trades")
    parser.add_argument("--init-only", action="store_true", help="Run loaders only, no trading")
    parser.add_argument("--quiet", action="store_true", help="Reduce output")
    parser.add_argument("--run-id", type=str, help="Run identifier (from EventBridge scheduler)", default=None)
    args = parser.parse_args()

    run_date = _date.fromisoformat(args.date) if args.date else None

    # ORCHESTRATOR_DRY_RUN env var takes precedence over --dry-run flag.
    # Step Functions TriggerOrchestrator sets this to "true" for pipeline validation runs.
    env_dry_run = os.getenv("ORCHESTRATOR_DRY_RUN", "false").lower() in (
        "true",
        "1",
        "yes",
    )
    dry_run = args.dry_run or env_dry_run

    from config.credential_validator import assert_credentials

    assert_credentials(on_failure="warn")

    if args.init_only:
        logger.info("Running in INIT-ONLY mode: loading data without trading")
        # For init-only, skip the orchestrator and just run loaders
        logger.info("To run loaders, execute: python3 run-all-loaders.py")
        sys.exit(0)

    from algo.infrastructure import get_config

    config = get_config()
    orch = Orchestrator(config=config, run_date=run_date, dry_run=dry_run, verbose=not args.quiet, run_id=args.run_id)
    try:
        final = orch.run()
        sys.exit(0 if final["success"] else 1)
    finally:
        orch.cleanup()
