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

# CRITICAL: Set LOCAL_MODE FIRST before any imports that check it
# This must happen before load_env_local() and any credential/AWS operations
if "LAMBDA_TASK_ROOT" not in os.environ:
    os.environ.setdefault("LOCAL_MODE", "true")
    os.environ.setdefault("ENVIRONMENT", "development")

# CRITICAL: Load environment variables from .env.local BEFORE any boto3/AWS calls
# This must happen before any other imports that might trigger AWS operations
from utils.dotenv_loader import load_env_local

load_env_local()

from algo.config.environment_validation import EnvironmentValidator
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
    """Daily workflow runner with explicit phases.

    ## Phase Execution Model

    The orchestrator runs 9 phases in sequence with explicit dependency management:

    **Phases 1-5: Data & Risk Gates (Skip on Halt)**
    - Phase 1: Data Freshness - Verify prices, technicals, market data are fresh
    - Phase 2: Circuit Breakers - Check portfolio drawdown, VIX, market stage, loss streaks
    - Phase 3: Position Monitor - Check for single-stock halts, stale orders (ALWAYS_RUN)
    - Phase 4: Reconciliation - Sync algo_positions with broker Alpaca
    - Phase 5: Exposure Policy - Set entry constraints based on market regime

    **Phases 6-9: Trading & Risk Closure (Always Run, even if earlier phases halt)**
    - Phase 6: Exit Execution - Close losing positions (ALWAYS_RUN - risk management)
    - Phase 7: Signal Generation - Rank stocks, generate buy/sell signals
    - Phase 8: Entry Execution - Execute entry trades from Phase 7 signals
    - Phase 9: Reconciliation - Create final portfolio snapshot, P&L logs (ALWAYS_RUN)

    ## Halt Behavior

    If any Phase 1-5 fails or halts (e.g., stale data, circuit breaker triggered):
    - Phases 1-5 that haven't run yet: SKIP (fail-closed for safety)
    - Phases 6, 9: CONTINUE (must run to close positions and record final state)
    - Phase 3: ALWAYS runs (position monitoring is critical even during halt)
    - Phases 7-8: Depend on Phase 5 data - will fail if exit constraints unavailable

    ## Why Phase 3/6/9 Always Run

    Position monitoring, exit execution, and reconciliation are NON-NEGOTIABLE:
    - Phase 3: Must detect if a held stock is halted (NYSE/NASDAQ halt)
    - Phase 6: Must close positions during market emergencies (CB L1/L2/L3 triggered)
    - Phase 9: Must record true portfolio state (P&L, positions) for audit trail

    Without these always-running phases, the algo could:
    - Hold a halted stock indefinitely (position forever stuck)
    - Fail to exit during market circuit breaker events (catastrophic loss)
    - Have no reconciliation record of what happened (audit failure)

    This is by design - risk management gates override data staleness.
    """

    # Status display flags for final report
    _STATUS_FLAGS = {
        "ok": "[OK] ",
        "halted": "[HALT]",
        "fail": "[FAIL]",
        "error": "[ERR] ",
        "blocked": "[BLOCK]",
        "degraded": "[DEGRAD]",
        "skipped": "[SKIP]",
    }

    def __init__(
        self,
        config: Any,
        run_date: _date | None = None,
        dry_run: bool = False,
        verbose: bool = True,
        run_id: str | None = None,
    ) -> None:
        # PHASE 3 FIX: Validate environment variables FIRST, before any other initialization
        # This prevents silent failures from missing credentials or configuration
        EnvironmentValidator.require_valid_or_halt("orchestrator")

        if config is None:
            raise ValueError(
                "Orchestrator requires explicit config parameter (dependency injection). "
                "Remove fallback to get_config() - get config at entry point and pass it explicitly."
            )

        # CRITICAL FIX 2026-07-22: Session 344 - validate required config keys at startup
        # This catches configuration issues early, not at phase execution time
        required_config_keys = [
            "phase1_min_coverage_pct",
            "phase1_min_symbol_count",
            "min_win_rate_pct",
            "max_daily_loss_pct",
            "max_weekly_loss_pct",
        ]
        missing_keys = [k for k in required_config_keys if k not in config]
        if missing_keys:
            logger.critical(
                f"[ORCHESTRATOR STARTUP] CRITICAL: Configuration missing required keys: {missing_keys}. "
                f"Cannot proceed without these critical trading safety thresholds. "
                f"Verify all keys exist in algo_config table."
            )
            raise RuntimeError(
                f"[ORCHESTRATOR] Required config keys missing: {missing_keys}. "
                f"Check algo_config table for: {', '.join(required_config_keys)}"
            )

        # CRITICAL FIX Session 345: Validate config value ranges, not just key existence
        # Config values set to 0 or None would disable all trading (fatal misconfiguration)
        value_range_checks = [
            ("min_win_rate_pct", 0, 100),  # Must be 0-100% (usually 30-50%)
            ("max_daily_loss_pct", 0, 100),  # Must be 0-100% (usually 2-5%)
            ("max_weekly_loss_pct", 0, 100),  # Must be 0-100% (usually 5-10%)
            ("phase1_min_coverage_pct", 0, 100),  # Must be 0-100% (usually 80-95%)
            ("phase1_min_symbol_count", 10, 10000),  # Must be 10+ symbols (usually 4500+)
        ]

        for key, min_val, max_val in value_range_checks:
            if key in config and config[key] is not None:
                val = config[key]
                try:
                    val_float = float(val)
                    if val_float < min_val or val_float > max_val:
                        raise RuntimeError(
                            f"[ORCHESTRATOR STARTUP] CRITICAL: {key}={val} outside valid range [{min_val}, {max_val}]. "
                            f"This is a fatal misconfiguration that would disable trading. "
                            f"Verify algo_config table has correct values."
                        )
                except (ValueError, TypeError) as e:
                    raise RuntimeError(
                        f"[ORCHESTRATOR STARTUP] CRITICAL: {key}={val} is not a valid number: {e}. "
                        f"Check algo_config table value type and format."
                    ) from e

        self.config = config

        env_execution_mode = os.getenv("ORCHESTRATOR_EXECUTION_MODE", "").strip().lower()
        if env_execution_mode:
            logger.info(f"[STARTUP] ORCHESTRATOR_EXECUTION_MODE env var set: {env_execution_mode}")
            self.execution_mode = env_execution_mode
        else:
            # OrchestratorConfig doesn't have get() method - it's static class attributes
            # Default to paper trading for local/test environments
            self.execution_mode = "paper"
            logger.info(f"[STARTUP] ORCHESTRATOR_EXECUTION_MODE env var not set, defaulting to: {self.execution_mode}")

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

        from utils.db.local_file_lock import get_lock_manager

        self.lock_manager = get_lock_manager()
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

        # 2. Validate Alpaca credentials whenever orders are actually sent to Alpaca.
        # execution_mode == "auto" sends real orders to Alpaca's PAPER endpoint when
        # alpaca_paper_trading=True, and to the LIVE endpoint when False - both need valid
        # credentials to authenticate. Only "paper"/"dry"/"review" execution_mode never talks
        # to Alpaca at all (see executor.py's _submit_and_validate_order). Previously this
        # skipped validation entirely whenever alpaca_paper_trading=True, regardless of
        # execution_mode - so an "auto" + paper-trading config (a normal, common combination)
        # passed startup validation with no credentials, then failed later and confusingly
        # when Phase 8 Entry Execution actually tried to place an order and got a 401. That's
        # exactly the fail-fast violation this validator exists to prevent.
        if execution_mode in ("live", "auto"):
            try:
                from config.credential_manager import CredentialManager

                is_paper_trading = self.config.get("alpaca_paper_trading")
                if is_paper_trading is None:
                    raise RuntimeError(
                        "[STARTUP] CRITICAL: alpaca_paper_trading key must be explicitly set in algo_config. "
                        "Never assume defaults for trading mode. Set to True for paper trading, False for live."
                    )
                # Credentials are required regardless of is_paper_trading: it only selects
                # which Alpaca endpoint "auto" mode sends orders to (paper vs live), not
                # whether an authenticated request happens at all. Alpaca creds are stored as
                # fields inside the algo/alpaca secret, not as their own top-level
                # Secrets Manager entries -- get_alpaca_credentials() is the
                # accessor that knows this (get_password("APCA_API_KEY_ID") would
                # look for a secret literally named that, which never exists).
                api_key = None
                api_secret = None
                try:
                    alpaca_creds = CredentialManager().get_alpaca_credentials()
                    api_key = alpaca_creds.get("key")
                    api_secret = alpaca_creds.get("secret")
                except ValueError as e:
                    logger.debug(f"[STARTUP] get_alpaca_credentials() failed: {e}")

                # For LOCAL_MODE (development), also check algo_config table
                if (not api_key or not api_secret) and os.getenv("LOCAL_MODE") == "true":
                    logger.info("[LOCAL_MODE] Checking algo_config for Alpaca credentials...")
                    try:
                        with DatabaseContext("read") as cur:
                            cur.execute("SELECT value FROM algo_config WHERE key = %s", ["alpaca_api_key"])
                            result = cur.fetchone()
                            if result is not None and result[0]:
                                api_key = result[0]

                            cur.execute("SELECT value FROM algo_config WHERE key = %s", ["alpaca_api_secret"])
                            result = cur.fetchone()
                            if result is not None and result[0]:
                                api_secret = result[0]

                        if api_key and api_secret:
                            logger.info("[LOCAL_MODE] Loaded Alpaca credentials from algo_config")
                            # Set env vars so rest of code sees them
                            os.environ["APCA_API_KEY_ID"] = api_key
                            os.environ["APCA_API_SECRET_KEY"] = api_secret
                    except Exception as e:
                        logger.debug(f"[LOCAL_MODE] Could not load from algo_config: {e}")

                if not api_key or not api_secret:
                    raise RuntimeError(
                        f"[STARTUP] CRITICAL: Alpaca credentials missing for execution_mode={execution_mode!r} "
                        f"(alpaca_paper_trading={is_paper_trading}). Both 'auto' and 'live' send orders to "
                        "Alpaca and require valid credentials, whether targeting the paper or live endpoint. "
                        "Configure APCA_API_KEY_ID and APCA_API_SECRET_KEY via AWS Secrets Manager or environment."
                    )
                logger.info(f"[OK] Alpaca credentials validated for execution_mode={execution_mode!r}")
            except ValueError as e:
                raise RuntimeError(f"[STARTUP] Credential validation failed: {e}") from e
            except RuntimeError as e:
                # CRITICAL: Never silently fall back to paper mode on credential failures
                # This masks security degradation and operator loses awareness of auth issues
                logger.critical(
                    f"[CREDENTIAL VALIDATION FAILED] {e}. "
                    "Live trading configured but credentials unavailable. "
                    "Halting orchestrator. Configure credentials or set execution_mode to 'paper'."
                )
                raise RuntimeError(
                    f"[ORCHESTRATOR HALT] Credential validation failed: {e}. "
                    "Cannot proceed with trading when credentials unavailable. "
                    "Set execution_mode=paper or provide valid AWS credentials."
                ) from e
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
            # FIXED: Config validation IS critical - these errors must not be silently skipped
            if "CRITICAL" in str(e):
                raise
            logger.error(f"[STARTUP] Config validation FAILED (CRITICAL): {e}")
            raise RuntimeError(
                f"[ORCHESTRATOR] Config validation failed - cannot proceed with trading. "
                f"Error: {e}. Check: (1) Environment variables set, "
                f"(2) AWS Secrets Manager accessible, (3) Config keys in database."
            ) from e

        # 4. Validate database schema (required tables and views)
        try:
            with DatabaseContext("read") as cur:
                # Check algo_positions table exists (critical for portfolio monitoring)
                # Note: algo_positions is a BASE TABLE, not a view
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'algo_positions' AND table_schema = 'public'
                    ) AS table_exists
                    """)
                row = cur.fetchone()
                if not row or not row.get("table_exists"):
                    logger.error(
                        "[STARTUP] CRITICAL: algo_positions table NOT found. "
                        "This table is required for portfolio monitoring. "
                        "Run migrations to create required database objects."
                    )
                    raise RuntimeError(
                        "[ORCHESTRATOR] Required database table 'algo_positions' not found. "
                        "Run database migrations before starting orchestrator."
                    )
                else:
                    logger.info("[OK] Database schema validation passed: algo_positions table exists")
        except RuntimeError:
            raise
        except Exception as e:
            # FIXED: Database schema validation IS critical - cannot proceed without it
            logger.error(f"[STARTUP] Database schema validation FAILED (CRITICAL): {e}")
            raise RuntimeError(
                f"[ORCHESTRATOR] Cannot validate database schema: {e}. "
                f"Check: (1) Database connection working, "
                f"(2) Migrations have run, (3) Required views exist."
            ) from e

    def _kill_long_running_loaders(self) -> None:
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
                        f"[CRITICAL] Task missing startedAt field - cannot assess if hung. "
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
                        # Don't silently continue - mark as degraded so operator is aware task termination failed

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

    def _cleanup_expired_locks(self) -> None:
        """Clean up expired loader locks from database.

        Prevents stale locks from hung loaders from blocking future orchestrator runs.
        Automatically called during preflight checks to maintain lock table health.
        Session 391: Fixed stale signal_quality_scores lock that held 2-hour TTL.
        Session 398: Be more aggressive - delete locks held > 1 hour even if not expired.
        Session 428: Further improvement - lower threshold to 10 min and alert on stuck locks.
        """
        try:
            with DatabaseContext("write") as cur:
                # First: Alert on stuck locks BEFORE deleting them (for debugging)
                # Stuck locks indicate loader crash/hang - need visibility
                cur.execute("""
                    SELECT loader_name, locked_at,
                           EXTRACT(EPOCH FROM (NOW() - locked_at)) as duration_sec
                    FROM loader_execution_locks
                    WHERE EXTRACT(EPOCH FROM (NOW() - locked_at)) > 600
                    ORDER BY locked_at ASC
                """)
                stuck_locks = cur.fetchall()
                if stuck_locks:
                    logger.critical(
                        f"[LOCK_CLEANUP ALERT] {len(stuck_locks)} loader lock(s) held > 10 minutes (loader crash/hang suspected): "
                        + ", ".join([f"{name}({dur:.0f}s)" for name, _, dur in stuck_locks])
                    )

                # Second: Delete expired locks OR locks held > 10 minutes (more aggressive than 30min)
                # Loaders should complete within 10 minutes - anything longer indicates failure
                cur.execute("""
                    DELETE FROM loader_execution_locks
                    WHERE expires_at <= CURRENT_TIMESTAMP
                       OR EXTRACT(EPOCH FROM (NOW() - locked_at)) > 600
                """)
                deleted_count = cur.rowcount

                if deleted_count > 0:
                    logger.info(f"[LOCK_CLEANUP] Force-deleted {deleted_count} stuck loader lock(s) (held > 10min)")
        except Exception as e:
            logger.critical(f"[LOCK_CLEANUP FAILED] Could not clean expired locks: {e}. Loader pipeline may be blocked!")
            # Don't halt trading, but make this CRITICAL so ops team sees it

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
                            AND (status = 'running' OR completion_pct < 90.0)
                            ORDER BY completion_pct ASC
                            """,
                            (list(critical_loaders),),
                        )

                        incomplete_loaders = cur.fetchall()
                        if not incomplete_loaders:
                            logger.info("[PROACTIVE WAIT] All critical loaders are at 90%+ completion")
                            return True

                        # Still running - log progress and wait
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

        Logs warnings if critical loaders are missing or stale (>4 hours old) - this often
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
                now_et = now_utc.astimezone(EASTERN_TZ)

                # CRITICAL FIX: Staleness threshold is context-aware (not a fixed 4-hour window)
                # - During market hours (9:30 AM - 4 PM ET): loaders stale if ran before market open
                # - After market close (4 PM - 9:30 AM ET): loaders stale if didn't run in yesterday's EOD pipeline
                # This prevents false "all loaders stale" alerts for overnight batch jobs
                if 9 <= now_et.hour < 16:  # During market hours 9:30 AM - 3:59 PM ET
                    # Require fresh data from today's morning pipeline or intraday updates
                    # Morning loaders run at 2:15 AM, technical at 2:55 AM, metrics at 4:20 PM (yesterday)
                    # So require within ~13 hours for this use case
                    stale_threshold = now_utc - timedelta(hours=13)
                else:
                    # After market close: require data from yesterday's EOD pipeline (4-5:30 PM ET)
                    # If it's before market open (9:30 AM), require yesterday's data (ran 16+ hours ago)
                    stale_threshold = now_utc - timedelta(hours=36)

                for table_name, status, last_updated, completion_pct, symbols_loaded, symbol_count in cur.fetchall():
                    loaders_checked.add(table_name)
                    # CRITICAL FIX: Database stores timestamps as NAIVE in Eastern Time (-05:00).
                    # Convert to UTC for staleness comparison, not assume they're already UTC.
                    if last_updated:
                        last_updated_utc = last_updated.replace(tzinfo=EASTERN_TZ).astimezone(timezone.utc)
                    else:
                        last_updated_utc = None

                    # CRITICAL: Must explicitly determine staleness - no silent assumptions about loader health
                    if last_updated_utc is None:
                        logger.error(
                            f"[LOADER HEALTH] {table_name} cannot determine staleness: last_updated_utc is None. "
                            "Loader status unknown - cannot proceed without explicit timestamp."
                        )
                        raise RuntimeError(
                            f"Cannot determine loader staleness for {table_name}: no last_updated_utc timestamp. "
                            "Loader status unknown, must fail-fast instead of assuming fresh."
                        )

                    is_stale = last_updated_utc < stale_threshold

                    # CRITICAL: completion_pct is None only if database query failed or loader hasn't reported yet
                    # Treat None as incomplete (fail-safe) - don't silently use 0 (which looks like successful 0% load)
                    if completion_pct is None:
                        is_complete = False
                        logger.error(
                            f"[LOADER HEALTH] {table_name} completion_pct is NULL (database error or loader never reported). "
                            "Treating as incomplete until next status update."
                        )
                    else:
                        is_complete = completion_pct >= 90.0

                    loader_status[table_name] = {
                        "status": status,
                        "last_updated": last_updated_utc,
                        "is_stale": is_stale,
                        "is_complete": is_complete,
                        "completion_pct": completion_pct,
                    }

                    if is_stale:
                        # NOTE: last_updated cannot be None here (would have raised error on line 826)
                        # This null check was defensive but dead code - last_updated_utc is guaranteed valid
                        age_hours = (now_utc - last_updated_utc).total_seconds() / 3600
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
                # FIXED: Detect hung loaders (partial completion 1-94%), not just 0% or missing
                all_loaders_checked = dict(loader_status)
                all_stale_or_missing = len(all_loaders_checked) > 0 and all(
                    status["is_stale"] or status["completion_pct"] is None or not status.get("is_complete")
                    for status in all_loaders_checked.values()
                )

                if all_stale_or_missing and (stale_loaders or missing_loaders):
                    # LOCAL_MODE failsafe will refresh stale loaders, so don't fail pre-flight
                    local_mode = os.getenv("LOCAL_MODE", "").lower() in ("1", "true", "yes")

                    if not local_mode:
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

                        # FIXED: Remove paper mode bypass - data integrity is non-negotiable
                        # Paper trading still requires fresh data to be trustworthy for testing
                        # If loaders aren't running, fix the loader infrastructure, don't bypass validation
                        raise RuntimeError(
                            f"[ORCHESTRATOR] CRITICAL HALT: All critical loaders are stale/missing. "
                            f"Cannot proceed with trading (live or paper) using stale data. "
                            f"Paper mode does NOT bypass data validation - test data must be fresh too. "
                            f"Stale loaders: {stale_loaders}. Missing loaders: {missing_loaders}. "
                            f"Fix: (1) Verify EventBridge scheduler firing loader pipelines, "
                            f"(2) Check ECS cluster has capacity to run loader tasks, "
                            f"(3) Review CloudWatch logs for loader failures, "
                            f"(4) Verify database connection pool has available connections, "
                            f"(5) Check if loader infrastructure (S3, Alpaca, yfinance) is accessible."
                        )
                    else:
                        # LOCAL_MODE: log as warning, Phase 1 failsafe will handle refresh
                        logger.warning(
                            f"[LOADER HEALTH] All loaders stale/missing - LOCAL_MODE will refresh. "
                            f"Stale: {stale_loaders}. Missing: {missing_loaders}."
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
            "trend_template_data",  # Phase 5 (SignalComputer - Minervini, Weinstein)
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
                # Normalize phase name: convert "ENTRY EXECUTION" -> "entry_execution"
                normalized_name = name.lower().replace(" ", "_")
                cur.execute(
                    """
                    INSERT INTO algo_audit_log (action_type, action_date, details, actor, status, created_at)
                    VALUES (%s, CURRENT_TIMESTAMP, %s, 'orchestrator', %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        f"phase_{phase_num}_{normalized_name}",
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

        # Informational DynamoDB write (phase1_degraded_mode key) - separate from halt flag
        # management so a DynamoDB write failure never prevents the halt flag from being cleared.
        # Skip in LOCAL_MODE (no AWS credentials available)
        local_mode = os.getenv("LOCAL_MODE", "").lower() in ("1", "true", "yes")
        logger.info(f"[PHASE1_DYNAMODB] LOCAL_MODE={local_mode}, env={os.getenv('LOCAL_MODE')}")
        if not local_mode:
            try:
                import boto3
                from botocore.exceptions import ClientError

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
            except ClientError as e:
                # Handle invalid AWS credentials gracefully.
                # DynamoDB write failures (permission denied, invalid token) don't block Phase 1.
                # This is informational only - halt flag management happens separately below.
                try:
                    error_dict = (
                        e.response.get("Error", {}) if hasattr(e, "response") and isinstance(e.response, dict) else {}
                    )
                    error_code = error_dict.get("Code", "UNKNOWN")
                    if error_code in ("UnrecognizedClientException", "AccessDenied", "AccessDeniedException"):
                        logger.info(
                            f"[PHASE1_DYNAMODB] Write skipped (invalid credentials): {error_code}. This is non-blocking."
                        )
                    else:
                        logger.warning(f"[PHASE1_DYNAMODB] Write failed ({error_code}): {e!s}")
                except Exception as validation_error:
                    logger.warning(
                        f"[PHASE1_DYNAMODB] Error parsing AWS response: {validation_error}. Original error: {e}"
                    )
            except Exception as e:
                # Catch any other boto3 errors (missing env vars, network issues, etc.)
                logger.warning(f"[PHASE1_DYNAMODB] Unexpected error during DynamoDB write: {type(e).__name__}: {e}")
        else:
            logger.debug("[LOCAL_MODE] Skipping DynamoDB write for phase1_degraded_mode")

        # Halt flag lifecycle: MUST succeed or orchestrator fails
        # Halt flag is the safety mechanism that prevents trading during data issues.
        # If we can't manage halt flags, we have no safety guarantees - must fail-fast.
        degraded_status = result.status == "degraded"
        if degraded_status:
            logger.info(f"[DEGRADED_MODE] Phase 1 returned degraded status: {result.error}")
            halt_set_result = self.halt_manager.set_halt_flag(f"Phase 1 degraded: {result.error}")
            if not halt_set_result:
                raise RuntimeError(
                    "[GOVERNANCE VIOLATION] Halt flag could not be set despite degraded data status. "
                    "This is a critical safety failure - data may be stale but we can't stop trading. "
                    "Orchestrator MUST fail. Check database connectivity (RDS and DynamoDB) and AWS credentials."
                )
        elif result.status == "ok":
            # Clear halt flag after Phase 1 verified data is fresh
            # If this fails (both DynamoDB and RDS unavailable), clear_halt_flag() raises RuntimeError
            self.halt_manager.clear_halt_flag(
                f"Phase 1 verified data is fresh at {datetime.now(timezone.utc).isoformat()}"
            )

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
        # CRITICAL FIX: Set halt flag when circuit breaker fires so Phase 8 respects it
        # Previously only Phase 1 called set_halt_flag, leaving Phase 2 halts unheeded by later phases
        if result.halted:
            halt_reason = result.error or "Circuit breaker check failed"
            logger.info(f"[PHASE 2] Setting halt flag due to circuit breaker: {halt_reason}")
            self.halt_manager.set_halt_flag(halt_reason)
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
        if result.data is None or "recommendations" not in result.data:
            self.log_phase_result(
                3,
                "POSITION MONITOR",
                "error",
                "Phase 3 data contract violated: missing 'recommendations' key in result",
            )
            logger.error("Phase 3 returned ok=True but missing recommendations in data contract")
            return False
        recs = result.data["recommendations"]
        if not isinstance(recs, list):
            self.log_phase_result(
                3,
                "POSITION MONITOR",
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
        if result.data is None or "actions" not in result.data:
            self.log_phase_result(
                5,
                "EXPOSURE POLICY ACTIONS",
                "error",
                "Phase 5 data contract violated: missing 'actions' key in result",
            )
            logger.error("Phase 5 returned ok=True but missing actions in data contract")
            return False
        actions = result.data["actions"]
        if not isinstance(actions, list):
            self.log_phase_result(
                5,
                "EXPOSURE POLICY ACTIONS",
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

        PHASE DEPENDENCY FIX: Phase 6 has always_run=True, so it must execute even if Phase 3/5 fail.
        Falls back to database reads if phase data unavailable.

        CRITICAL: Even though Phase 6 always runs, we MUST log if dependencies are halted
        so operators understand why exit logic might be degraded.
        """
        if not executor:
            raise RuntimeError(
                "[PHASE 6] CRITICAL: Executor is None. Phase 6 requires validated data from Phases 3 and 5. "
                "This should never happen - check phase_executor.py initialization."
            )

        from algo.orchestrator.phase_data_contract import MissingPhaseDataError

        position_recs = []
        exposure_actions = []

        # Try to get Phase 3 data (position recommendations)
        # Note: Phase 6 always runs even if Phase 3 failed, but we must log degradation
        phase3_result = executor.get_result(3)
        if phase3_result and phase3_result.halted:
            logger.warning(
                f"[PHASE 6] Phase 3 halted: {phase3_result.error or 'unknown reason'}. "
                f"Phase 6 (always_run) continuing with degraded position monitoring. "
                f"Exits will proceed based on database state only."
            )

        try:
            position_recs = executor.get_phase_data_required(3, "recommendations")
        except MissingPhaseDataError as e:
            logger.warning(
                f"[PHASE 6] Phase 3 data unavailable: {e}. "
                f"Phase 6 (always_run) continuing with empty position_recs. "
                f"Exits will proceed based on database state only."
            )

        # Try to get Phase 5 data (exposure actions)
        # Note: Phase 6 always runs even if Phase 5 failed, but we must log degradation
        phase5_result = executor.get_result(5)
        if phase5_result and phase5_result.halted:
            # CRITICAL: Check if Phase 5 halted due to missing market regime data
            # This is a system-critical issue that should block exits until resolved
            halt_reason = phase5_result.error or "unknown reason"
            if "market" in halt_reason.lower() or "regime" in halt_reason.lower():
                logger.critical(
                    f"[PHASE 6 CRITICAL] Phase 5 halted due to missing market data: {halt_reason}. "
                    f"Cannot execute exits safely without market context. This is a system-critical failure."
                )
                # FAIL-FAST: Market regime data is non-negotiable for risk management
                raise RuntimeError(
                    f"[PHASE 6] Cannot execute exits: Phase 5 failed to load market regime data. "
                    f"Market exposure assessment is required for safe position management. {halt_reason}"
                )
            else:
                logger.warning(
                    f"[PHASE 6] Phase 5 halted: {halt_reason}. "
                    f"Phase 6 (always_run) continuing with position-monitor-only exits. "
                    f"Exposure policy enforcement may be degraded."
                )

        try:
            exposure_actions = executor.get_phase_data_required(5, "actions")
        except MissingPhaseDataError as e:
            logger.warning(
                f"[PHASE 6] Phase 5 data unavailable: {e}. "
                f"Phase 6 (always_run) continuing with empty exposure_actions. "
                f"Exits will proceed with position-monitor-only logic."
            )

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

        PHASE DEPENDENCY FIX: Fetches validated data from Phase 5 with halt checking.
        """
        if not executor:
            raise RuntimeError(
                "[PHASE 7] CRITICAL: Executor is None. Phase 7 requires exposure constraints from Phase 5. "
                "Cannot execute signal generation without validated market exposure constraints. "
                "This should never happen - check phase_executor.py initialization."
            )

        # CRITICAL FIX: Check if Phase 5 was halted/failed before extracting data
        phase5_result = executor.get_result(5)
        if phase5_result is None:
            error_msg = "[PHASE 7] Phase 5 (Exposure Policy) never executed - dependency chain broken"
            logger.critical(error_msg)
            self.log_phase_result(7, "SIGNAL GENERATION & RANKING", "halt", error_msg)
            from algo.orchestrator.phase_result import PhaseResult

            return PhaseResult(
                7,
                "SIGNAL GENERATION & RANKING",
                "halted",
                {"qualified_trades": [], "liquidity_passed": 0},
                True,
                error_msg,
            )

        if phase5_result.halted:
            error_msg = f"[PHASE 7] Phase 5 halted: {phase5_result.error or 'unknown reason'}"
            logger.critical(error_msg)
            self.log_phase_result(7, "SIGNAL GENERATION & RANKING", "halt", error_msg)
            from algo.orchestrator.phase_result import PhaseResult

            return PhaseResult(
                7,
                "SIGNAL GENERATION & RANKING",
                "halted",
                {"qualified_trades": [], "liquidity_passed": 0},
                True,
                error_msg,
            )

        if not phase5_result.ok:
            error_msg = f"[PHASE 7] Phase 5 failed: status={phase5_result.status}, error={phase5_result.error}"
            logger.critical(error_msg)
            self.log_phase_result(7, "SIGNAL GENERATION & RANKING", "halt", error_msg)
            from algo.orchestrator.phase_result import PhaseResult

            return PhaseResult(
                7,
                "SIGNAL GENERATION & RANKING",
                "halted",
                {"qualified_trades": [], "liquidity_passed": 0},
                True,
                error_msg,
            )

        exposure_constraints = executor.get_phase_data_required(5, "constraints")

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

    def _handle_concurrency_lock(self) -> dict[str, Any] | None:
        # NOTE: Paper trading is NOT exempt from locking. Paper runs still write
        # shared production state (DB rows, live Alpaca paper-account orders), so
        # concurrent unlocked runs corrupt that state exactly like live trading would
        # (duplicate signals/orders, inconsistent portfolio snapshots).
        # CRITICAL: Distributed lock is ALWAYS required except for dry-run (which doesn't write).
        # The SKIP_ORCHESTRATOR_LOCK bypass has been PERMANENTLY REMOVED (Session 272).
        # If you need to skip locking for testing, use dry_run=True instead.
        skip_lock_check = self.dry_run

        if not skip_lock_check:
            lock_acquired = self._acquire_run_lock()
            if not lock_acquired:
                if self.lock_manager.is_available:
                    logger.error("\nABORT: Could not acquire run lock. Another orchestrator instance is running.")
                    return {"success": False, "error": "Lock acquisition failed"}
                else:
                    # CRITICAL FIX (Session 282): ALWAYS fail closed when DynamoDB locks unavailable.
                    # Session 281 removed LOCAL_MODE fallback to FileLockManager in get_lock_manager(),
                    # but this code still allowed fail-open in LOCAL_MODE creating race condition.
                    #
                    # Issue: Two concurrent LOCAL_MODE processes could both:
                    # 1. Get permission error from DynamoDB (is_available=False)
                    # 2. Check LOCAL_MODE env var (both see "true")
                    # 3. Both return None from this function (fail open)
                    # 4. Both proceed to execute orchestrator simultaneously
                    # 5. Both write to shared production DB and live Alpaca account
                    # Result: Duplicate orders, portfolio corruption, catastrophic losses
                    #
                    # Solution: Fail closed when DynamoDB unavailable, REGARDLESS of LOCAL_MODE.
                    # LOCAL_MODE testing must use DynamoDB distributed locks just like production.
                    # If you need to test without AWS access, use dry_run=True instead.
                    logger.critical(
                        "\nABORT: Distributed lock system unavailable (is_available=False). "
                        "Cannot verify single orchestrator instance. DynamoDB access required for all runs "
                        "(LOCAL_MODE included). LOCAL_MODE development still connects to shared production DB "
                        "and live Alpaca account, so distributed locking is non-negotiable. "
                        "Fix: Ensure AWS credentials available, or use dry_run=True for testing."
                    )
                    return {
                        "success": False,
                        "error": "Distributed lock system unavailable. Cannot proceed with trading.",
                    }
        else:
            # Only reason to skip lock is dry_run (which doesn't write to database/broker)
            if not self.dry_run:
                raise RuntimeError(
                    "[CRITICAL] Lock check was skipped but not dry_run. "
                    "This should never happen - distributed lock is ALWAYS required for non-dry-run executions. "
                    "Check for SKIP_ORCHESTRATOR_LOCK bypass in orchestrator initialization."
                )
            logger.info("[LOCK-SKIP] Skipping distributed lock check (dry-run mode - no database writes)")
        return None

    # ---------- Main entrypoint ----------

    def _run_preflight_checks(self) -> dict[str, Any] | None:
        """Run preflight checks. Returns early-exit response if checks fail, else None."""
        logger.info(f"\n{'=' * 70}")
        logger.info("PRE-FLIGHT CHECKS (before Phase 1)")
        logger.info(f"{'=' * 70}")

        logger.info("[CRITICAL] Checking market calendar...")
        if not MarketCalendar.is_trading_day(self.run_date):
            logger.critical(
                f"[MARKET_HALT] {self.run_date.strftime('%A, %B %d, %Y')} is NOT a trading day. "
                f"Orchestrator cannot execute trading logic on weekends/holidays. "
                f"GOVERNANCE: Trading must occur during market hours only."
            )
            # CRITICAL FIX: Do NOT call _final_report() for preflight early returns
            # _final_report() inserts to database, which we must NOT do for skipped runs
            # Build response dict directly without phases or database insertion
            return {
                "run_id": self.run_id,
                "run_date": self.run_date.isoformat(),
                "phases": [],
                "success": False,
                "halted": False,
                "skipped": True,
                "reason": f"non_trading_day: {self.run_date.strftime('%A')}",
            }
        logger.info(f"[OK] {self.run_date.strftime('%A')} is a trading day - proceeding with orchestration")

        # CRITICAL FIX: Market hours guard at orchestrator entry point
        # Prevents manual test runs outside market hours (9:30 AM - 4:00 PM ET) from corrupting production state
        # Phase 8 also has this guard, but adding it here stops pre-market runs much earlier
        # dry_run=True bypasses this to allow safe testing at any time
        from utils.infrastructure.market_timing import MARKET_CLOSE_TIME, MARKET_OPEN_TIME

        now_et = datetime.now(EASTERN_TZ).time()
        if not self.dry_run and not (MARKET_OPEN_TIME <= now_et < MARKET_CLOSE_TIME):
            logger.warning(
                f"[MARKET_HOURS_GUARD] Orchestrator run attempted outside market hours ({now_et.strftime('%H:%M:%S')} ET). "
                f"Market hours: {MARKET_OPEN_TIME.strftime('%H:%M')} - {MARKET_CLOSE_TIME.strftime('%H:%M')} ET. "
                f"This prevents pre-market manual testing from corrupting production state. "
                f"Use dry_run=True to test outside market hours safely."
            )
            return {
                "run_id": self.run_id,
                "run_date": self.run_date.isoformat(),
                "phases": [],
                "success": False,
                "halted": False,
                "skipped": True,
                "reason": f"outside_market_hours: {now_et.strftime('%H:%M:%S')} ET",
            }

        logger.info("[CRITICAL] Running critical data checks...")
        try:
            logger.debug("[PREFLIGHT] Opening database context (timeout=10s)")
            with DatabaseContext("read", timeout=10) as cur:
                logger.debug("[PREFLIGHT] Validating required tables")
                if not self._validate_required_tables(cur):
                    logger.error("[HALT] Required tables missing - cannot proceed")
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
        logger.info("[OK] Database connectivity check passed")

        logger.info("\n[CHECK] Monitoring RDS connection pool...")
        self.db_monitor.check_connection_pool_health()

        logger.info("\n[CHECK] Validating startup configuration...")
        self._validate_startup_configuration()

        logger.info("\n[CHECK] Killing long-running analytics loaders...")
        self._kill_long_running_loaders()

        logger.info("\n[CHECK] Cleaning up expired loader locks...")
        self._cleanup_expired_locks()

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

        # Wire up pipeline health monitoring (Session 286 fix)
        # Computes row_count and age_days for ALL 94 tables in data_loader_status
        logger.info("\n[PIPELINE MONITORING] Computing health for all 94 data tables...")
        try:
            from algo.monitoring import PipelineHealth

            health_monitor = PipelineHealth()
            pipeline_status = health_monitor.get_pipeline_status()
            health_monitor.log_health_check(pipeline_status)
            logger.info(
                f"[PIPELINE MONITORING] Health check complete: {pipeline_status.healthy_count}/{pipeline_status.total_count} tables healthy"
            )
            if pipeline_status.critical_alerts:
                logger.warning(f"[PIPELINE MONITORING] Critical alerts: {pipeline_status.critical_alerts}")
        except RuntimeError as e:
            logger.error(
                f"[PIPELINE MONITORING] Failed to log pipeline health: {e}. "
                f"Data quality visibility degraded - age_days may be NULL for some tables."
            )
        except Exception as e:
            logger.error(
                f"[PIPELINE MONITORING] Unexpected error during health check: {e}. "
                f"Proceeding anyway - monitoring is non-blocking."
            )

        return None

    def _wait_for_loaders_before_execution(self) -> None:
        """Wait for critical loaders to complete before executor runs."""
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

    def _execute_phases(self) -> dict[str, Any]:
        """Execute the 9-phase orchestration sequence and return executor result."""
        logger.info("\n[DEADLOCK PREVENTION] Checking if halt flag needs proactive clear...")
        self.halt_manager.proactive_clear_stale_halt()

        self.executor = self._setup_executor(skip_phases=None)
        with TimeBlock("orchestrator_executor"):
            executor_result = self.executor.run()

        executor_phases = executor_result.get("results")
        if executor_phases is None:
            raise RuntimeError(
                "[ORCHESTRATOR] CRITICAL: Phase executor returned None for results. "
                "Cannot proceed without phase execution details. Check orchestrator logs for phase failures."
            )
        for phase_num, phase_result in executor_phases.items():
            # Each phase already called self.log_phase_result() with its real human-readable
            # summary during execution (every _executor_phase_N wires log_phase_result_fn to
            # self.log_phase_result), which populated self.phase_results[phase_num] correctly
            # and forwarded it to the execution tracker / event hub / audit log. No phase ever
            # puts that text into PhaseResult.data["summary"] (phases use "reason" in .data, or
            # pass the summary straight to the callback) - .data["summary"] is always empty.
            # Re-deriving summary from it here, then calling log_phase_result() a SECOND time
            # with that empty string, overwrote the good value already recorded above with a
            # blank one - the actual cause of every phase showing an empty summary in the health
            # panel and orchestrator_execution_log despite phases computing real ones. Just keep
            # what was already logged; only fall back if a phase somehow never called the
            # callback (defensive, not the expected path).
            already_logged = self.phase_results.get(phase_num)
            summary = already_logged.get("summary", "") if already_logged else ""
            if not summary:
                summary = phase_result.data.get("summary", "") if phase_result.data else ""
            if not summary and phase_result.status in ("error", "halted", "degraded") and phase_result.error:
                summary = phase_result.error

            if (
                already_logged is not None
                and already_logged.get("status") != phase_result.status
                and phase_num in self.execution_tracker.phase_results
            ):
                # The phase called log_phase_result_fn() directly during execution with its own
                # ad-hoc status string ("halt", "alert", "warn", "no_signals", ...) - that raw
                # value already reached self.execution_tracker.phase_results (and, via it,
                # orchestrator_execution_log.phase_results, the JSON blob the dashboard health
                # panel reads) through the log_phase_result() call the phase made. The block
                # below corrects self.phase_results (THIS orchestrator instance's own dict, used
                # for the console report and any_error/any_halt/any_degraded aggregation below)
                # to phase_result.status, the canonical PhaseResult vocabulary ("ok"/"halted"/
                # "error"/"degraded"/"skipped") - but never told the tracker, so the persisted
                # record keeps the raw string forever. Confirmed live: phase 7's "no candidates
                # today" case logs "no_signals" (correctly classified as PhaseResult
                # status="degraded" - a normal, expected outcome) but health.py's status buckets
                # don't recognize "no_signals" and fall back to the error bucket, rendering a
                # completely ordinary zero-signal day as a red failure indicator. Keep the
                # tracker's copy in sync so the DB record - and everything downstream of it -
                # uses the same canonical vocabulary the orchestrator itself already trusts.
                self.execution_tracker.phase_results[phase_num]["status"] = phase_result.status

            if already_logged is None:
                # Phase never called log_phase_result_fn itself: this is the skip path inside
                # phase_executor.py's execute_phase() (skip_if_halted=True after an earlier
                # halt), which builds a PhaseResult directly and never calls phase.execute_fn -
                # so the log_phase_result_fn callback wired to it never fires. Previously this
                # only ever updated self.phase_results (this orchestrator instance's in-memory
                # dict, used solely for the console _final_report()), never
                # self.execution_tracker (utils/logging/execution_tracker.py, the tracker whose
                # phase_results actually gets JSON-serialized into orchestrator_execution_log
                # and counted into phases_completed/halted/errored). Result: every skipped
                # phase (4, 5, 7, 8 whenever an earlier phase halts) silently vanished from the
                # persisted audit trail and the health dashboard instead of showing as skipped -
                # confirmed live: a halted run's DB row phase_results only had phases 1/2/3/6/9,
                # phases 4/5/7/8 entirely absent rather than status="skipped". Route through the
                # canonical log_phase_result() (same path every executed phase already uses) so
                # skipped phases reach the DB, audit log, and event hub too.
                self.log_phase_result(phase_num, phase_result.phase_name, phase_result.status, summary)
            else:
                self.phase_results[phase_num] = {
                    "phase": phase_num,
                    "name": phase_result.phase_name,
                    "status": phase_result.status,
                    "summary": summary,
                }

        return executor_result

    def _handle_executor_result(self, executor_result: dict[str, Any]) -> dict[str, Any] | None:
        if "success" not in executor_result:
            raise RuntimeError(
                f"Executor result missing 'success' field. "
                f"Available keys: {list(executor_result.keys())}. "
                f"Cannot determine if execution succeeded."
            )

        if not executor_result["success"]:
            error_phase = executor_result.get("error_phase")
            if error_phase is None:
                raise ValueError(
                    f"[EXECUTOR] Execution failed but missing required 'error_phase' field. "
                    f"Cannot identify which phase halted. Result: {executor_result}"
                )
            logger.critical(f"[EXECUTOR] Phase sequence halted at Phase {error_phase}")
            return self._final_report()

        return None

    def _emit_performance_metrics(self, total_elapsed: float) -> None:
        """Emit orchestrator performance metrics to CloudWatch."""
        log_metrics_summary()
        logger.info(f"\n[TOTAL] Orchestrator run completed in {total_elapsed:.2f}s")
        logger.info(f"[END TIME] {datetime.now(timezone.utc).isoformat()}")

        try:
            from algo.reporting import MetricsPublisher

            with MetricsPublisher() as metrics:
                metrics.put_loader_duration("orchestrator_run", total_elapsed)
                run_hour = datetime.now(EASTERN_TZ).hour
                if run_hour < 10:
                    metrics.add_metric(
                        "morning_prep_pipeline_seconds",
                        total_elapsed,
                        unit="Seconds",
                    )
                else:
                    metrics.add_metric("eod_pipeline_seconds", total_elapsed, unit="Seconds")
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.debug(f"Could not emit pipeline timing metrics: {e}")

    def run(self) -> dict[str, Any]:
        self.run_start = time.time()
        logger.info(f"\n{'#' * 70}")
        logger.info(f"#   ALGO ORCHESTRATOR - {self.run_date}  ({'DRY RUN' if self.dry_run else 'LIVE'})")
        logger.info(f"#   run_id: {self.run_id}")
        logger.info(f"#   START TIME: {datetime.now(timezone.utc).isoformat()}")
        logger.info(f"{'#' * 70}")

        lock_result = self._handle_concurrency_lock()
        if lock_result is not None:
            return lock_result

        try:
            preflight_result = self._run_preflight_checks()
            if preflight_result is not None:
                # Save audit log even on early exit (non-trading day, preflight failures)
                self._save_early_exit_log(preflight_result)
                return preflight_result

            self._wait_for_loaders_before_execution()
            executor_result = self._execute_phases()
            early_exit = self._handle_executor_result(executor_result)
            if early_exit is not None:
                return early_exit

            total_elapsed = time.time() - self.run_start
            self._emit_performance_metrics(total_elapsed)
            return self._final_report()
        finally:
            self._release_run_lock()

    def _save_early_exit_log(self, exit_result: dict[str, Any]) -> None:
        """Save execution log for early exits (non-trading days, preflight failures).

        CRITICAL: Even when orchestrator exits early, we must record it for audit trail.
        """
        try:
            reason = exit_result.get("reason", "early_exit")
            status = "skipped" if exit_result.get("skipped") else "halted"

            self.execution_tracker.save_execution_log(status, reason)
            logger.debug(f"[EXECUTION_LOG] Saved early exit log: {reason}")
        except Exception as e:
            logger.warning(f"[EXECUTION_LOG] Could not save early exit log: {e}")

    def _final_report(self) -> dict[str, Any]:
        logger.info(f"\n{'#' * 70}")
        logger.info(f"#   FINAL REPORT - {self.run_id}")
        logger.info(f"{'#' * 70}")
        for n, info in sorted(self.phase_results.items(), key=lambda x: str(x[0])):
            status_flag = self._STATUS_FLAGS.get(info["status"], "[?]   ")
            logger.info(f"  {status_flag} Phase {n}: {info['name']:22s} - {info['summary']}")
        logger.info(f"{'#' * 70}\n")

        any_error = any(p["status"] in ("error", "fail") for p in self.phase_results.values())
        any_halt = any(p["status"] == "halted" for p in self.phase_results.values())
        any_degraded = any(p["status"] == "degraded" for p in self.phase_results.values())
        any_blocked = any(p["status"] == "blocked" for p in self.phase_results.values())
        any_skipped = any(p["status"] == "skipped" for p in self.phase_results.values())

        # CRITICAL FIX: If a phase has status="halted", it's a policy halt (e.g., circuit breaker),
        # not an error. Don't mark overall as "error" just because a halt occurred.
        # Priority: halted > error (a halt is a controlled stop, error is unexpected)
        if any_halt:
            any_error = False  # Halt takes precedence over error status

        # Determine reason for halt/skip if applicable
        skip_reason = None
        if any_error:
            skip_reason = next(
                (p["summary"] for p in self.phase_results.values() if p["status"] in ("error", "fail")),
                "orchestrator_error",
            )
        elif any_halt:
            skip_reason = next(
                (p["summary"] for p in self.phase_results.values() if p["status"] == "halted"),
                "circuit_breaker_halted",
            )
        elif any_degraded:
            skip_reason = next(
                (p["summary"] for p in self.phase_results.values() if p["status"] == "degraded"),
                "phase_degraded",
            )
        elif any_skipped:
            skip_reason = next(
                (p["summary"] for p in self.phase_results.values() if p["status"] == "skipped"),
                "phase_skipped",
            )

        result = {
            "run_id": self.run_id,
            "run_date": self.run_date.isoformat(),
            "phases": [{"phase": n, **info} for n, info in sorted(self.phase_results.items(), key=lambda x: str(x[0]))],
            "success": not (any_error or any_halt or any_degraded or any_skipped),  # blocked handled separately below
            "halted": any_halt,  # Only actual halts (circuit breaker, errors) - not degraded/skipped
            "skipped": any_halt or any_degraded or any_skipped or any_blocked,  # Required by Lambda handler
            "reason": skip_reason or "none",  # Required by Lambda handler
        }

        # FIXED Issue #6: Save execution log for audit trail
        try:
            if any_error:
                overall_status = "error"
                # Look for error/fail status phases first, then halted (some phases use "halted" for errors)
                halt_reason = next(
                    (p["summary"] for p in self.phase_results.values() if p["status"] in ("error", "fail", "halted")),
                    "Unknown error - no phase summary available",
                )
            elif any_halt:
                overall_status = "halted"
                halt_reason = next(
                    (p["summary"] for p in self.phase_results.values() if p["status"] == "halted"),
                    "Halted - reason unknown",
                )
            elif any_degraded:
                overall_status = "degraded"
                halt_reason = next(
                    (p["summary"] for p in self.phase_results.values() if p["status"] == "degraded"),
                    "Degraded - reason unknown",
                )
            elif any_blocked:
                # CRITICAL: "blocked" means a safety guard stopped Phase 8 (risk limit, pending orders, market hours).
                # This is EXPECTED and CORRECT behavior - a guard preventing over-leveraging is not a failure.
                # If Phase 9 still runs and succeeds, the run is healthy.
                phase_8_blocked = any(
                    p["status"] == "blocked" and p.get("phase") == 8
                    for p in self.phase_results.values()
                )
                # FAIL-FAST: Phase 9 must be present (always_run) - no fallback to alternate key type
                # CRITICAL FIX: phase_results should ALWAYS use int keys (9, not "9").
                # Trying both key types masks inconsistency in how phases store results.
                if 9 not in self.phase_results:
                    raise RuntimeError(
                        f"[ORCHESTRATOR CRITICAL] Phase 9 results missing from phase_results. "
                        f"Phase 9 is always_run=True and MUST be present for status determination. "
                        f"Available phase keys: {sorted(self.phase_results.keys())}. "
                        f"Key types should be int only. This indicates a bug in phase_executor or phase execution flow."
                    )
                phase_9_data = self.phase_results[9]
                if not phase_9_data:
                    raise RuntimeError(
                        f"[ORCHESTRATOR CRITICAL] Phase 9 result is empty dict. "
                        f"Phase 9 must return non-empty result with phase/name/status/summary fields."
                    )
                phase_9_succeeded = phase_9_data.get("status") in ("ok", "success")

                if phase_8_blocked and phase_9_succeeded:
                    # Phase 8 blocked by guard but Phase 9 (always_run) succeeded - healthy run with guard
                    overall_status = "ok"
                    halt_reason = next(
                        (p["summary"] for p in self.phase_results.values() if p["status"] == "blocked"),
                        "Blocked by guard - reason unknown",
                    )
                else:
                    # Block was unexpected or Phase 9 failed - mark as degraded
                    overall_status = "degraded"
                    halt_reason = next(
                        (p["summary"] for p in self.phase_results.values() if p["status"] == "blocked"),
                        "Blocked - reason unknown",
                    )
            elif any_skipped:
                # CRITICAL: Distinguish between "skipped due to market hours" vs "skipped due to upstream failure"
                # Phase 8 skipping due to market hours guard is EXPECTED and CORRECT behavior (9:30 AM - 4:00 PM ET).
                # If Phase 8 skipped for this reason and always-run Phase 9 succeeded, the run is healthy ("ok").
                # Only mark as "degraded" if skip was due to upstream phase failure.
                phase_8_market_hours_skip = any(
                    p["status"] == "skipped" and "MARKET HOURS GUARD" in p.get("summary", "")
                    for p in self.phase_results.values()
                )
                # FAIL-FAST: Phase 9 must be present (always_run) - no fallback to alternate key type
                # CRITICAL FIX: phase_results should ALWAYS use int keys (9, not "9").
                # Trying both key types masks inconsistency in how phases store results.
                if 9 not in self.phase_results:
                    raise RuntimeError(
                        f"[ORCHESTRATOR CRITICAL] Phase 9 results missing from phase_results. "
                        f"Phase 9 is always_run=True and MUST be present for status determination. "
                        f"Available phase keys: {sorted(self.phase_results.keys())}. "
                        f"Key types should be int only. This indicates a bug in phase_executor or phase execution flow."
                    )
                phase_9_data = self.phase_results[9]
                if not phase_9_data:
                    raise RuntimeError(
                        f"[ORCHESTRATOR CRITICAL] Phase 9 result is empty dict. "
                        f"Phase 9 must return non-empty result with phase/name/status/summary fields."
                    )
                phase_9_succeeded = phase_9_data.get("status") in ("ok", "success")

                if phase_8_market_hours_skip and phase_9_succeeded:
                    # Phase 8 skipped due to market hours but Phase 9 (always_run) succeeded - healthy run
                    overall_status = "ok"
                    halt_reason = next(
                        (p["summary"] for p in self.phase_results.values() if p["status"] == "skipped"),
                        "Skipped - reason unknown",
                    )
                else:
                    # Skip was due to upstream failure or other issue - mark as degraded
                    overall_status = "degraded"
                    halt_reason = next(
                        (p["summary"] for p in self.phase_results.values() if p["status"] == "skipped"),
                        "Skipped - reason unknown",
                    )
            else:
                overall_status = "success"
                halt_reason = None

            # Update result dict to reflect overall_status determination
            # (especially for blocked guards that ended up as ok_status)
            result["success"] = overall_status in ("success", "ok")

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

        # Publish CloudWatch metrics (non-blocking - never let metrics interrupt trading)
        try:
            from algo.reporting import MetricsPublisher

            with MetricsPublisher(dry_run=self.dry_run) as m:
                m.put_orchestrator_result(bool(result["success"]), {str(k): v for k, v in self.phase_results.items()})

                # Extract numeric data from executor phase results (not self.phase_results)
                if hasattr(self, "executor") and self.executor:
                    # Signal count from phase 7 (signal generation)
                    phase7_result = self.executor.get_result(7)
                    if phase7_result and hasattr(phase7_result, "data"):
                        # CRITICAL: Check phase status before using defaults
                        # Distinguish: "phase halted" (0 attempted) vs "found 0 signals" (0 generated)
                        if phase7_result.halted:
                            # Phase was halted (upstream failure) - don't attempt to extract metrics
                            logger.debug(f"Phase 7 halted (reason: {phase7_result.error}), skipping metrics")
                            # Do NOT put signal count - let it remain None in metrics
                        else:
                            # Phase ran (halted=False) - extract signal count with explicit validation
                            signals = phase7_result.data.get("liquidity_passed")
                            if signals is None:
                                # Phase succeeded but field is missing - this is an error in phase data contract
                                logger.error(
                                    f"Phase 7 succeeded but missing 'liquidity_passed' field. "
                                    f"Data contract violation. Available keys: {list(phase7_result.data.keys())}"
                                )
                                # Don't put count - metrics will show None (data unavailable)
                            elif not isinstance(signals, int):
                                logger.warning(
                                    f"Phase 7 'liquidity_passed' has unexpected type {type(signals).__name__}: {signals!r}. "
                                    f"Signal count should be explicit integer."
                                )
                                # Don't put count - let it remain None
                            else:
                                m.put_signal_count(signals)
                    else:
                        logger.debug("Phase 7 result not found in executor")
                        # Don't put signal count - let it remain None in metrics

                    # Trade count from phase 8 (entry execution)
                    phase8_result = self.executor.get_result(8)
                    if phase8_result and hasattr(phase8_result, "data"):
                        if phase8_result.halted:
                            logger.debug(f"Phase 8 halted (reason: {phase8_result.error}), skipping metrics")
                        else:
                            trades = phase8_result.data.get("entered")
                            if isinstance(trades, int):
                                m.put_trade_count(trades)
                            elif trades is None:
                                logger.error(
                                    f"Phase 8 succeeded but missing 'entered' field. "
                                    f"Data contract violation. Available keys: {list(phase8_result.data.keys())}"
                                )
                            else:
                                logger.warning(f"Phase 8 returned non-int entered count: {type(trades).__name__}")
                    else:
                        logger.debug("Phase 8 result not found in executor")

                    # Open position count from phase 9 (reconciliation)
                    phase9_result = self.executor.get_result(9)
                    if phase9_result and hasattr(phase9_result, "data"):
                        if phase9_result.halted:
                            logger.debug(f"Phase 9 halted (reason: {phase9_result.error}), skipping metrics")
                        else:
                            positions = phase9_result.data.get("positions")
                            if isinstance(positions, int):
                                m.put_open_positions(positions)
                            elif positions is None:
                                logger.error(
                                    f"Phase 9 succeeded but missing 'positions' field. "
                                    f"Data contract violation. Available keys: {list(phase9_result.data.keys())}"
                                )
                            else:
                                logger.warning(f"Phase 9 returned non-int positions: {type(positions).__name__}")
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
    # LOCAL_MODE already set at module import (line 16-18)
    # No additional setup needed here - just continue with argument parsing

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
