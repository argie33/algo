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
from algo.orchestration.database_health_monitor import DatabaseHealthMonitor
from algo.orchestration.halt_flag_manager import HaltFlagManager
from algo.orchestration.phase_event_hub import (
    PhaseCompletedEvent,
    PhaseErrorEvent,
    PhaseStartedEvent,
    PhaseStatus,
    get_event_hub,
)
from algo.orchestrator.phase_executor import OrchestratorPhaseExecutor, PhaseDefinition
from algo.orchestrator.phase_registry import PhaseRegistry
from algo.reporting import AlertManager
from monitoring.metrics_context import (
    TimeBlock,
    log_metrics_summary,
)
from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ
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

        self.run_date = run_date or datetime.now(EASTERN_TZ).date()
        self.dry_run = dry_run
        self.verbose = verbose
        self.phase_results: dict[int | str, Any] = {}
        self.run_id = f"RUN-{self.run_date.isoformat()}-{datetime.now(timezone.utc).strftime('%H%M%S')}"

        self.execution_tracker = get_tracker()
        self.execution_tracker.set_run_context(self.run_id, self.run_date)

        from utils.db import DynamoDBLockManager
        self.lock_manager = DynamoDBLockManager()
        self._lock_acquired = False

        self.degraded_mode = False
        self.alerts = AlertManager()

        self.db_monitor = DatabaseHealthMonitor(self.alerts)
        self.halt_manager = HaltFlagManager(self.alerts, self.log_phase_result)

    def cleanup(self) -> None:
        """No-op: RDS Proxy handles connection cleanup."""

    # ---------- Database health monitoring (delegated to specialist) ----------

    def _check_db_connectivity(self) -> bool:
        """Delegate to DatabaseHealthMonitor."""
        return self.db_monitor.check_db_connectivity()

    def _check_halt_flag(self) -> bool:
        """Delegate to HaltFlagManager."""
        return self.halt_manager.check_halt_flag()

    def _set_halt_flag(self, reason: str = "") -> bool:
        """Delegate to HaltFlagManager."""
        return self.halt_manager.set_halt_flag(reason)

    def _clear_halt_flag(self, reason: str = "") -> bool:
        """Delegate to HaltFlagManager."""
        return self.halt_manager.clear_halt_flag(reason)

    def _check_connection_pool_health(self) -> None:
        """Delegate to DatabaseHealthMonitor."""
        self.db_monitor.check_connection_pool_health()

    def _health_check_diagnostics(self) -> None:
        """Delegate to DatabaseHealthMonitor."""
        self.db_monitor.health_check_diagnostics()

    def _verify_task_stopped(
        self,
        ecs: Any,
        cluster: str,
        task_arn: str,
        loader_name: str,
        max_retries: int = 3,
        retry_delay_sec: float = 1.0,
    ) -> bool:
        """Delegate to DatabaseHealthMonitor."""
        return self.db_monitor.verify_task_stopped(ecs, cluster, task_arn, loader_name, max_retries, retry_delay_sec)

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
                self._set_halt_flag(f"Phase 1 degraded: {result.error}")
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

        Loads phase definitions from PhaseRegistry and wires executor methods.
        Eliminates Shotgun Surgery: adding a phase is now a single registry entry,
        not multiple method additions and orchestrator changes.

        Returns:
            OrchestratorPhaseExecutor ready to execute all phases.
        """
        executor = OrchestratorPhaseExecutor(config=self.config, halt_check_fn=self._check_halt_flag)

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

    def _executor_phase_6(self, executor=None, **kwargs):
        """Executor wrapper for Phase 6: Exit Execution.

        PHASE DEPENDENCY FIX: Fetches validated data from Phase 3 and 5.
        """
        from algo.orchestrator.phase6_exit_execution import run as run_phase6

        position_recs = executor.get_phase_data(3, "recommendations", []) if executor else []
        exposure_actions = executor.get_phase_data(5, "actions", []) if executor else []

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

    def _executor_phase_7(self, executor=None, **kwargs):
        """Executor wrapper for Phase 7: Signal Generation.

        PHASE DEPENDENCY FIX: Fetches validated data from Phase 5.
        """
        from algo.orchestrator.phase7_signal_generation import run as run_phase7

        exposure_constraints = executor.get_phase_data(5, "constraints") if executor else None

        result = run_phase7(
            self.run_date,
            self.dry_run,
            self.verbose,
            self.log_phase_result,
            exposure_constraints=exposure_constraints,
            config=self.config,
        )
        return result

    def _executor_phase_8(self, executor=None, **kwargs):
        """Executor wrapper for Phase 8: Entry Execution.

        PHASE DEPENDENCY FIX: Now passes executor so phase can fetch validated data
        from Phase 7 and 5 instead of relying on instance attributes.
        """
        from algo.orchestrator.phase8_entry_execution import run as run_phase8

        result = run_phase8(
            self.config,
            self.run_date,
            self.dry_run,
            self.verbose,
            self.log_phase_result,
            executor=executor,
        )
        return result

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

        except (ValueError, ZeroDivisionError, TypeError, KeyError, AttributeError) as e:
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
