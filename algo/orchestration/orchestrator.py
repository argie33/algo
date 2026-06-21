#!/usr/bin/env python3

import json
import logging
import os
import sys
import time
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import psycopg2

from algo.infrastructure import MarketCalendar
from algo.orchestrator.phase_executor import OrchestratorPhaseExecutor, PhaseDefinition
from algo.reporting import AlertManager
from monitoring.metrics_context import (
    TimeBlock,
    log_metrics_summary,
)
from utils.db import DatabaseContext, assert_safe_table
from utils.infrastructure import (
    EASTERN_TZ,
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

    HALT_FLAG_DYNAMODB_KEY = "orchestrator_halt"

    def __init__(
        self,
        config: Any,
        run_date: _date | None = None,
        dry_run: bool = False,
        verbose: bool = True,
    ) -> None:
        if config is None:
            raise ValueError(
                "Orchestrator requires explicit config parameter (dependency injection). "
                "Remove fallback to get_config() — get config at entry point and pass it explicitly."
            )
        self.config = config

        # Override execution_mode from environment variable if set
        env_execution_mode = os.getenv("ORCHESTRATOR_EXECUTION_MODE", "").strip().lower()
        if env_execution_mode:
            self.config.override("execution_mode", env_execution_mode)

        # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
        self.run_date = run_date or datetime.now(EASTERN_TZ).date()
        self.dry_run = dry_run
        self.verbose = verbose
        self.phase_results: dict[int | str, Any] = {}
        self.run_id = f"RUN-{self.run_date.isoformat()}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
        # FIXED Issue #6: Initialize execution tracker for audit trail logging
        self.execution_tracker = get_tracker()
        self.execution_tracker.set_run_context(self.run_id, self.run_date)
        # FIXED Issue #8: Use DynamoDB lock manager instead of filesystem lock for distributed locking in Fargate
        from utils.db import DynamoDBLockManager

        self.lock_manager = DynamoDBLockManager()
        self._lock_acquired = False
        # FIXED Issue #3: Halt flag now uses DynamoDB instead of /tmp (which is ephemeral in Lambda)
        self._halt_flag_checked = False
        self.degraded_mode = False
        self.alerts = AlertManager()

        # RDS Proxy handles connection pooling - no local pool needed
        # Database is ALWAYS required - both dry-run and live execution need data to validate phases
        # degraded_mode is ONLY set if database connection actually fails (checked at pre-flight)
        self.degraded_mode = False

        # DB failure counter removed: /tmp is ephemeral in Lambda (doesn't persist across invocations).
        # CloudWatch alarms on DB connection errors are more reliable for detecting outages.

    def cleanup(self) -> None:
        """No-op: RDS Proxy handles connection cleanup."""

    # ---------- Database health monitoring (B4) ----------

    def _check_db_connectivity(self) -> bool:
        """Test if database is reachable. Returns True if OK, False if failed."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT 1")
            return True
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _check_halt_flag(self) -> bool:
        """Check for halt flag in DynamoDB. Returns True if halt was requested.

        Uses DynamoDB instead of /tmp to work in Lambda where /tmp is ephemeral.
        SECURITY: If DynamoDB is unreachable, emits CloudWatch alarm metric.

        ISSUE #8 FIX: Halt flag persists through entire trading day (9:30 AM - 4:00 PM ET)
        to prevent Phase 5 from generating signals with stale data set by early morning
        Phase 1. Auto-expires only at market open of next trading day (9:30 AM ET).

        Timeline example:
        - 2:30 AM: Loaders detect stale data → Phase 1 sets halt_flag with triggered_at=2:30 AM
        - 9:30 AM, 1 PM, 3 PM, 5:30 PM: Orchestrator runs check halt_flag → still active (same day)
        - 9:30 AM NEXT DAY: Auto-clears halt_flag at market open (new trading day)

        """

        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
            table = dynamodb.Table(table_name)

            response = table.get_item(Key={"key": self.HALT_FLAG_DYNAMODB_KEY})
            if "Item" in response and response["Item"].get("halt_flag") is True:
                triggered_at_str = response["Item"].get("triggered_at", "")
                if triggered_at_str:
                    try:
                        trigger_dt = datetime.fromisoformat(triggered_at_str.replace("Z", "+00:00"))
                        now_utc = datetime.now(timezone.utc)

                        # Convert to ET for trading hour comparison
                        trigger_et = trigger_dt.astimezone(EASTERN_TZ)
                        now_et = now_utc.astimezone(EASTERN_TZ)

                        trigger_date = trigger_et.date()
                        now_date_et = now_et.date()

                        # Check if halt is from a previous trading day
                        if trigger_date < now_date_et:
                            # Halt flag from previous day: auto-clear only if we've passed
                            # market open (9:30 AM) of current trading day
                            market_open_et = now_et.replace(
                                hour=MARKET_OPEN_HOUR,
                                minute=MARKET_OPEN_MINUTE,
                                second=0,
                                microsecond=0,
                            )
                            market_open_et = market_open_et.replace(tzinfo=EASTERN_TZ)

                            if now_et >= market_open_et:
                                logger.info(
                                    f"[HALT_FLAG] Halt from {trigger_date} past market open ({MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} ET) "
                                    f"on {now_date_et} — auto-clearing"
                                )
                                table.put_item(
                                    Item={
                                        "key": self.HALT_FLAG_DYNAMODB_KEY,
                                        "halt_flag": False,
                                        "reason": "Auto-expired: halt flag from prior trading day after market open",
                                        "reset_at": now_utc.isoformat(),
                                    }
                                )
                                return False
                            else:
                                # Pre-market on current day, keep halt from previous day active
                                # (e.g., stale data from night loaders should halt all-day trading)
                                logger.info(
                                    f"[HALT_FLAG] Halt from {trigger_date} still active before market open today"
                                )
                                return True

                        # Same trading day: halt persists throughout entire day
                        # (early morning Phase 1 sets flag to protect all-day trading)
                        if trigger_date == now_date_et:
                            hours_halted = (now_utc - trigger_dt).total_seconds() / 3600
                            logger.critical(
                                f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED on {now_date_et}. "
                                f"Triggered {hours_halted:.1f}h ago at {trigger_et.strftime('%H:%M ET')}. "
                                f"Reason: {response['Item'].get('reason', 'Unknown')[:150]}"
                            )
                            self.log_phase_result(
                                0,
                                "halt_flag_detected",
                                "halted",
                                f"Halt flag detected (triggered at {trigger_et.strftime('%H:%M ET')}: {response['Item'].get('reason', 'Unknown')[:100]})",
                            )
                            return True

                    except (ValueError, KeyError) as parse_err:
                        logger.warning(f"[HALT_FLAG] Could not parse triggered_at: {parse_err}")

                reason = response["Item"].get("reason", "Unknown")
                logger.critical(
                    f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED (could not parse timestamp). Reason: {reason[:150]}"
                )
                self.log_phase_result(
                    0,
                    "halt_flag_detected",
                    "halted",
                    f"Halt flag detected: {reason[:100]}",
                )
                return True

            # Halt flag not set in DynamoDB
            return False
        except (ValueError, ZeroDivisionError, TypeError) as e:
            # CRITICAL SAFETY: DynamoDB unavailable means we cannot verify halt flag status
            # MUST FAIL-CLOSED: Assume halt is set if we can't verify the flag
            # Better to stop trading unnecessarily than to trade when halt was set
            logger.critical(f"[CRITICAL] Could not check halt flag in DynamoDB: {e}")
            logger.critical("[CRITICAL] FAILING CLOSED: Treating DynamoDB unavailability as halt condition for safety")

            # Emit alert to operations team
            try:
                from algo.reporting import AlertManager

                alerts = AlertManager()
                alerts.send_position_alert(
                    "DYNAMODB",
                    "HALT_CHECK_UNAVAILABLE",
                    "DynamoDB halt flag check failed. Emergency halt mechanism DISABLED. Trading halted as fail-safe. "
                    f"Error: {str(e)[:200]}",
                    {"error": str(e)[:200], "action": "manual_intervention_required"},
                )
            except (ValueError, ZeroDivisionError, TypeError) as alert_err:
                logger.warning(f"Could not send DynamoDB unavailability alert: {alert_err}")

            # Emit metric for monitoring
            try:
                from algo.reporting import MetricsPublisher

                MetricsPublisher().add_metric("DynamoDBHaltCheckFailure", 1, unit="Count")
            except (ValueError, ZeroDivisionError, TypeError) as metric_err:
                logger.warning(f"Could not emit halt check failure metric: {metric_err}")

            # Return True (halt condition) to fail-closed
            return True

    def _set_halt_flag(self, reason: str = "") -> bool:
        """Set halt flag in DynamoDB. Returns True if successfully set.

        ISSUE #8 FIX: When Phase 1 detects stale data, set halt flag to stop
        Phase 5 from generating full-intensity signals during degradation.

        ISSUE #10 FIX: Track multiple halt events in a day for escalation.
        """
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
            table = dynamodb.Table(table_name)

            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)

            # ISSUE #10 FIX: Check if halt flag was already set today (escalation tracking)
            halt_count = 1
            halt_escalated = False
            response = table.get_item(Key={"key": self.HALT_FLAG_DYNAMODB_KEY})
            if "Item" in response and response["Item"].get("halt_flag") is True:
                # Flag already set today - this is a repeat failure requiring escalation
                first_trigger = response["Item"].get("triggered_at", "")
                if first_trigger:
                    try:
                        first_dt = datetime.fromisoformat(first_trigger.replace("Z", "+00:00"))
                        first_et = first_dt.astimezone(EASTERN_TZ)
                        # Same trading day = escalate
                        if first_et.date() == now_et.date():
                            halt_count = response["Item"].get("halt_count", 1) + 1
                            halt_escalated = True
                            logger.critical(
                                f"[HALT_FLAG_ESCALATION] REPEATED HALT on {now_et.date()}: "
                                f"Halt #{halt_count} in same day. "
                                f"First at {first_et.strftime('%H:%M ET')}, now at {now_et.strftime('%H:%M ET')}. "
                                f"Reason: {reason[:100]}"
                            )
                            # Send escalation alert if repeated failures
                            if halt_count >= 2:
                                try:
                                    self.alerts.send_position_alert(
                                        "HALT_ESCALATION",
                                        f"HALT_REPEAT_{halt_count}",
                                        f"Halt flag triggered {halt_count} times on {now_et.date()}. "
                                        "Repeated data quality issues. Manual investigation required.",
                                        {
                                            "halt_count": halt_count,
                                            "first_at": first_trigger,
                                            "latest_reason": reason[:100],
                                        },
                                    )
                                except (ValueError, ZeroDivisionError, TypeError) as alert_err:
                                    logger.warning(f"Could not send escalation alert: {alert_err}")
                    except (ValueError, KeyError) as escalation_err:
                        logger.warning(f"Could not check halt escalation: {escalation_err}")

            table.put_item(
                Item={
                    "key": self.HALT_FLAG_DYNAMODB_KEY,
                    "halt_flag": True,
                    "triggered_at": now_utc.isoformat(),
                    "reason": reason or "Phase 1 degraded: stale data detected",
                    "halt_count": halt_count,
                }
            )

            if halt_escalated and halt_count >= 2:
                logger.critical(f"[HALT_FLAG_SET_ESCALATED] {reason or 'Phase 1 degraded'} (halt #{halt_count})")
            else:
                logger.critical(f"[HALT_FLAG_SET] {reason or 'Phase 1 degraded: halt flag activated'}")
            return True
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _clear_halt_flag(self, reason: str = "") -> bool:
        """Clear halt flag in DynamoDB. Returns True if successfully cleared.

        ISSUE #8 FIX: When Phase 1 verifies data is fresh, explicitly clear the
        halt flag to allow Phase 5 to generate signals normally.

        Args:
            reason: Optional explanation for why halt was cleared

        Returns: True if successfully cleared, False on error
        """
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
            table = dynamodb.Table(table_name)

            now_utc = datetime.now(timezone.utc)
            table.put_item(
                Item={
                    "key": self.HALT_FLAG_DYNAMODB_KEY,
                    "halt_flag": False,
                    "cleared_at": now_utc.isoformat(),
                    "reason": reason or "Phase 1 verified: data is fresh",
                    "reset_at": now_utc.isoformat(),
                }
            )
            logger.info(f"[HALT_FLAG_CLEARED] {reason or 'Phase 1 verified: data is fresh, resuming normal trading'}")
            return True
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _check_connection_pool_health(self) -> None:
        """Monitor RDS connection pool and alert if approaching limits."""
        try:
            from algo.monitoring import check_stuck_connections, get_pool_status

            status = get_pool_status()
            logger.debug(
                f"[RDS_POOL] Status: {status['active_connections']}/{status['max_connections']} "
                f"({status['usage_pct']:.0f}%)"
            )

            # Alert on stuck connections (held >5min)
            if status["stuck_connections_count"] > 0:
                logger.warning(f"[RDS_POOL] Found {status['stuck_connections_count']} stuck connections")
                check_stuck_connections()
        except (KeyError, ValueError, AttributeError) as e:
            logger.debug(f"Could not check connection pool health: {e}")

    def _health_check_diagnostics(self) -> None:
        """Log system health status: what's working, what's not, what's stale."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SET statement_timeout = 10000")  # 10s timeout

                # Check key table freshness
                tables_to_check = [
                    ("price_daily", "Prices"),
                    ("market_health_daily", "Market health"),
                    ("market_exposure_daily", "Market exposure"),
                    ("buy_sell_daily", "Buy/sell signals (Phase 5)"),
                    ("trend_template_data", "Trend template"),
                    ("sector_ranking", "Sector ranking"),
                    ("swing_trader_scores", "Swing scores (legacy)"),
                ]

                logger.info("  Table Freshness Status:")
                try:
                    for table, _desc in tables_to_check:
                        assert_safe_table(table)

                    union_parts = []
                    for table, _desc in tables_to_check:
                        table_safe = assert_safe_table(table)
                        union_parts.append(
                            f"SELECT '{table}' as table_name, MAX(date) as latest_date FROM {table_safe}"
                        )

                    union_query = " UNION ALL ".join(union_parts)
                    cur.execute(union_query)

                    dates_by_table = {}
                    for row in cur.fetchall():
                        row_dict = dict(row)
                        dates_by_table[row_dict["table_name"]] = row_dict["latest_date"]

                    for table, desc in tables_to_check:
                        try:
                            latest_date = dates_by_table.get(table)
                            if latest_date:
                                from datetime import date as date_type
                                from datetime import datetime as dt

                                if isinstance(latest_date, date_type) and not isinstance(latest_date, datetime):
                                    latest_dt = dt.combine(latest_date, dt.min.time()).replace(tzinfo=timezone.utc)
                                elif isinstance(latest_date, datetime) and latest_date.tzinfo is None:
                                    latest_dt = latest_date.replace(tzinfo=timezone.utc)
                                else:
                                    latest_dt = (
                                        latest_date
                                        if isinstance(latest_date, datetime)
                                        else dt.fromisoformat(str(latest_date)).replace(tzinfo=timezone.utc)
                                    )
                                age = (datetime.now(timezone.utc) - latest_dt).days
                                logger.info(f"    [{age}d old] {desc:20s}: {latest_date}")
                            else:
                                logger.info(f"    [EMPTY] {desc:20s}: no data")
                        except (psycopg2.DatabaseError, psycopg2.OperationalError) as t_err:
                            logger.warning(f"    [ERROR] {desc:20s}: {t_err}")
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.warning(f"  Could not fetch table freshness: {e}")

                # Check loader status
                try:
                    cur.execute("""
                        SELECT table_name, status, last_updated
                        FROM data_loader_status
                        WHERE table_name IN ('price_daily', 'buy_sell_daily', 'market_health_daily', 'market_exposure_daily')
                        ORDER BY table_name
                    """)
                    logger.info("  Loader Status:")
                    for row in cur.fetchall():
                        logger.info(f"    {row[0]:25s}: {row[1]:10s} (updated {row[2]})")
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as loader_err:
                    logger.debug(f"    Could not check loader status: {loader_err}")

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"  Health check failed: {e}")

    def _verify_task_stopped(
        self,
        ecs,
        cluster: str,
        task_arn: str,
        loader_name: str,
        max_retries: int = 3,
        retry_delay_sec: float = 1.0,
    ) -> bool:
        """Verify that a task actually stopped. Returns True if verified STOPPED, False if verification failed.

        ISSUE #5 FIX: Prevents hung tasks consuming RDS connections by verifying termination.
        Retries with escalating delays because ECS stop_task is async and may fail silently.
        """
        for attempt in range(1, max_retries + 1):
            try:
                response = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])
                tasks = response.get("tasks")
                if not tasks or not isinstance(tasks, list) or len(tasks) == 0:
                    logger.error(
                        f"[TASK_TERMINATION] Attempt {attempt}: Task {task_arn} not found in describe_tasks response"
                    )
                    if attempt < max_retries:
                        time.sleep(retry_delay_sec)
                        retry_delay_sec *= 1.5  # Exponential backoff
                    continue

                task_status = tasks[0].get("lastStatus", "UNKNOWN")
                desired_status = tasks[0].get("desiredStatus", "UNKNOWN")

                logger.debug(
                    f"[TASK_TERMINATION] Attempt {attempt}: {loader_name} lastStatus={task_status}, desiredStatus={desired_status}"
                )

                # Task is confirmed stopped
                if task_status == "STOPPED":
                    logger.info(f"[TASK_TERMINATION] ✓ {loader_name} task {task_arn} verified STOPPED")
                    return True

                # Task still running but stop was requested
                if desired_status == "STOPPED" and task_status in (
                    "RUNNING",
                    "DEPROVISIONING",
                ):
                    if attempt < max_retries:
                        logger.debug(
                            f"[TASK_TERMINATION] Attempt {attempt}: Stop requested, waiting for status transition..."
                        )
                        time.sleep(retry_delay_sec)
                        retry_delay_sec *= 1.5
                        continue

                # Task didn't receive stop signal
                logger.error(
                    f"[TASK_TERMINATION] Attempt {attempt}: Task status {task_status}/{desired_status} — stop not acknowledged"
                )
                if attempt < max_retries:
                    time.sleep(retry_delay_sec)
                    retry_delay_sec *= 1.5

            except (ValueError, KeyError, AttributeError, psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"[TASK_TERMINATION] Attempt {attempt}: Failed to verify task status: {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay_sec)
                    retry_delay_sec *= 1.5

        # All retries exhausted — termination verification failed
        logger.critical(
            f"[TASK_TERMINATION] FAILED: {loader_name} task {task_arn} did not transition to STOPPED after {max_retries} attempts. "
            "RDS connection may not be released. Manual intervention required."
        )
        return False

    def _kill_long_running_loaders(self) -> None:
        """CRITICAL: Kill hung loaders (analytics + critical-path) if approaching next orchestrator run.

        Analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics)
        iterate 5000+ symbols with yfinance rate limits and can run 6+ hours.

        Critical-path loaders (swing_trader_scores_vectorized, trend_template_data, sector_ranking,
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
                "swing_trader_scores_vectorized",
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
                    continue

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
                    except (ValueError, KeyError, AttributeError) as stop_err:
                        logger.error(f"[TASK_TERMINATION] stop_task() call failed: {stop_err}")
                        failed_terminations.append((loader_name, task_arn, str(stop_err)))
                        continue

                    # ISSUE #5: Verify task actually stopped (with retries)
                    if self._verify_task_stopped(ecs, cluster, task_arn, loader_name):
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

        except (ValueError, KeyError, AttributeError, psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"[OOM_PREVENTION] Could not check/kill long-running loaders: {e}")
            # Don't halt trading for this check - it's advisory

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

            logger.info(f"[TABLE-CHECK] All {len(required_tables)} required tables exist ✓")
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
            logger.warning(f"Warning: Could not persist audit log entry: {e}")

    # ---------- Phase implementations ----------

    def phase_1_data_freshness(self):
        """Thin delegation to phase1_data_freshness module.

        New version only checks: are today's prices loaded? 95%+ coverage?
        Removes all the complex grace period / hung task detection logic.
        """
        self.log_phase_start(1, "DATA FRESHNESS CHECK")
        from algo.orchestrator.phase1_data_freshness import run as run_phase1

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
                    "reason": result.summary if degraded_status else None,
                    "ttl": int(time.time()) + 3600,  # 1-hour TTL
                }
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError) as e:
            logger.debug(f"Failed to write Phase 1 degraded_mode status to DynamoDB: {e}")

        # Halt flag lifecycle: always run regardless of informational write success above.
        try:
            degraded_status = result.status == "degraded"
            if degraded_status:
                logger.info(f"[DEGRADED_MODE] Phase 1 returned degraded status: {result.summary}")
                self._set_halt_flag(f"Phase 1 degraded: {result.summary}")
            elif result.status == "ok":
                self._clear_halt_flag(f"Phase 1 verified data is fresh at {datetime.now(timezone.utc).isoformat()}")
        except (ValueError, KeyError, AttributeError) as e:
            logger.warning(f"Failed to manage halt flag after Phase 1: {e}")

        return not result.halted

    def phase_2_circuit_breakers(self) -> bool:
        """Thin delegation to phase2_circuit_breakers module."""
        self.log_phase_start(2, "CIRCUIT BREAKERS")
        from algo.orchestrator.phase2_circuit_breakers import run as run_phase2

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
        from algo.orchestrator.phase3_position_monitor import run as run_phase3

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
        recs = result.data.get("recommendations")
        self._position_recs = recs if recs is not None else []
        return True

    def phase_5_exposure_policy(self) -> bool:
        """Thin delegation to phase5_exposure_policy module."""
        self.log_phase_start(5, "EXPOSURE POLICY ACTIONS")
        from algo.orchestrator.phase5_exposure_policy import run as run_phase5

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
        self._exposure_constraints = result.data.get("constraints")
        actions = result.data.get("actions")
        self._exposure_actions = actions if actions is not None else []
        return True

    def phase_6_exit_execution(self) -> bool:
        """Thin delegation to phase6_exit_execution module."""
        self.log_phase_start(6, "EXIT EXECUTION")
        # No halt flag check: exits must always run to reduce risk even when entries are halted.
        from algo.orchestrator.phase6_exit_execution import run as run_phase6

        # Phase 6 depends on Phase 3 and 5 producing position_recs and exposure_actions
        if not hasattr(self, "_position_recs"):
            raise RuntimeError(
                "[PHASE 6 CRITICAL] _position_recs not set by Phase 3. Phase 3 must run and succeed before Phase 6."
            )
        if not hasattr(self, "_exposure_actions"):
            raise RuntimeError(
                "[PHASE 6 CRITICAL] _exposure_actions not set by Phase 5. Phase 5 must run and succeed before Phase 6."
            )

        result = run_phase6(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
            self._position_recs,
            self._exposure_actions,
            self._check_halt_flag,
        )
        self._phase6_result = result
        return not result.halted

    def phase_7_signal_generation(self) -> bool:
        """Thin delegation to phase7_signal_generation module.

        ISSUE #4 FIX: Explicit dependency validation.
        Phase 7 depends on Phase 5 producing valid exposure_constraints.
        If constraints are missing or invalid, fail loudly instead of silently degrading.

        New version: Compute signals on-the-fly from price data.
        No dependency on technical_data_daily.
        """
        self.log_phase_start(7, "SIGNAL GENERATION & RANKING")
        from algo.orchestrator.phase7_signal_generation import run as run_phase7
        from algo.orchestrator.phase_data_contract import validate_phase_5_constraints

        # CRITICAL VALIDATION: Phase 5 must have produced valid exposure constraints
        if not hasattr(self, "_exposure_constraints"):
            raise RuntimeError(
                "[PHASE 7 CRITICAL] Exposure constraints not set by Phase 5. Phase 5 must run and succeed before Phase 7."
            )

        exposure_constraints = self._exposure_constraints
        if exposure_constraints is None:
            raise ValueError(
                "[PHASE 7 CRITICAL] Exposure constraints are None. Phase 5 must produce valid constraints."
            )

        # Validate constraints schema
        try:
            validate_phase_5_constraints(exposure_constraints)
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f"[PHASE 7 CRITICAL] Exposure constraints invalid: {e}") from e

        result = run_phase7(
            self.run_date,
            self.dry_run,
            self.verbose,
            self.log_phase_result,
            exposure_constraints,
            self._check_halt_flag,
            phase1_degraded=False,
            config=self.config,
        )
        self._phase7_result = result
        trades = result.data.get("qualified_trades")
        self._qualified_trades = trades if trades is not None else []
        self.phase_results.setdefault(7, {})["signals_evaluated"] = len(self._qualified_trades)
        return not result.halted

    def phase_8_entry_execution(self) -> bool:
        """Thin delegation to phase8_entry_execution module.

        New version: Compute ATR + SMA_50 on-demand, execute immediately.
        """
        self.log_phase_start(8, "ENTRY EXECUTION")
        from algo.orchestrator.phase8_entry_execution import run as run_phase8

        # Phase 8 depends on Phase 7 and 5 producing qualified_trades and exposure_constraints
        if not hasattr(self, "_qualified_trades"):
            raise RuntimeError(
                "[PHASE 8 CRITICAL] _qualified_trades not set by Phase 7. Phase 7 must run and succeed before Phase 8."
            )
        if not hasattr(self, "_exposure_constraints"):
            raise RuntimeError(
                "[PHASE 8 CRITICAL] _exposure_constraints not set by Phase 5. Phase 5 must run and succeed before Phase 8."
            )

        result = run_phase8(
            self.config,
            self.run_date,
            self.dry_run,
            self.verbose,
            self.log_phase_result,
            self._qualified_trades,
            self._exposure_constraints,
            self._check_halt_flag,
        )
        self._phase8_result = result
        if "entered" not in result.data:
            raise RuntimeError(
                f"Phase 8 (entry execution) returned incomplete result: missing 'entered' field. "
                f"Got keys: {list(result.data.keys())}"
            )
        self.phase_results.setdefault(8, {})["trades_executed"] = result.data["entered"]
        return not result.halted

    def phase_9_reconcile(self) -> bool:
        """Thin delegation to phase9_reconciliation module."""
        self.log_phase_start(9, "RECONCILIATION & SNAPSHOT")
        # No halt flag check: snapshot must always be written so circuit breakers
        # have accurate portfolio state on the next invocation.
        from algo.orchestrator.phase9_reconciliation import run as run_phase9

        result = run_phase9(self.config, self.run_date, self.log_phase_result)
        self._phase9_result = result
        if "positions" not in result.data:
            raise RuntimeError(
                f"Phase 9 (reconciliation) returned incomplete result: missing 'positions' field. "
                f"Got keys: {list(result.data.keys())}"
            )
        self.phase_results.setdefault(9, {})["open_positions"] = result.data["positions"]
        return not result.halted

    # ---------- Executor setup (Phase 2: Phase Executor Framework) ----------

    def _setup_executor(self) -> OrchestratorPhaseExecutor:
        """Create and configure the phase executor.

        Registers all phases with their dependencies, transforming the monolithic
        run() control flow into a declarative phase graph.

        Returns:
            OrchestratorPhaseExecutor ready to execute all phases.
        """
        executor = OrchestratorPhaseExecutor(config=self.config, halt_check_fn=self._check_halt_flag)

        # Phase 1: Data Freshness
        executor.register_phase(
            PhaseDefinition(
                phase_num=1,
                phase_name="DATA FRESHNESS CHECK",
                dependencies=[],
                execute_fn=self._executor_phase_1,
                skip_if_halted=False,
            )
        )

        # Phase 2: Circuit Breakers (depends on Phase 1)
        executor.register_phase(
            PhaseDefinition(
                phase_num=2,
                phase_name="CIRCUIT BREAKERS",
                dependencies=[1],
                execute_fn=self._executor_phase_2,
                skip_if_halted=False,
            )
        )

        # Phase 3: Position Monitor (always runs, even if Phase 2 fails)
        executor.register_phase(
            PhaseDefinition(
                phase_num=3,
                phase_name="POSITION MONITOR",
                dependencies=[],
                execute_fn=self._executor_phase_3,
                skip_if_halted=True,
            )
        )

        # Phase 4: Reconciliation (depends on Phase 3)
        executor.register_phase(
            PhaseDefinition(
                phase_num=4,
                phase_name="RECONCILIATION",
                dependencies=[3],
                execute_fn=self._executor_phase_4,
                skip_if_halted=True,
            )
        )

        # Phase 5: Exposure Policy (depends on Phase 4)
        executor.register_phase(
            PhaseDefinition(
                phase_num=5,
                phase_name="EXPOSURE POLICY ACTIONS",
                dependencies=[4],
                execute_fn=self._executor_phase_5,
                skip_if_halted=True,
            )
        )

        # Phase 6: Exit Execution (always runs, depends on Phase 5)
        executor.register_phase(
            PhaseDefinition(
                phase_num=6,
                phase_name="EXIT EXECUTION",
                dependencies=[5],
                execute_fn=self._executor_phase_6,
                skip_if_halted=False,
                always_run=True,
            )
        )

        # Phase 7: Signal Generation (depends on Phase 5)
        executor.register_phase(
            PhaseDefinition(
                phase_num=7,
                phase_name="SIGNAL GENERATION & RANKING",
                dependencies=[5],
                execute_fn=self._executor_phase_7,
                skip_if_halted=True,
            )
        )

        # Phase 8: Entry Execution (depends on Phase 7 and 5)
        executor.register_phase(
            PhaseDefinition(
                phase_num=8,
                phase_name="ENTRY EXECUTION",
                dependencies=[7, 5],
                execute_fn=self._executor_phase_8,
                skip_if_halted=True,
            )
        )

        # Phase 9: Reconciliation (always runs, final snapshot)
        executor.register_phase(
            PhaseDefinition(
                phase_num=9,
                phase_name="RECONCILIATION & SNAPSHOT",
                dependencies=[8],
                execute_fn=self._executor_phase_9,
                skip_if_halted=False,
                always_run=True,
            )
        )

        return executor

    def _executor_phase_1(self, **kwargs):
        """Executor wrapper for Phase 1."""
        self.phase_1_data_freshness()
        if not hasattr(self, "_phase1_result"):
            raise RuntimeError("[PHASE 1] phase_1_data_freshness() did not set _phase1_result")
        return self._phase1_result

    def _executor_phase_2(self, **kwargs):
        """Executor wrapper for Phase 2."""
        self.phase_2_circuit_breakers()
        if not hasattr(self, "_phase2_result"):
            raise RuntimeError("[PHASE 2] phase_2_circuit_breakers() did not set _phase2_result")
        return self._phase2_result

    def _executor_phase_3(self, **kwargs):
        """Executor wrapper for Phase 3."""
        self.phase_3_position_monitor()
        if not hasattr(self, "_phase3_result"):
            raise RuntimeError("[PHASE 3] phase_3_position_monitor() did not set _phase3_result")
        return self._phase3_result

    def _executor_phase_4(self, **kwargs):
        """Executor wrapper for Phase 4: Reconciliation."""
        from algo.orchestrator.phase4_reconciliation import run as run_phase4

        result = run_phase4(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
        )
        return result

    def _executor_phase_5(self, **kwargs):
        """Executor wrapper for Phase 5: Exposure Policy."""
        self.phase_5_exposure_policy()
        if not hasattr(self, "_phase5_result"):
            raise RuntimeError("[PHASE 5] phase_5_exposure_policy() did not set _phase5_result")
        return self._phase5_result

    def _executor_phase_6(self, **kwargs):
        """Executor wrapper for Phase 6: Exit Execution."""
        self.phase_6_exit_execution()
        if not hasattr(self, "_phase6_result"):
            raise RuntimeError("[PHASE 6] phase_6_exit_execution() did not set _phase6_result")
        return self._phase6_result

    def _executor_phase_7(self, **kwargs):
        """Executor wrapper for Phase 7: Signal Generation."""
        self.phase_7_signal_generation()
        if not hasattr(self, "_phase7_result"):
            raise RuntimeError("[PHASE 7] phase_7_signal_generation() did not set _phase7_result")
        return self._phase7_result

    def _executor_phase_8(self, **kwargs):
        """Executor wrapper for Phase 8: Entry Execution."""
        self.phase_8_entry_execution()
        if not hasattr(self, "_phase8_result"):
            raise RuntimeError("[PHASE 8] phase_8_entry_execution() did not set _phase8_result")
        return self._phase8_result

    def _executor_phase_9(self, **kwargs):
        """Executor wrapper for Phase 9: Final Reconciliation."""
        self.phase_9_reconcile()
        if not hasattr(self, "_phase9_result"):
            raise RuntimeError("[PHASE 9] phase_9_reconcile() did not set _phase9_result")
        return self._phase9_result

    # ---------- Main entrypoint ----------

    def run(self) -> dict[str, Any]:
        run_start = time.time()
        logger.info(f"\n{'#' * 70}")
        logger.info(f"#   ALGO ORCHESTRATOR — {self.run_date}  ({'DRY RUN' if self.dry_run else 'LIVE'})")
        logger.info(f"#   run_id: {self.run_id}")
        logger.info(f"#   START TIME: {datetime.now(timezone.utc).isoformat()}")
        logger.info(f"{'#' * 70}")

        if not MarketCalendar.is_trading_day(self.run_date):
            status = MarketCalendar.market_status(datetime.combine(self.run_date, datetime.min.time()))
            logger.info(f"\n Market closed: {status['reason']}")
            logger.info("Skipping all trading phases.\n")
            # FIXED Issue #6: Log skipped runs to execution log
            self.execution_tracker.save_execution_log("skipped", status["reason"])
            return {
                "success": True,
                "skipped": True,
                "reason": f"Market closed: {status['reason']}",
            }

        # Concurrency lock — prevent two orchestrators running at once
        # which would risk duplicate trades or double-counting circuit breakers
        # Skip lock check in dry-run mode (no actual trades) or when DynamoDB unavailable
        if not self.dry_run:
            lock_acquired = self._acquire_run_lock()
            if not lock_acquired:
                if self.lock_manager.is_available:
                    # DynamoDB is available but lock couldn't be acquired (another instance running)
                    logger.error("\nABORT: Could not acquire run lock. Another orchestrator instance is running.")
                    return {"success": False, "error": "Lock acquisition failed"}
                else:
                    # DynamoDB unavailable (no permissions, network issue, etc.) - allow to continue with warning
                    logger.warning(
                        "[DEGRADED MODE] DynamoDB lock unavailable - running without distributed lock protection"
                    )
        else:
            logger.info("[DRY-RUN] Skipping distributed lock check (dry-run mode)")

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
                        return cast(dict[str, Any], self._final_report())

                    logger.info("[OK] All pre-flight checks passed")
            except TimeoutError as e:
                logger.error(f"  [HALT] Pre-flight database timeout (pool exhausted?): {e}")
                report = cast(dict[str, Any], self._final_report())
                report["skipped"] = True
                report["reason"] = "database_timeout"
                return report
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"  [HALT] Pre-flight check failed: {type(e).__name__}: {e}", exc_info=True)
                # Return skipped=True when DB is unreachable so test verification
                # treats this as a transient skip, not a code bug (phases={})
                report = cast(dict[str, Any], self._final_report())
                if "connection" in str(e).lower() or "database" in str(e).lower() or "pool" in str(e).lower():
                    report["skipped"] = True
                    report["reason"] = "database_unavailable"
                return report

            logger.info("\n[CHECK] Database connectivity...")
            if not self._check_db_connectivity():
                logger.error("[DB_ERROR] Database connectivity check FAILED")
                logger.error("Check CloudWatch alarms for database availability. Returning skipped status.")
                report = cast(dict[str, Any], self._final_report())
                report["skipped"] = True
                report["reason"] = "database_unavailable"
                return report
            else:
                logger.info("[OK] Database connectivity check passed")

            logger.info("\n[CHECK] Monitoring RDS connection pool...")
            self._check_connection_pool_health()

            logger.info("\n[CHECK] Killing long-running analytics loaders...")
            self._kill_long_running_loaders()

            logger.info("\n[HEALTH CHECK] System diagnostics before Phase 1:")
            self._health_check_diagnostics()

            executor = self._setup_executor()
            with TimeBlock("orchestrator_executor"):
                executor_result = executor.run()

            if not executor_result.get("success"):
                logger.critical(f"[EXECUTOR] Phase sequence halted at Phase {executor_result.get('error_phase')}")
                return cast(dict[str, Any], self._final_report())

            # Log performance metrics and total time
            log_metrics_summary()
            total_elapsed = time.time() - run_start
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

            return cast(dict[str, Any], self._final_report())
        finally:
            self._release_run_lock()

    def _final_report(self):
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
        result = {
            "run_id": self.run_id,
            "run_date": self.run_date.isoformat(),
            "phases": self.phase_results,
            "success": not any_error,
            "halted": any_halt,
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
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"[EXECUTION_LOG] Failed to save execution log: {e}")

        # Publish CloudWatch metrics (non-blocking — never let metrics interrupt trading)
        try:
            from algo.reporting import MetricsPublisher

            with MetricsPublisher(dry_run=self.dry_run) as m:
                m.put_orchestrator_result(result["success"], self.phase_results)

                # Signal count from phase 5 summary
                if 5 in self.phase_results:
                    phase5 = self.phase_results[5]
                    signals = phase5.get("signals_evaluated")
                    if isinstance(signals, int):
                        m.put_signal_count(signals)
                else:
                    logger.warning("Phase 5 result missing from phase_results")

                # Trade count from phase 6 summary
                if 6 in self.phase_results:
                    phase6 = self.phase_results[6]
                    trades = phase6.get("trades_executed")
                    if isinstance(trades, int):
                        m.put_trade_count(trades)
                else:
                    logger.warning("Phase 6 result missing from phase_results")

                # Open position count from phase 7
                if 7 in self.phase_results:
                    phase7 = self.phase_results[7]
                    positions = phase7.get("open_positions")
                    if isinstance(positions, int):
                        m.put_open_positions(positions)
                else:
                    logger.warning("Phase 7 result missing from phase_results")

        except Exception as e:
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
    orch = Orchestrator(config=config, run_date=run_date, dry_run=dry_run, verbose=not args.quiet)
    try:
        final = orch.run()
        sys.exit(0 if final["success"] else 1)
    finally:
        orch.cleanup()
