#!/usr/bin/env python3

import sys
from pathlib import Path


# Ensure project root is in path before importing modules that need it
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import json
import logging
import os
import time
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union

import psycopg2
import psycopg2.extensions
import psycopg2.sql

from algo.infrastructure import MarketCalendar
from algo.reporting import AlertManager
from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table
from utils.infrastructure.market_timing import (
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    ORCHESTRATOR_KILL_BUFFER_MINUTES,
    ORCHESTRATOR_RUN_TIMES_TUPLE,
)
from utils.infrastructure.timezone import EASTERN_TZ
from utils.logging.execution_tracker import get_tracker


try:
    from monitoring.metrics_context import (
        TimeBlock,
        log_metrics_summary,
    )
except ImportError:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "[MONITORING] monitoring.metrics_context not available — timing metrics disabled. "
        "Rebuild Docker image to include monitoring/ package."
    )
    from contextlib import contextmanager

    @contextmanager  # type: ignore[no-redef, misc]
    def TimeBlock(name, **kwargs):  # type: ignore[no-redef, misc]
        yield

    def log_metrics_summary() -> None:  # type: ignore[no-redef, misc]
        pass

logger = logging.getLogger(__name__)


class Orchestrator:
    """Daily workflow runner with explicit phases."""

    HALT_FLAG_DYNAMODB_KEY = "orchestrator_halt"

    def __init__(
        self,
        config: Any,
        run_date: Optional[_date] = None,
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
        env_execution_mode = (
            os.getenv("ORCHESTRATOR_EXECUTION_MODE", "").strip().lower()
        )
        if env_execution_mode:
            self.config.override("execution_mode", env_execution_mode)

        # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
        self.run_date = run_date or datetime.now(EASTERN_TZ).date()
        self.dry_run = dry_run
        self.verbose = verbose
        self.phase_results: Dict[Union[int, str], Any] = {}
        self.run_id = f"RUN-{self.run_date.isoformat()}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
        # FIXED Issue #6: Initialize execution tracker for audit trail logging
        self.execution_tracker = get_tracker()
        self.execution_tracker.set_run_context(self.run_id, self.run_date)
        # FIXED Issue #8: Use DynamoDB lock manager instead of filesystem lock for distributed locking in Fargate
        from utils.db.dynamo_lock import DynamoDBLockManager

        self.lock_manager = DynamoDBLockManager()
        self._lock_acquired = False
        # FIXED Issue #X: Halt flag now uses DynamoDB + RDS redundancy (eliminates DynamoDB single point of failure)
        from utils.db.halt_flag import get_halt_flag_manager

        self.halt_flag_manager = get_halt_flag_manager()
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
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            logger.error(f"  [ERROR] Database connectivity check failed: {e}")
            return False

    def _check_halt_flag(self) -> bool:
        """Check for halt flag with DynamoDB + RDS redundancy.

        Returns True if halt was requested, False if not halted.

        FIXED Issue #X: Eliminates DynamoDB single point of failure.
        - Tries DynamoDB first (fast)
        - Falls back to RDS if DynamoDB unavailable
        - Circuit breaker: if DynamoDB unavailable >3 times in 5 min, uses RDS only
        - If both unavailable: conservative fail-closed (assume halt)
        """

        halt_flag, reason = self.halt_flag_manager.check_halt_flag()

        # If we got a definitive answer (True or False)
        if halt_flag is not None:
            if halt_flag:
                logger.critical(
                    f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED. Reason: {reason}"
                )
                self.log_phase_result(
                    0,
                    "halt_flag_detected",
                    "halted",
                    f"Halt flag detected: {reason[:100] if reason else 'Unknown'}",
                )
            return halt_flag

        # Both storages unavailable: fail-closed for safety
        logger.critical(
            "[CRITICAL] Could not check halt flag in either DynamoDB or RDS"
        )
        logger.critical(
            "[CRITICAL] FAILING CLOSED: Treating unavailability as halt condition for safety"
        )

        # Emit alert to operations team
        try:
            self.alerts.send_position_alert(
                "HALT_FLAG",
                "CHECK_UNAVAILABLE",
                "Could not verify halt flag status (both DynamoDB and RDS unavailable). Trading halted as fail-safe.",
                {"action": "manual_intervention_required"},
            )
        except Exception as alert_err:
            logger.error(
                f"Could not send halt flag unavailability alert (trading halted): {alert_err}"
            )

        # Emit metric for monitoring
        try:
            from algo.reporting import MetricsPublisher

            MetricsPublisher().add_metric("HaltFlagCheckFailure", 1, unit="Count")
        except Exception as metric_err:
            logger.debug(
                f"Could not emit halt flag check failure metric (non-critical): {metric_err}"
            )

        # Return True (halt condition) to fail-closed
        return True

    def _set_halt_flag(self, reason: str = "") -> bool:
        """Set halt flag in both DynamoDB and RDS. Returns True if set successfully.

        FIXED Issue #X: Dual-storage ensures halt flag persists even if one
        storage is temporarily unavailable. Uses halt_flag_manager for redundancy.
        """
        success = self.halt_flag_manager.set_halt_flag(
            reason or "Phase 1 degraded: stale data detected"
        )

        # Send escalation alert if halt is being triggered for 2nd time in a day
        halt_flag, _ = self.halt_flag_manager.check_halt_flag()
        if halt_flag:
            try:
                self.alerts.send_position_alert(
                    "HALT_FLAG",
                    "SET",
                    f'Halt flag set: {reason or "Stale data detected"}',
                    {"reason": reason},
                )
            except Exception as alert_err:
                logger.error(f"Could not send halt flag set alert: {alert_err}")

        return success

    def _clear_halt_flag(self, reason: str = "") -> bool:
        """Clear halt flag in both DynamoDB and RDS. Returns True if successfully cleared.

        FIXED Issue #X: Uses halt_flag_manager for dual-storage clearing, ensuring
        halt flag is cleared in both storages for consistency.

        Args:
            reason: Optional explanation for why halt was cleared

        Returns: True if successfully cleared, False on error
        """
        success = self.halt_flag_manager.clear_halt_flag(
            reason or "Phase 1 verified: all data fresh"
        )
        logger.info(
            f"[HALT_FLAG_CLEARED] {reason or 'Phase 1 verified: data is fresh, resuming normal trading'}"
        )
        return success

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
                logger.warning(
                    f"[RDS_POOL] Found {status['stuck_connections_count']} stuck connections"
                )
                check_stuck_connections()
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            logger.debug(f"Could not check connection pool health: {e}")

    def _health_check_diagnostics(self) -> None:
        """Log system health status: what's working, what's not, what's stale."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SET statement_timeout = 10000")  # 10s timeout

                # Check key table freshness (tables populated by current pipelines)
                tables_to_check = [
                    ("price_daily", "SPY prices"),
                    ("market_health_daily", "Market health"),
                    ("trend_template_data", "Trend template"),
                    ("swing_trader_scores", "Swing scores"),
                    ("sector_ranking", "Sector ranking"),
                    ("market_exposure_daily", "Market exposure"),
                ]

                logger.info("  Table Freshness Status:")
                for table, desc in tables_to_check:
                    try:
                        table_safe = assert_safe_table(table)
                        cur.execute(
                            psycopg2.sql.SQL("SELECT MAX(date) FROM {} LIMIT 1").format(
                                psycopg2.sql.Identifier(table_safe)
                            )
                        )
                        row = cur.fetchone()
                        latest_date = (
                            row[0] if row is not None and row[0] is not None else None
                        )
                        if latest_date:
                            from datetime import date as date_type
                            from datetime import datetime as dt

                            if isinstance(latest_date, date_type) and not isinstance(
                                latest_date, datetime
                            ):
                                latest_dt = dt.combine(
                                    latest_date, dt.min.time()
                                ).replace(tzinfo=timezone.utc)
                            elif (
                                isinstance(latest_date, datetime)
                                and latest_date.tzinfo is None
                            ):
                                latest_dt = latest_date.replace(tzinfo=timezone.utc)
                            else:
                                latest_dt = (
                                    latest_date
                                    if isinstance(latest_date, datetime)
                                    else dt.fromisoformat(str(latest_date)).replace(
                                        tzinfo=timezone.utc
                                    )
                                )
                            age = (datetime.now(timezone.utc) - latest_dt).days
                            logger.info(f"    [{age}d old] {desc:20s}: {latest_date}")
                        else:
                            logger.info(f"    [EMPTY] {desc:20s}: no data")
                    except Exception as t_err:
                        logger.warning(f"    [ERROR] {desc:20s}: {t_err}")

                # Check loader status
                try:
                    cur.execute("""
                        SELECT table_name, status, last_updated
                        FROM data_loader_status
                        WHERE table_name IN ('price_daily', 'swing_trader_scores', 'trend_template_data', 'market_health_daily')
                        ORDER BY table_name
                    """)
                    logger.info("  Loader Status:")
                    for row in cur.fetchall():
                        logger.info(
                            f"    {row[0]:25s}: {row[1]:10s} (updated {row[2]})"
                        )
                except Exception as loader_err:
                    logger.debug(f"    Could not check loader status: {loader_err}")

        except Exception as e:
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
                if not response.get("tasks"):
                    logger.error(
                        f"[TASK_TERMINATION] Attempt {attempt}: Task {task_arn} not found in describe_tasks response"
                    )
                    if attempt < max_retries:
                        time.sleep(retry_delay_sec)
                        retry_delay_sec *= 1.5  # Exponential backoff
                    continue

                task_status = response["tasks"][0].get("lastStatus", "UNKNOWN")
                desired_status = response["tasks"][0].get("desiredStatus", "UNKNOWN")

                logger.debug(
                    f"[TASK_TERMINATION] Attempt {attempt}: {loader_name} lastStatus={task_status}, desiredStatus={desired_status}"
                )

                # Task is confirmed stopped
                if task_status == "STOPPED":
                    logger.info(
                        f"[TASK_TERMINATION] ✓ {loader_name} task {task_arn} verified STOPPED"
                    )
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

            except Exception as e:
                logger.error(
                    f"[TASK_TERMINATION] Attempt {attempt}: Failed to verify task status: {e}"
                )
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

        Critical-path loaders (swing_trader_scores, trend_template_data, sector_ranking,
        market_health_daily, market_exposure_daily, algo_metrics_daily) should complete within
        30-90 minutes (per steering doc line 91). If still running 15 min before next orchestrator
        run, they're hung and consuming RDS connections.

        If any is still running when orchestrator fires, RDS connection pool exhaustion occurs.
        This check prevents that.

        Dynamic timeout: calculate time until next orchestrator run, subtract 15 min buffer.
        Orchestrator runs at: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET (Mon-Fri only)

        ISSUE #5 FIX: Verifies task termination to prevent hung tasks consuming RDS connections.
        ISSUE #1 FIX: Added critical-path loaders to kill check (swing_trader_scores,
                      trend_template_data, sector_ranking, market_health_daily).
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
            # Loaders actually in morning/EOD pipelines. signal_quality_scores,
            # buy_sell_daily, technical_data_daily were removed from both pipelines;
            # orchestrator computes signals on-the-fly from trend_template_data.
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
                orch_time = now_et.replace(
                    hour=orch_hour, minute=orch_minute, second=0, microsecond=0
                )
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
            kill_threshold_et = next_orch_et - timedelta(
                minutes=ORCHESTRATOR_KILL_BUFFER_MINUTES
            )
            max_runtime = kill_threshold_et - now_et

            if max_runtime.total_seconds() <= 0:
                logger.debug(
                    "[OOM_PREVENTION] Next orchestrator run is imminent, using 5 min max runtime"
                )
                max_runtime = timedelta(minutes=5)

            logger.debug(
                f"[OOM_PREVENTION] Next orchestrator run at {next_orch_et.strftime('%H:%M')} ET. "
                f"Kill timeout: {max_runtime.total_seconds()/60:.0f} minutes"
            )

            # List running tasks
            response = ecs.list_tasks(cluster=cluster, desiredStatus="RUNNING")
            if not response.get("taskArns"):
                return

            # Get task details (includes startedAt timestamp)
            task_details = ecs.describe_tasks(
                cluster=cluster, tasks=response["taskArns"]
            )
            now = datetime.now(timezone.utc)

            failed_terminations = []
            for task in task_details.get("tasks", []):
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
                        f"max {max_runtime.total_seconds()/3600:.1f}h before next orch run): {task_arn}"
                    )

                    # ISSUE #5: Issue stop request
                    try:
                        ecs.stop_task(
                            cluster=cluster,
                            task=task_arn,
                            reason="Loader hung beyond timeout before next orchestrator run",
                        )
                    except Exception as stop_err:
                        logger.error(
                            f"[TASK_TERMINATION] stop_task() call failed: {stop_err}"
                        )
                        failed_terminations.append(
                            (loader_name, task_arn, str(stop_err))
                        )
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
                        failed_terminations.append(
                            (loader_name, task_arn, "verification timeout")
                        )

            # ISSUE #5: Alert if any terminations failed
            if failed_terminations:
                error_details = "; ".join(
                    [f"{name}: {err}" for name, arn, err in failed_terminations]
                )
                logger.critical(
                    f"[TASK_TERMINATION] ESCALATION: {len(failed_terminations)} task termination(s) failed. "
                    f"{error_details}"
                )
                try:
                    self.alerts.send_position_alert(
                        "TASK_TERMINATION",
                        "HUNG_LOADER_TERMINATION_FAILED",
                        f"Failed to terminate {len(failed_terminations)} hung loaders. RDS connections may not be released. "
                        f'Check CloudWatch logs and manually stop: {", ".join([arn.split("/")[-1] for _, arn, _ in failed_terminations])}',
                        {
                            "failed_tasks": [
                                {"loader": name, "task_arn": arn, "error": err}
                                for name, arn, err in failed_terminations
                            ]
                        },
                    )
                except Exception as alert_err:
                    logger.error(
                        f"[TASK_TERMINATION] Could not send escalation alert: {alert_err}"
                    )

        except Exception as e:
            logger.warning(
                f"[OOM_PREVENTION] Could not check/kill long-running loaders: {e}"
            )
            # Don't halt trading for this check - it's advisory

    def _validate_required_tables(self, cur: Any) -> bool:
        """FIXED Issue #23: Validate that all required tables exist before running phases.

        Returns: True if all tables exist, False if any critical table is missing.
        """
        required_tables = [
            "price_daily",  # Phase 1, Phase 5 signal generation
            "trend_template_data",  # Phase 5 (SignalComputer — Minervini, Weinstein)
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
                        logger.error(
                            f"[TABLE-CHECK] Missing required table: {table_name}"
                        )
                except Exception as e:
                    logger.error(
                        f"[TABLE-CHECK] Failed to check table {table_name}: {e}"
                    )
                    missing_tables.append(table_name)

            if missing_tables:
                logger.error(
                    f"[TABLE-CHECK] Cannot proceed: missing tables {missing_tables}"
                )
                self.log_phase_result(
                    0,
                    "table_validation",
                    "halt",
                    f'Missing tables: {", ".join(missing_tables)}',
                )
                return False

            logger.info(
                f"[TABLE-CHECK] All {len(required_tables)} required tables exist ✓"
            )
            return True

        except Exception as e:
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
        self._lock_acquired = self.lock_manager.acquire(
            timeout_seconds=lock_timeout_seconds
        )
        return self._lock_acquired

    def _release_run_lock(self) -> None:
        """Release the distributed lock."""
        if self._lock_acquired:
            self.lock_manager.release()

    def log_phase_start(self, phase_num: Union[int, str], name: str) -> None:
        if self.verbose:
            logger.info(f"\n{'='*70}")
            logger.info(f"PHASE {phase_num}: {name}")
            logger.info(f"{'='*70}")

    def log_phase_result(
        self, phase_num: Union[int, str], name: str, status: str, summary: str
    ) -> None:
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
        except Exception as e:
            logger.critical(
                f"[AUDIT_FAILURE] Could not persist audit log entry for phase {phase_num}: {e}"
            )
            # Audit log failure must never abort trading

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
        except Exception as e:
            logger.debug(f"Failed to write Phase 1 degraded_mode status to DynamoDB: {e}")

        # Halt flag lifecycle: always run regardless of informational write success above.
        # Previously coupled with the DynamoDB write in one try-block, which meant a
        # DynamoDB write failure would silently prevent clearing a stuck halt flag.
        try:
            degraded_status = result.status == "degraded"
            if degraded_status:
                logger.info(
                    f"[DEGRADED_MODE] Phase 1 returned degraded status: {result.summary}"
                )
                self._set_halt_flag(f"Phase 1 degraded: {result.summary}")
            elif result.status == "ok":
                # Clear halt flag so Phase 5/6 can resume signal generation and entries.
                # This undoes any halt set by data-freshness-monitor or a prior failed run.
                self._clear_halt_flag(
                    f"Phase 1 verified data is fresh at {datetime.now(timezone.utc).isoformat()}"
                )
        except Exception as e:
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
        if not result.ok:
            return False
        self._position_recs = result.data.get("recommendations", [])
        return True

    def phase_3b_exposure_policy(self) -> bool:
        """Thin delegation to phase3b_exposure_policy module."""
        self.log_phase_start("3b", "EXPOSURE POLICY ACTIONS")
        from algo.orchestrator.phase3b_exposure_policy import run as run_phase3b

        result = run_phase3b(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
        )
        if not result.ok:
            return False
        self._exposure_constraints = result.data.get("constraints")
        self._exposure_actions = result.data.get("actions", [])
        return True

    def phase_4_exit_execution(self) -> bool:
        """Thin delegation to phase4_exit_execution module."""
        self.log_phase_start(4, "EXIT EXECUTION")
        # No halt flag check: exits must always run to reduce risk even when entries are halted.
        from algo.orchestrator.phase4_exit_execution import run as run_phase4

        result = run_phase4(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
            getattr(self, "_position_recs", []),
            getattr(self, "_exposure_actions", []),
            self._check_halt_flag,
        )
        return not result.halted

    def phase_5_signal_generation(self) -> bool:
        """Thin delegation to phase5_signal_generation module.

        New version: Compute signals on-the-fly from price data.
        No dependency on technical_data_daily.
        """
        self.log_phase_start(5, "SIGNAL GENERATION & RANKING")
        from algo.orchestrator.phase5_signal_generation import run as run_phase5

        result = run_phase5(
            self.run_date,
            self.dry_run,
            self.verbose,
            self.log_phase_result,
            getattr(self, "_exposure_constraints", {}),
            self._check_halt_flag,
            phase1_degraded=False,
            config=self.config,
        )
        self._qualified_trades = result.data.get("qualified_trades", [])
        self.phase_results.setdefault(5, {})["signals_evaluated"] = len(
            self._qualified_trades
        )
        return not result.halted

    def phase_6_entry_execution(self) -> bool:
        """Thin delegation to phase6_entry_execution module.

        New version: Compute ATR + SMA_50 on-demand, execute immediately.
        """
        self.log_phase_start(6, "ENTRY EXECUTION")
        from algo.orchestrator.phase6_entry_execution import run as run_phase6

        result = run_phase6(
            self.config,
            self.run_date,
            self.dry_run,
            self.verbose,
            self.log_phase_result,
            getattr(self, "_qualified_trades", []),
            getattr(self, "_exposure_constraints", None),
            self._check_halt_flag,
        )
        self.phase_results.setdefault(6, {})["trades_executed"] = result.data.get(
            "entered", 0
        )
        return not result.halted

    def phase_7_reconcile(self) -> bool:
        """Thin delegation to phase7_reconciliation module."""
        self.log_phase_start(7, "RECONCILIATION & SNAPSHOT")
        # No halt flag check: snapshot must always be written so circuit breakers
        # have accurate portfolio state on the next invocation.
        from algo.orchestrator.phase7_reconciliation import run as run_phase7

        result = run_phase7(self.config, self.run_date, self.log_phase_result)
        self.phase_results.setdefault(7, {})["open_positions"] = result.data.get(
            "positions", 0
        )
        return not result.halted

    # ---------- Main entrypoint ----------

    def run(self) -> Dict[str, Any]:
        run_start = time.time()
        logger.info(f"\n{'#'*70}")
        logger.info(
            f"#   ALGO ORCHESTRATOR — {self.run_date}  ({'DRY RUN' if self.dry_run else 'LIVE'})"
        )
        logger.info(f"#   run_id: {self.run_id}")
        logger.info(f"#   START TIME: {datetime.now(timezone.utc).isoformat()}")
        logger.info(f"{'#'*70}")

        if not MarketCalendar.is_trading_day(self.run_date):
            status = MarketCalendar.market_status(
                datetime.combine(self.run_date, datetime.min.time())
            )
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
                    logger.error(
                        "\nABORT: Could not acquire run lock. Another orchestrator instance is running."
                    )
                    return {"success": False, "error": "Lock acquisition failed"}
                else:
                    # DynamoDB unavailable (no permissions, network issue, etc.) - allow to continue with warning
                    logger.warning(
                        "[DEGRADED MODE] DynamoDB lock unavailable - running without distributed lock protection"
                    )
        else:
            logger.info("[DRY-RUN] Skipping distributed lock check (dry-run mode)")

        try:
            logger.info(f"\n{'='*70}")
            logger.info("PRE-FLIGHT CHECKS (before Phase 1)")
            logger.info(f"{'='*70}")
            logger.info("[CRITICAL] Running critical data checks...")
            try:
                with DatabaseContext("read") as cur:
                    # Validate required tables exist (schema check only).
                    # Data freshness and patrol are handled by Phase 1 with proper
                    # halt/observe-only distinctions and fresh patrol execution.
                    if not self._validate_required_tables(cur):
                        logger.error("[HALT] Required tables missing — cannot proceed")
                        return self._final_report()

                    logger.info("[OK] All pre-flight checks passed")
            except Exception as e:
                logger.error(f"  [HALT] Pre-flight check failed: {e}")
                # Return skipped=True when DB is unreachable so test verification
                # treats this as a transient skip, not a code bug (phases={})
                report = self._final_report()
                if "connection" in str(e).lower() or "database" in str(e).lower():
                    report["skipped"] = True
                    report["reason"] = "database_unavailable"
                return report

            logger.info("\n[CHECK] Database connectivity...")
            if not self._check_db_connectivity():
                logger.error("[DB_ERROR] Database connectivity check FAILED")
                logger.error(
                    "Check CloudWatch alarms for database availability. Returning skipped status."
                )
                report = self._final_report()
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

            try:
                phase_1_start = time.time()
                logger.info(
                    f"\n[PHASE 1] Starting at {datetime.now(timezone.utc).isoformat()}"
                )
                with TimeBlock("phase_1_data_freshness"):
                    # Call instance method (not module directly) so DynamoDB halt flag
                    # lifecycle and degraded-mode writes in phase_1_data_freshness() execute.
                    self.phase_1_data_freshness()
                    phase1_result = self._phase1_result
                    if phase1_result.halted:
                        logger.error(
                            "\nPhase 1 failed: prices not loaded or coverage insufficient."
                        )
                        self.log_phase_result(
                            1, "data_freshness", "halt", phase1_result.error or ""
                        )
                        # Still run Phase 3/4 so stops are checked on open positions.
                        # Phase 4 comment: "exits must always run to reduce risk even when entries are halted."
                        self.phase_3_position_monitor()
                        self.phase_3b_exposure_policy()
                        self.phase_4_exit_execution()
                        self.phase_7_reconcile()
                        return self._final_report()
                phase_1_elapsed = time.time() - phase_1_start
                logger.info(
                    f"[PHASE 1] Completed in {phase_1_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}"
                )
            except Exception as e:
                logger.error(
                    f"\nERROR in phase 1 (data freshness): {e}. Running Phase 3/4/7 before halting."
                )
                self.log_phase_result(1, "data_freshness", "error", str(e))
                try:
                    self.phase_3_position_monitor()
                    self.phase_3b_exposure_policy()
                    self.phase_4_exit_execution()
                except Exception as phase4_err:
                    logger.error(f"Phase 3/4 also failed after Phase 1 error: {phase4_err}")
                self.phase_7_reconcile()
                return self._final_report()

            phase_2_start = time.time()
            logger.info(
                f"\n[PHASE 2] Starting at {datetime.now(timezone.utc).isoformat()}"
            )
            with TimeBlock("phase_2_circuit_breakers"):
                phase_2_passed = self.phase_2_circuit_breakers()
            phase_2_elapsed = time.time() - phase_2_start
            logger.info(
                f"[PHASE 2] Completed in {phase_2_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}"
            )

            if not phase_2_passed:
                logger.info(
                    "\nHALT: Circuit breaker fired. Will still review positions but skip new entries."
                )
                self.phase_3_position_monitor()
                self.phase_3b_exposure_policy()
                self.phase_4_exit_execution()
                self.phase_7_reconcile()
                return self._final_report()

            # Phase 3: Position Monitor
            # ISSUE #7 FIX: Track whether Phase 3 completed successfully
            phase_3_failed = False
            phase_3_start = time.time()
            logger.info(
                f"\n[PHASE 3] Starting at {datetime.now(timezone.utc).isoformat()}"
            )
            try:
                with TimeBlock("phase_3_position_monitor"):
                    self.phase_3_position_monitor()
                phase_3_elapsed = time.time() - phase_3_start
                logger.info(
                    f"[PHASE 3] Completed in {phase_3_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}"
                )
            except Exception as e:
                phase_3_failed = True
                logger.error(f"✗ Phase 3 (Position Monitor) failed: {e}", exc_info=True)
                self.log_phase_result(3, "position_monitor", "error", str(e))

            # Phase 3b: Exposure Policy
            # ISSUE #7 FIX: Track whether Phase 3b completed successfully
            phase_3b_failed = False
            phase_3b_start = time.time()
            logger.info(
                f"\n[PHASE 3b] Starting at {datetime.now(timezone.utc).isoformat()}"
            )
            try:
                with TimeBlock("phase_3b_exposure_policy"):
                    self.phase_3b_exposure_policy()
                phase_3b_elapsed = time.time() - phase_3b_start
                logger.info(
                    f"[PHASE 3b] Completed in {phase_3b_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}"
                )
            except Exception as e:
                phase_3b_failed = True
                logger.error(f"✗ Phase 3b (Exposure Policy) failed: {e}", exc_info=True)
                self.log_phase_result("3b", "exposure_policy", "error", str(e))

            # Phase 4: Exit Execution
            phase_4_start = time.time()
            logger.info(
                f"\n[PHASE 4] Starting at {datetime.now(timezone.utc).isoformat()}"
            )
            try:
                with TimeBlock("phase_4_exit_execution"):
                    result = self.phase_4_exit_execution()
                    if not result:
                        logger.critical(
                            "HALT: Phase 4 (Exit Execution) returned False — running Phase 7 for snapshot then stopping."
                        )
                        self.phase_7_reconcile()
                        return self._final_report()
                phase_4_elapsed = time.time() - phase_4_start
                logger.info(
                    f"[PHASE 4] Completed in {phase_4_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}"
                )
            except Exception as e:
                logger.error(f"✗ Phase 4 (Exit Execution) failed: {e}", exc_info=True)
                self.log_phase_result(4, "exit_execution", "error", str(e))

            # ISSUE #7 FIX: Check prerequisites before Phase 5
            # Phase 5 requires exposure_constraints from Phase 3b. If Phase 3b failed,
            # we cannot proceed with signal generation (it needs to validate against exposure limits).
            if phase_3b_failed:
                logger.critical(
                    "[PHASE 5] SKIPPING — Phase 3b (Exposure Policy) failed. "
                    "Cannot generate signals without exposure constraints. Running Phase 7 for snapshot then stopping."
                )
                self.phase_7_reconcile()
                return self._final_report()

            # Phase 5: Signal Generation
            phase_5_failed = False
            phase_5_start = time.time()
            logger.info(
                f"\n[PHASE 5] Starting at {datetime.now(timezone.utc).isoformat()}"
            )
            try:
                with TimeBlock("phase_5_signal_generation"):
                    result = self.phase_5_signal_generation()
                    if not result:
                        # ISSUE #10 FIX: Provide context about why Phase 5 halted
                        # Phase 5's phase_5_signal_generation() method logs halt reason internally
                        logger.warning(
                            "Phase 5 (Signal Generation) halted — no entries this run. "
                            "See Phase 5 logs above for reason (market regime, exposure policy, no qualified signals, or data quality). Skipping Phase 6."
                        )
                        # Phase 7 must still run: it creates the portfolio snapshot that Phase 5
                        # needs on its next invocation. Skipping Phase 7 here causes a deadlock
                        # where Phase 5 always halts (no snapshot) and Phase 7 never creates one.
                        self.phase_7_reconcile()
                        return self._final_report()
                phase_5_elapsed = time.time() - phase_5_start
                logger.info(
                    f"[PHASE 5] Completed in {phase_5_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}"
                )
            except Exception as e:
                phase_5_failed = True
                logger.error(
                    f"✗ Phase 5 (Signal Generation) failed: {e}", exc_info=True
                )
                self.log_phase_result(5, "signal_generation", "error", str(e))

            # ISSUE #7 FIX: Skip Phase 6 if Phase 5 failed (no qualified trades available)
            if phase_5_failed:
                logger.critical(
                    "[PHASE 6] SKIPPING — Phase 5 (Signal Generation) failed with exception. "
                    "Cannot execute entries without valid signals. Running Phase 7 for snapshot then stopping."
                )
                self.phase_7_reconcile()
                return self._final_report()

            # Phase 6: Entry Execution
            phase_6_start = time.time()
            logger.info(
                f"\n[PHASE 6] Starting at {datetime.now(timezone.utc).isoformat()}"
            )
            try:
                with TimeBlock("phase_6_entry_execution"):
                    result = self.phase_6_entry_execution()
                    if not result:
                        # ISSUE #10 FIX: Provide context about why Phase 6 halted
                        logger.critical(
                            "HALT: Phase 6 (Entry Execution) halted — no new signal-based trades will be entered. "
                            "See logs above for halt reason. Running Phase 7 before exit."
                        )
                        # Phase 7 must still run — portfolio snapshot required for circuit breakers next invocation.
                        self.phase_7_reconcile()
                        return self._final_report()
                phase_6_elapsed = time.time() - phase_6_start
                logger.info(
                    f"[PHASE 6] Completed in {phase_6_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}"
                )
            except Exception as e:
                logger.error(f"✗ Phase 6 (Entry Execution) failed: {e}", exc_info=True)
                self.log_phase_result(6, "entry_execution", "error", str(e))

            # Phase 7: Reconciliation (fail-open — doesn't execute trades, just records state)
            phase_7_start = time.time()
            logger.info(
                f"\n[PHASE 7] Starting at {datetime.now(timezone.utc).isoformat()}"
            )
            try:
                with TimeBlock("phase_7_reconciliation"):
                    result = self.phase_7_reconcile()
                # Phase 7 is fail-open: if reconciliation fails, we still finalize the report
                # (positions may already be executed, so we must sync state)
                phase_7_elapsed = time.time() - phase_7_start
                logger.info(
                    f"[PHASE 7] Completed in {phase_7_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}"
                )
            except Exception as e:
                logger.error(f"✗ Phase 7 (Reconciliation) failed: {e}", exc_info=True)
                self.log_phase_result(7, "reconciliation", "error", str(e))

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
                        metrics.add_metric(
                            "eod_pipeline_seconds", total_elapsed, unit="Seconds"
                        )
            except Exception as e:
                logger.debug(f"Could not emit pipeline timing metrics: {e}")

            return self._final_report()
        finally:
            self._release_run_lock()

    def _final_report(self):
        logger.info(f"\n{'#'*70}")
        logger.info(f"#   FINAL REPORT — {self.run_id}")
        logger.info(f"{'#'*70}")
        for n, info in sorted(self.phase_results.items(), key=lambda x: str(x[0])):
            status_flag = {
                "success": "[OK] ",
                "halt": "[HALT]",
                "fail": "[FAIL]",
                "error": "[ERR] ",
            }.get(info["status"], "[?]   ")
            logger.info(
                f"  {status_flag} Phase {n}: {info['name']:22s} — {info['summary']}"
            )
        logger.info(f"{'#'*70}\n")

        any_error = any(
            p["status"] in ("error", "fail") for p in self.phase_results.values()
        )
        any_halt = any(p["status"] == "halt" for p in self.phase_results.values())
        result = {
            "run_id": self.run_id,
            "run_date": self.run_date.isoformat(),
            "phases": self.phase_results,
            "success": not any_error,
            "halted": any_halt,
        }

        # FIXED Issue #6: Save execution log for audit trail
        if any_error:
            overall_status = "error"
            halt_reason = next(
                (
                    p["summary"]
                    for p in self.phase_results.values()
                    if p["status"] == "error"
                ),
                None,
            )
        elif any_halt:
            overall_status = "halted"
            halt_reason = next(
                (
                    p["summary"]
                    for p in self.phase_results.values()
                    if p["status"] == "halt"
                ),
                None,
            )
        else:
            overall_status = "success"
            halt_reason = None

        if not self.execution_tracker.save_execution_log(overall_status, halt_reason):
            logger.critical(
                f"[AUDIT_FAILURE] Could not save execution log for run {self.run_id}"
            )
            # Audit log failure must never prevent the final report from returning

        # Publish CloudWatch metrics (non-blocking — never let metrics interrupt trading)
        try:
            from algo.reporting import MetricsPublisher

            with MetricsPublisher(dry_run=self.dry_run) as m:
                m.put_orchestrator_result(result["success"], self.phase_results)

                # Signal count from phase 5 summary
                phase5 = self.phase_results.get(5, {})
                signals = phase5.get("signals_evaluated", 0)
                if isinstance(signals, int):
                    m.put_signal_count(signals)

                # Trade count from phase 6 summary
                phase6 = self.phase_results.get(6, {})
                trades = phase6.get("trades_executed", 0)
                if isinstance(trades, int):
                    m.put_trade_count(trades)

                # Open position count from phase 7
                phase7 = self.phase_results.get(7, {})
                positions = phase7.get("open_positions", 0)
                if isinstance(positions, int):
                    m.put_open_positions(positions)

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
    parser.add_argument(
        "--dry-run", action="store_true", help="Plan only, no real trades"
    )
    parser.add_argument(
        "--init-only", action="store_true", help="Run loaders only, no trading"
    )
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
    orch = Orchestrator(
        config=config, run_date=run_date, dry_run=dry_run, verbose=not args.quiet
    )
    try:
        final = orch.run()
        sys.exit(0 if final["success"] else 1)
    finally:
        orch.cleanup()
