"""Orchestrator mixin (OrchestratorRunLoopMixin), extracted from orchestrator.py
(file-size ratchet split, 2026-09-10). Methods moved verbatim - no behavior change -
except call sites for names some test files patch at module level on
algo.orchestration.orchestrator (DatabaseContext/datetime/get_event_hub/run_phaseN)
now go through `_owner()` so that patching keeps working regardless of which mixin
file actually calls them; see `_owner()`'s own docstring. Mixed into Orchestrator via
multiple inheritance in orchestrator.py - every other `self.` call here resolves
normally through the instance regardless of which mixin file defines it.
"""

import logging
import os
from datetime import timezone
from typing import TYPE_CHECKING, Any

import psycopg2

from algo.infrastructure import MarketCalendar
from monitoring.metrics_context import TimeBlock, log_metrics_summary
from utils.infrastructure import EASTERN_TZ

if TYPE_CHECKING:
    from algo.orchestration._orchestrator_protocol import OrchestratorProtocol

    _Base = OrchestratorProtocol
else:
    _Base = object

logger = logging.getLogger(__name__)


def _owner() -> Any:
    """Lazy reference to the owner module (algo.orchestration.orchestrator), resolved at
    call time not import time. Several tests patch `algo.orchestration.orchestrator.
    DatabaseContext` / `.datetime` / `.get_event_hub` / `.run_phase1` / `.run_phase2` /
    `.run_phase9` directly (module-level monkeypatching) - a plain top-level import of
    those names in THIS file would bind this module's own separate copy, which those
    patches can never reach. Going through `_owner().X` always reads whatever the owner
    module's current attribute is, mocked or real - same pattern as loaders/helpers/
    vqg_quality.py's `_owner()` for the identical reason. Importing lazily (inside this
    function body, not at module level) also avoids a circular import, since the owner
    module is what imports THIS module.
    """
    from algo.orchestration import orchestrator as _owner_mod

    return _owner_mod


class OrchestratorRunLoopMixin(_Base):
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
            # SESSION 105 FIX: Clean up stale orchestrator run locks BEFORE acquisition attempt.
            # Previous implementation cleaned loader locks AFTER lock acquisition,
            # but stale orchestrator-run-lock blocks acquisition entirely.
            # Example: Friday orchestrator crashed, lock file never deleted, Saturday/Monday
            # runs fail immediately with "Could not acquire run lock" even though no process is running.
            # Fix: Cleanup stale run locks (>30 min old) before attempting acquisition.
            self._cleanup_stale_orchestrator_run_locks()

            lock_acquired = self._acquire_run_lock()
            if not lock_acquired:
                if self.lock_manager.is_available:
                    logger.error("\nABORT: Could not acquire run lock. Another orchestrator instance is running.")
                    # Unlike every other early-exit path in run(), this branch used to return
                    # without writing to execution_tracker/algo_orchestrator_runs, so a lock
                    # contention abort left zero record it ever happened.
                    halt_reason = "lock_contention: another orchestrator instance already holds the run lock"
                    try:
                        self.execution_tracker.save_execution_log("halted", halt_reason)
                        self._save_orchestrator_run_status("halted", halt_reason)
                    except Exception as e:
                        logger.warning(f"[EXECUTION_LOG] Could not save lock-contention status: {e}")
                    return {"success": False, "error": "Lock acquisition failed", "halted": True, "reason": halt_reason}
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
                    # Same silent-early-exit gap as the sibling branch above.
                    halt_reason = "lock_system_unavailable: distributed lock backend unreachable, failing closed"
                    try:
                        self.execution_tracker.save_execution_log("halted", halt_reason)
                        self._save_orchestrator_run_status("halted", halt_reason)
                    except Exception as e:
                        logger.warning(f"[EXECUTION_LOG] Could not save lock-unavailable status: {e}")
                    return {
                        "success": False,
                        "error": "Distributed lock system unavailable. Cannot proceed with trading.",
                        "halted": True,
                        "reason": halt_reason,
                    }
            self._install_shutdown_handler()
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
        # CRITICAL FIX: Enforce market hours guard ALWAYS, even in dry_run mode
        # Previous bug: dry_run=True bypassed this guard, allowing pre-market position creation during simulations
        # This caused 5 pre-market positions to be created on 2026-08-07 05:03 ET, which resulted in:
        # - Bad fills at market open
        # - 5 consecutive losses (triggered circuit breaker halt)
        # - Real portfolio damage from a test run
        #
        # dry_run mode should simulate WHAT WOULD HAPPEN, not change WHEN things happen.
        # Market hours guard is a safety check that must always apply.
        # Phase 8 also has this guard, but adding it here stops pre-market runs much earlier.
        # ALLOW_OUTSIDE_MARKET_HOURS=true still bypasses for explicit automated testing.
        from utils.infrastructure.market_timing import (
            MARKET_CLOSE_TIME,
            MARKET_OPEN_TIME,
            MONITOR_WINDOW_CLOSE_TIME,
        )

        allow_outside_hours = os.environ.get("ALLOW_OUTSIDE_MARKET_HOURS", "false").lower() == "true"

        # SAFETY HARDENING (2026-08-23): ALLOW_OUTSIDE_MARKET_HOURS is a local-testing-only
        # env var (not set by any deployed terraform/infra config - confirmed via full-repo
        # grep), documented in CLAUDE.md for exercising phase logic outside real market hours.
        # Nothing previously stopped it from ALSO bypassing this guard in execution_mode="auto"
        # (real live trading) if left set by human error (stale shell env, copy-pasted .env).
        # That would be more severe here than the equivalent gap already fixed in
        # phase8_entry_execution.py's own copy of this same guard: unlike Phase 8, Phase 6
        # (portfolio-rotation force-close) and Phase 9 (broker reconciliation/position-sync)
        # have NO independent market-hours check of their own - they rely entirely on this one
        # guard, so bypassing it here would let them run outside market hours with zero
        # remaining safety net. Force off in live mode regardless of the env var, with a loud
        # CRITICAL log so a real misconfiguration is never silently swallowed.
        if self.execution_mode == "auto" and allow_outside_hours:
            logger.critical(
                "[MARKET_HOURS_GUARD SAFETY] ALLOW_OUTSIDE_MARKET_HOURS is set but "
                "execution_mode='auto' (live trading) - ignoring it. This bypass is for "
                "paper/dry/review testing only and is never honored in live mode. No override "
                "may bypass the market-hours guard for real order execution."
            )
            allow_outside_hours = False

        now_et = _owner().datetime.now(EASTERN_TZ).time()
        # The evening/monitor-only run (dry_run=True, never places real orders - see
        # MONITOR_ONLY_RUN_IDENTIFIERS in lambda_function.py) is intentionally scheduled at
        # 5:30 PM ET, after MARKET_CLOSE_TIME. Only widen the UPPER bound for it; the lower
        # bound (MARKET_OPEN_TIME) stays identical for every run type, so this does not
        # reopen the pre-market incident (2026-08-07, 05:03 ET) this guard exists to prevent.
        window_close = MONITOR_WINDOW_CLOSE_TIME if self.dry_run else MARKET_CLOSE_TIME
        logger.info(
            f"[MARKET_HOURS_GUARD] Checking: allow_outside_hours={allow_outside_hours}, now_et={now_et}, market_open={MARKET_OPEN_TIME}, window_close={window_close}"
        )

        # Market hours enforced for ALL runs, UNLESS explicitly allowed - but dry_run
        # (monitor-only) runs get a later upper bound so the legitimate 5:30 PM evening slot
        # can pass this guard instead of skipping every single day (live-confirmed 2026-08-17).
        if not allow_outside_hours and not (MARKET_OPEN_TIME <= now_et < window_close):
            logger.critical(
                f"[MARKET_HOURS_GUARD] BLOCKING: Orchestrator run attempted outside market hours ({now_et.strftime('%H:%M:%S')} ET). "
                f"Allowed window: {MARKET_OPEN_TIME.strftime('%H:%M')} - {window_close.strftime('%H:%M')} ET. "
                f"This prevents pre-market/after-hours execution from corrupting production state. "
                f"To test outside market hours, use: ALLOW_OUTSIDE_MARKET_HOURS=true"
            )
            # CRITICAL FIX: Save to execution log BEFORE returning, so DB records the guard block
            # Previous: guard returned early without saving status, so DB showed "success" for blocked runs
            halt_reason = f"outside_market_hours: {now_et.strftime('%H:%M:%S')} ET"
            try:
                self.execution_tracker.save_execution_log("degraded", halt_reason)
                self._save_orchestrator_run_status("degraded", halt_reason)
                logger.debug("[EXECUTION_LOG] Saved degraded status for market hours guard block")
            except Exception as e:
                logger.warning(f"[EXECUTION_LOG] Could not save guard block status: {e}")

            return {
                "run_id": self.run_id,
                "run_date": self.run_date.isoformat(),
                "phases": [],
                "success": False,
                "halted": False,
                "skipped": True,
                "reason": f"outside_market_hours: {now_et.strftime('%H:%M:%S')} ET",
            }
        if MARKET_OPEN_TIME <= now_et < window_close:
            logger.info(f"[MARKET_HOURS_GUARD] OK: Current time {now_et} is within the allowed window")
        else:
            # allow_outside_hours is the only reason we got here while actually outside hours.
            # Previous message unconditionally claimed "within market hours" even on this path,
            # which erased the only signal (besides re-deriving it from raw env vars) that a
            # safety guard was bypassed rather than genuinely satisfied.
            logger.warning(
                f"[MARKET_HOURS_GUARD] BYPASSED via ALLOW_OUTSIDE_MARKET_HOURS=true: current time "
                f"{now_et} is OUTSIDE the allowed window ({MARKET_OPEN_TIME}-{window_close} ET). "
                f"Proceeding anyway because the guard was explicitly overridden."
            )

        logger.info("[CRITICAL] Running critical data checks...")

        # SESSION 105 FIX: Clean up idle-in-transaction connections before preflight
        # These connections poison the pool and cause all subsequent queries to timeout
        # with "canceling statement due to statement timeout" errors. This happens when:
        # 1. A transaction aborts on a connection
        # 2. Connection returned to pool WITHOUT proper rollback()
        # 3. Next query on that connection gets InFailedSqlTransaction
        # While Session 95 fixed the rollback on close, we also need to clean up
        # Idle-in-transaction sessions cleanup moved to Phase 1 startup
        # (see phase1_data_freshness._cleanup_stuck_database_sessions)

        try:
            logger.debug("[PREFLIGHT] Opening database context (timeout=10s)")
            with _owner().DatabaseContext("read", timeout=10) as cur:
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

        logger.info("\n[CHECK] Verifying Alpaca account type matches execution mode...")
        self._verify_alpaca_account_type()

        logger.info("\n[CHECK] Verifying database transaction isolation level...")
        self._verify_database_isolation_level()

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

        # Pipeline health monitoring runs AFTER phases execute (see run()) - not here.
        # It used to run pre-Phase-1, which meant its "latest_date" snapshot for every
        # table Phase 1-9 write to in THIS run (circuit_breaker_status every run via
        # Phase 2, algo_trades/algo_positions/algo_signals/algo_performance_daily/etc
        # whenever Phase 6/7/8/9 do) always reflected the PREVIOUS run's data, not this
        # run's. For circuit_breaker_status specifically (rewritten every single run,
        # sla_days=1) that meant the dashboard's data_loader_status-derived "Stale
        # detail" showed it ~1 day stale for the entire gap between runs, every day,
        # despite the table itself never actually going stale - live-confirmed
        # 2026-08-20: circuit_breaker_status.updated_at was 2.2h old (fresh) while its
        # data_loader_status row still held 2026-08-19's business date after that
        # morning's run, because the sweep ran before that run's Phase 2 wrote today's
        # row. See _run_pipeline_health_sweep().

        return None

    def _cleanup_stale_orchestrator_run_locks(self) -> None:
        """Clean up stale orchestrator run locks BEFORE acquisition attempt.

        SESSION 106 FIX: Aggressive cleanup to prevent hung loaders from blocking runs.
        - Orchestrator locks older than 20 min (was 30 min) = likely crashed
        - Loader locks older than 5 min (was 10 min via reaper) = certainly hung + killed

        Why aggressive: Hung loader monitor kills processes after 5min stall,
        but lock files may persist. Without cleanup, Friday hung loader blocks
        Saturday/Monday runs indefinitely.
        """
        try:
            from utils.db.local_file_lock import get_lock_manager

            lock_manager = get_lock_manager()
            if lock_manager and hasattr(lock_manager, "cleanup_expired_locks"):
                # Clean orchestrator locks >20 min old (typical run is 5-20 min)
                cleaned_orch = lock_manager.cleanup_expired_locks(
                    lock_key="orchestrator-run-lock", max_age_seconds=1200
                )
                # Clean ALL other locks >5 min old (hung loaders are killed after 5min stall)
                cleaned_loaders = lock_manager.cleanup_expired_locks(lock_key=None, max_age_seconds=300)
                if cleaned_orch > 0 or cleaned_loaders > 0:
                    logger.warning(
                        f"[LOCK_CLEANUP] Removed {cleaned_orch} orchestrator + {cleaned_loaders} loader locks. "
                        f"Likely stale from killed hung processes."
                    )
        except Exception as cleanup_err:
            logger.warning(
                f"[LOCK_CLEANUP_RUN] Failed to cleanup stale orchestrator locks: {cleanup_err}. Proceeding anyway."
            )

    def _cleanup_stale_loader_locks(self) -> None:
        """Clean up any stale loader locks from crashed or hung processes.

        SESSION 106 FIX: More aggressive cleanup for hung loaders.
        Local loader monitor kills hung processes after 5min stall + kills them.
        Any loader lock >5 min old indicates a process that was killed/hung.

        This is safe because:
        1. Legitimate loader runs take 10+ minutes minimum
        2. A lock older than 5 minutes with no active process = hung + killed
        3. Cleanup at orchestrator STARTUP, before phases run
        """
        try:
            from utils.db.local_file_lock import get_lock_manager

            lock_manager = get_lock_manager()
            if lock_manager and hasattr(lock_manager, "cleanup_expired_locks"):
                # max_age_seconds=600 deletes locks created 10+ minutes ago
                # This catches crashed loader processes much faster than waiting for TTL expiry
                cleaned = lock_manager.cleanup_expired_locks(max_age_seconds=600)
                if cleaned > 0:
                    logger.warning(
                        f"[LOCK_CLEANUP] Removed {cleaned} stale lock(s) from crashed loaders (older than 600s)"
                    )
        except Exception as cleanup_err:
            logger.warning(f"[LOCK_CLEANUP] Failed to cleanup stale locks: {cleanup_err}. Proceeding anyway.")

        # CRITICAL SESSION 105 FIX: Also reap loaders stuck RUNNING at 0% for hours
        # Lock files and status rows are separate - a crashed loader leaves both stuck.
        # This marks them FAILED so Phase 1 doesn't wait for ghosts and failsafe can retry.
        # Session 104 found: price_daily RUNNING 0% for 9min, etf_price_monthly RUNNING 0% for 130min,
        # company_info_sec RUNNING 0% for 162min. These were never reaped, blocking retry.
        logger.info("[STALE_LOADER_REAPER] Checking for loaders stuck RUNNING at 0%...")
        try:
            from utils.loaders.status_manager import reap_stale_running_loaders

            reaped = reap_stale_running_loaders()
            if reaped:
                logger.warning(f"[STALE_LOADER_REAPER] Reaped {len(reaped)} stuck loaders: {reaped}")
            else:
                logger.info("[STALE_LOADER_REAPER] No stale RUNNING loaders found (good)")
        except Exception as reaper_err:
            logger.warning(f"[STALE_LOADER_REAPER] Failed to reap stale loaders: {reaper_err}. Proceeding anyway.")

    def _wait_for_loaders_before_execution(self) -> None:
        """Wait for critical loaders to complete before executor runs."""
        logger.info("\n[PROACTIVE WAIT] Waiting for critical loaders to complete before Phase 1...")
        try:
            # REDUCED TIMEOUT (2026-08-05): price_daily loader stuck at 85.8%. Don't wait 5min.
            loaders_ready = self._wait_for_critical_loaders_proactive(max_wait_seconds=30)
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

            # Ensure ALL phases (executed or skipped) are logged to execution_tracker.
            # Phases that call log_phase_result_fn during execution are already in execution_tracker.
            # Phases that don't (including successful ones and skipped ones) need to be added now.
            # Without this, successful phases that don't explicitly call the callback won't appear
            # in orchestrator_execution_log, causing empty phase_results arrays and dashboard
            # visibility issues. This is a catch-all: log any phase not already in the tracker.
            if phase_num not in self.execution_tracker.phase_results:
                self.log_phase_result(phase_num, phase_result.phase_name, phase_result.status, summary)

            # Update orchestrator's in-memory tracking (used for console report)
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
        logger.info(f"[END TIME] {_owner().datetime.now(timezone.utc).isoformat()}")

        try:
            from algo.reporting import MetricsPublisher

            with MetricsPublisher() as metrics:
                metrics.put_loader_duration("orchestrator_run", total_elapsed)
                run_hour = _owner().datetime.now(EASTERN_TZ).hour
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

    def _run_pipeline_health_sweep(self) -> None:
        """Compute row_count/age_days/status for all ~94 tables in data_loader_status.

        Must run AFTER _execute_phases(), not before - see the comment left in
        _run_preflight_checks() where this call used to live. Non-blocking:
        failures here must never affect trading logic, only observability.
        """
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
