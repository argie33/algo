#!/usr/bin/env python3

import logging
import os
import sys
import time
from datetime import date as _date
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
from algo.orchestration.database_health_monitor import DatabaseHealthMonitor
from algo.orchestration.halt_flag_manager import HaltFlagManager
from algo.orchestration.phase_event_hub import (
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
from algo.reporting import AlertManager
from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ
from utils.logging import get_tracker

# Add project root (parent of parent of parent since we're in algo/orchestration)
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


logger = logging.getLogger(__name__)


# is_obviously_fake_alpaca_key() moved 2026-08-21 to algo/config/credential_manager.py
# (a lower-level module this file already imports from, never the reverse) so it can also
# guard get_alpaca_credentials()'s own database-fallback tier, not just this file's strict
# execution_mode="auto" startup gate - see that module's docstring for the full story.
# Re-exported here for backward compatibility with existing callers/tests that import it
# from this module.
from algo.config.credential_manager import is_obviously_fake_alpaca_key
from algo.orchestration.orchestrator_final_report import OrchestratorFinalReportMixin
from algo.orchestration.orchestrator_loader_health import OrchestratorLoaderHealthMixin
from algo.orchestration.orchestrator_phases_executor import OrchestratorPhasesMixin
from algo.orchestration.orchestrator_run_loop import OrchestratorRunLoopMixin
from algo.orchestration.orchestrator_startup import OrchestratorStartupMixin

# Kept here (even though no code in THIS file calls them directly) so they stay real
# attributes of algo.orchestration.orchestrator: the split-out mixin files above access
# them only via `_owner().X` (see each mixin's `_owner()` docstring), and several existing
# tests patch them at this exact module path (e.g. patch('algo.orchestration.orchestrator.
# run_phase2', ...)) - removing these as "unused" would silently break both.

# Genuine references (not just an import statement) so ruff's unused-import fixer never
# strips these - they must stay real module attributes for `_owner().X` and test patches
# at this exact module path (e.g. patch('algo.orchestration.orchestrator.run_phase2', ...))
# to keep working, even though no code in this file's own methods calls them directly.
_REEXPORTED_FOR_MODULE_LEVEL_PATCHABILITY = (
    is_obviously_fake_alpaca_key,
    get_event_hub,
    run_phase1,
    run_phase2,
    run_phase3,
    run_phase4,
    run_phase5,
    run_phase6,
    run_phase7,
    run_phase8,
    run_phase9,
    DatabaseContext,
)


def compute_run_mode_label(dry_run: bool, execution_mode: str, alpaca_paper_trading: bool) -> str:
    """Compute the run-mode label for the startup banner operators scan for real-money risk.

    dry_run alone does NOT mean real money is at risk - execution_mode="paper" (or "auto"
    with alpaca_paper_trading=True) still routes to Alpaca's paper endpoint. Only
    execution_mode="auto" with alpaca_paper_trading=False actually risks real money.
    Previously the banner printed "LIVE" for any non-dry-run, including ordinary local
    paper-mode test runs, which was indistinguishable in the logs from an actual real-money
    run.
    """
    if dry_run:
        return "DRY RUN"
    if execution_mode == "auto" and not alpaca_paper_trading:
        return "LIVE - REAL MONEY"
    return "PAPER"


class Orchestrator(
    OrchestratorStartupMixin,
    OrchestratorLoaderHealthMixin,
    OrchestratorPhasesMixin,
    OrchestratorRunLoopMixin,
    OrchestratorFinalReportMixin,
):
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
        db_execution_mode = self.config.get("execution_mode")
        # Recorded here (self.alerts isn't constructed yet) and sent once it is, a few lines
        # down - see _resolve_execution_mode's docstring for why this needs a real alert.
        self._execution_mode_mismatch_alert = self._resolve_execution_mode(env_execution_mode, db_execution_mode)

        # CRITICAL: Validate execution_mode is one of the supported values
        valid_execution_modes = {"paper", "dry", "review", "auto"}
        if self.execution_mode not in valid_execution_modes:
            raise ValueError(
                f"[STARTUP CRITICAL] Invalid execution_mode: '{self.execution_mode}'. "
                f"Must be one of: {', '.join(sorted(valid_execution_modes))}. "
                f"Note: 'live' is not supported; use 'auto' with alpaca_paper_trading=false for real-money trading. "
                f"Check ORCHESTRATOR_EXECUTION_MODE env var and algo_config table."
            )

        # CRITICAL FIX: Cache the DB execution_mode value to prevent race conditions
        # where config reloads/refreshes between startup validation and later checks
        # This snapshot ensures the validation at line ~350 uses the SAME value we validated here
        self._cached_db_execution_mode = db_execution_mode or self.execution_mode

        # Explicitly default run_date to today if not provided
        self.run_date = run_date if run_date is not None else datetime.now(EASTERN_TZ).date()
        self.dry_run = dry_run
        self.verbose = verbose
        self.phase_results: dict[int | str, Any] = {}
        # Use provided run_id if given (from EventBridge scheduler), otherwise generate one
        if run_id:
            self.run_id = run_id
        else:
            # CRITICAL FIX: Include microseconds to prevent run_id collision on same-second retries
            # Problem: If run fails at 14:23:45.900 and retries at 14:23:45.950,
            # same-second retry would generate identical run_id, breaking conflict detection
            # Solution: Include microseconds for uniqueness (prevents silent state corruption)
            now_utc = datetime.now(timezone.utc)
            self.run_id = f"RUN-{self.run_date.isoformat()}-{now_utc.strftime('%H%M%S')}-{now_utc.microsecond}"

        self.execution_tracker = get_tracker()
        self.execution_tracker.set_run_context(self.run_id, self.run_date)

        from utils.db.local_file_lock import get_lock_manager

        # BUG FIX 2026-08-31: get_lock_manager()'s own default lock_duration_seconds is 300s
        # (Session 107 lowered it from 600s for faster crashed-loader-lock cleanup), but
        # _acquire_run_lock()'s own docstring says "Orchestrator runs typically take 470+
        # seconds" - LONGER than the lock's own TTL. That means during every normal (non-crashed)
        # run, this lock's DynamoDB expires_at timestamp passes while the run is still actively
        # submitting real trades (around Phase 6-8) - any concurrent acquire() attempt from then
        # until release (a manual re-trigger, an EventBridge Scheduler retry, a second invocation
        # someone starts unaware one is already running) would see "expired" and succeed,
        # producing exactly the "two orchestrators running simultaneously against the same live
        # Alpaca account" scenario Session 282's fail-closed fix (below, this same class) was
        # written to prevent - that fix only covers the lock BACKEND being unavailable, not the
        # TTL being shorter than a real run. 1800s (30 min) gives a large safety margin over the
        # documented ~470s typical runtime while still bounding a genuinely crashed run's lock
        # hold time to something far short of the ~24h gap between scheduled production runs
        # (see terraform/prod.tfvars - only the 9:30 AM run is enabled).
        self.lock_manager = get_lock_manager(lock_duration_seconds=1800)
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

        if self._execution_mode_mismatch_alert:
            try:
                self.alerts.send_position_alert(
                    "ORCHESTRATOR", "EXECUTION_MODE_MISMATCH", self._execution_mode_mismatch_alert
                )
            except Exception as alert_err:
                logger.error(f"[STARTUP] Failed to send execution_mode mismatch alert (non-blocking): {alert_err}")

        self.db_monitor = DatabaseHealthMonitor(self.alerts)
        self.halt_manager = HaltFlagManager(self.alerts, self.log_phase_result)

        # NOTE: Alpaca credential validation deferred to Phase 4 (DailyReconciliation)
        # This allows Phases 1-3 (data refresh) to run even if Alpaca credentials are temporarily
        # unavailable. Credential validation happens when AlpacaSyncManager is instantiated in
        # Phase 4, failing the reconciliation phase but not blocking data pipelines.
        logger.info("[STARTUP] Orchestrator ready. Alpaca credentials will be validated in Phase 4.")

    def cleanup(self) -> None:
        """No-op: RDS Proxy handles connection cleanup."""

    def run(self) -> dict[str, Any]:
        self.run_start = time.time()
        # Use self.config's execution_mode (the algo_config DB value), NOT self.execution_mode
        # (the ORCHESTRATOR_EXECUTION_MODE env var) - the DB value is what actually governs
        # real order submission (TradeExecutor/HandlerContext read self.config, never
        # self.execution_mode), so the banner must reflect it or it can misreport real-money
        # risk in either direction. See _validate_startup_configuration's fail-fast check for
        # the same divergence, added 2026-07-28.
        run_mode_label = compute_run_mode_label(
            self.dry_run,
            self.config.get("execution_mode", "paper"),
            self.config.get("alpaca_paper_trading", True),
        )
        logger.info(f"\n{'#' * 70}")
        logger.info(f"#   ALGO ORCHESTRATOR - {self.run_date}  ({run_mode_label})")
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

            self._cleanup_stale_loader_locks()
            self._wait_for_loaders_before_execution()
            executor_result = self._execute_phases()
            self._run_pipeline_health_sweep()
            early_exit = self._handle_executor_result(executor_result)
            if early_exit is not None:
                return early_exit

            total_elapsed = time.time() - self.run_start
            self._emit_performance_metrics(total_elapsed)
            return self._final_report()
        except Exception as e:
            # GAP FOUND 2026-07-28: save_execution_log() is only ever called from
            # _save_early_exit_log() (preflight halts) and _final_report() (normal
            # completion) - both require this try block to return normally. But
            # phase_executor.py's execute_phase() deliberately re-raises RuntimeError for
            # governance violations (e.g. phase6_exit_execution.py's "Phase 3 crashed,
            # open positions unevaluated" / "credentials missing" checks) to crash the
            # whole orchestrator rather than silently continue - and neither this method,
            # its callers (lambda_function.py, run_local_orchestrator.py), nor Python's
            # default handler ever wrote anything to orchestrator_execution_log for that
            # crash. The run vanished from the one table the dashboard/API/health checks
            # query - indistinguishable from "never ran" instead of a visible halted/error
            # record, the exact "exit execution halted, not sure why" blind spot this
            # table exists to prevent. Record the crash, then re-raise unchanged - this
            # must not swallow the governance-violation crash, only make it forensically
            # visible.
            logger.critical(f"[ORCHESTRATOR CRASH] Unhandled exception during run: {type(e).__name__}: {e}")
            try:
                self.execution_tracker.save_execution_log("error", f"Orchestrator crashed: {type(e).__name__}: {e}")
            except Exception as log_err:
                logger.error(f"[ORCHESTRATOR CRASH] Could not save crash to execution log: {log_err}")
            raise
        finally:
            self._release_run_lock()
            self._restore_shutdown_handler()


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

    from algo.config.credential_validator import assert_credentials

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
