#!/usr/bin/env python3
"""Centralized loader status management - ensures consistent status updates across all loaders.

CRITICAL: Use this for ALL loader status updates. Eliminates copy-paste bugs and status inconsistency.

Usage:
    from utils.loaders.status_manager import LoaderStatusManager
    from utils.loaders.status_enum import LoaderStatus

    manager = LoaderStatusManager(table_name="price_daily")

    # Start loader
    manager.mark_running()  # Sets status=RUNNING, execution_started=NOW

    # Log progress
    manager.update_progress(symbols_loaded=100, symbol_count=5000, completion_pct=2.0)

    # Finish (success)
    manager.mark_completed()  # Sets status=COMPLETED, execution_completed=NOW

    # Or finish (error)
    manager.mark_failed("Connection timeout after 5 retries")
"""

import logging
from typing import Any

from utils.db import DatabaseContext
from utils.loaders.status_enum import LoaderStatus

logger = logging.getLogger(__name__)


class LoaderStatusManager:
    """Manage loader status updates with validation and consistency checks.

    ISSUE #9 FIX: All status updates wrapped in advisory locks to prevent
    concurrent progress updates from overwriting counts. Uses PostgreSQL
    pg_advisory_lock() for application-level locking.
    """

    def __init__(self, table_name: str) -> None:
        """Initialize status manager for a specific loader table.

        Args:
            table_name: Name of the table this loader updates (e.g., 'price_daily')

        Raises:
            ValueError: table_name is empty/falsy. Confirmed live 2026-08-03: a caller
                somewhere constructed this with an empty string, and _ensure_status_row_exists's
                INSERT ... ON CONFLICT DO NOTHING happily created a permanent
                data_loader_status row keyed by '' - not tied to any real table, so no loader
                ever updates its symbol_count/symbols_loaded, so every mark_completed() call
                against it hits the <98%-completion safety check and marks it FAILED, forever
                incrementing consecutive_failures. pipeline_health.py's secondary-table sweep
                (SELECT DISTINCT table_name FROM data_loader_status) then picks up this
                phantom row and logs "Error checking secondary table : Empty table name" on
                every single health check. Failing fast here prevents the row from ever
                being created again.
        """
        if not table_name:
            raise ValueError(f"LoaderStatusManager requires a non-empty table_name, got {table_name!r}")
        self.table_name = table_name
        self._ensure_status_row_exists()

    def _acquire_lock(self, timeout: int = 10) -> None:
        """No-op for backwards compatibility.

        REMOVED: Advisory locks were broken - pg_advisory_lock acquired in one connection
        but released when that connection closed, leaving no lock for subsequent operations.
        Replaced with SELECT FOR UPDATE which holds lock within transaction.

        This method is kept for backwards compatibility but does nothing.
        Lock acquisition now happens inline in mark_running/update_progress/etc.
        """

    def _release_lock(self) -> None:
        """No-op for backwards compatibility - transaction-level locks auto-release.

        REMOVED: Advisory locks were broken. SELECT FOR UPDATE locks are automatically
        released when the transaction commits (or rolls back).

        This method is kept for backwards compatibility but does nothing.
        """

    def _ensure_status_row_exists(self) -> None:
        """Create data_loader_status row if it doesn't exist.

        Initializes with status=NOT_STARTED (loader hasn't run yet).
        """
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO data_loader_status (table_name, status)
                    VALUES (%s, %s)
                    ON CONFLICT (table_name) DO NOTHING
                    """,
                    (self.table_name, LoaderStatus.NOT_STARTED.value),
                )
        except Exception as e:
            logger.warning(
                f"[STATUS_MANAGER] Could not ensure status row for {self.table_name}: {e}. "
                f"Will attempt status updates anyway."
            )

    def mark_running(self, symbol_count: int | None = None) -> None:
        """Mark loader as starting execution now.

        Sets: status=RUNNING, execution_started=NOW, completion_pct=0, symbols_loaded=0, symbols_failed=0

        FIXED 2026-08-10: symbols_failed was the one counter this method left untouched while
        resetting symbols_loaded/completion_pct (same bug class already fixed here for those
        two - see the comment below). A fresh run's row showed 0% complete next to a nonzero
        symbols_failed carried over from the PRIOR run's final count, misread as "already
        failing hard" on a run that hadn't processed anything yet. Live-reproduced 2026-08-10:
        growth_metrics/quality_metrics showed a frozen 289/205 symbols_failed across multiple
        checks minutes apart while genuinely still running - stale, not live. That column is
        also surfaced directly to the dashboard health panel (lambda/api/routes/algo_handlers/
        market.py), so the stale value was actively misleading operator monitoring.

        ISSUE #9 FIX: Uses SELECT FOR UPDATE for row-level locking within a single transaction.
        This prevents concurrent updates from overwriting counts.

        Args:
            symbol_count: Optional total number of symbols being loaded (for completion_pct calculation)
        """
        try:
            with DatabaseContext("write") as cur:
                # SELECT FOR UPDATE locks the row within this transaction
                cur.execute(
                    "SELECT status FROM data_loader_status WHERE table_name = %s FOR UPDATE",
                    (self.table_name,),
                )
                result = cur.fetchone()
                if result:
                    current_status = result[0]
                    if current_status not in (
                        LoaderStatus.NOT_STARTED.value,
                        LoaderStatus.COMPLETED.value,
                        LoaderStatus.FAILED.value,
                        LoaderStatus.TIMEOUT.value,
                    ):
                        logger.warning(
                            f"[STATUS_MANAGER] Unexpected status transition for {self.table_name}: "
                            f"{current_status} -> RUNNING"
                        )

                # FIXED 2026-08-10: neither branch used to touch last_updated at all, leaving it
                # frozen at whatever the previous run (or pipeline_health.py's own business-date
                # health-sweep) last wrote - stale from the very first second of a fresh run, for
                # any loader whose run() doesn't call start_heartbeat() (see
                # algo/monitoring/pipeline_health.py's _check_stuck_loaders docstring for the full
                # chain this fed into: false "stuck/crashed" alerts on healthy, actively-running
                # loaders). Stamping it here gives every run an accurate baseline the moment it
                # starts, regardless of whether anything updates it again mid-run.
                #
                # FIXED 2026-08-10 (live evidence): completion_pct/symbols_loaded were left
                # untouched by the no-symbol_count branch, and only symbols_loaded (not
                # completion_pct) was reset in the symbol_count branch. A loader that calls
                # mark_running() and then crashes/hangs before its first update_progress() -
                # e.g. technical_data_daily, live-reproduced: execution_started stamped fresh,
                # status stuck at RUNNING, but completion_pct/symbols_loaded still read
                # "100.00%, 10549/10549" carried over from the PRIOR successful run - leaves a
                # self-contradictory row that reads as "100% done" to any caller keying off
                # completion_pct (orchestrator.py's proactive-wait) while status says RUNNING,
                # producing a false "stalled at 100%" alarm instead of an honest "0% - just
                # started, no data yet" signal. A fresh run has zero real progress the instant
                # it starts; reset both fields here unconditionally so a crash before the first
                # update_progress() call reads as 0%, not a stale echo of the last success.
                if symbol_count is not None:
                    cur.execute(
                        """
                        UPDATE data_loader_status
                        SET status = %s, execution_started = NOW(), execution_completed = NULL, error_message = NULL, symbol_count = %s, symbols_loaded = 0, symbols_failed = 0, completion_pct = 0, last_updated = NOW()
                        WHERE table_name = %s
                        """,
                        (LoaderStatus.RUNNING.value, symbol_count, self.table_name),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE data_loader_status
                        SET status = %s, execution_started = NOW(), execution_completed = NULL, error_message = NULL, symbols_loaded = 0, symbols_failed = 0, completion_pct = 0, last_updated = NOW()
                        WHERE table_name = %s
                        """,
                        (LoaderStatus.RUNNING.value, self.table_name),
                    )
                if cur.rowcount != 1:
                    raise RuntimeError(
                        f"[STATUS_MANAGER] CRITICAL: Failed to update {self.table_name} status. "
                        f"rowcount={cur.rowcount}, expected 1. Status row may be missing from data_loader_status."
                    )
            logger.info(f"[STATUS] {self.table_name}: RUNNING")
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to mark {self.table_name} as RUNNING: {e}")
            raise

    def update_progress(
        self,
        symbols_loaded: int | None = None,
        symbol_count: int | None = None,
        completion_pct: float | None = None,
    ) -> None:
        """Update loader progress without changing status.

        ISSUE #9 FIX: Uses SELECT FOR UPDATE to prevent concurrent updates from overwriting counts.
        Validates monotonic increase: symbols_loaded cannot decrease.

        Args:
            symbols_loaded: Number of symbols processed so far
            symbol_count: Total number of symbols to process
            completion_pct: Percentage complete (0-100)
        """
        try:
            with DatabaseContext("write") as cur:
                # SELECT FOR UPDATE locks the row within this transaction
                cur.execute(
                    "SELECT symbols_loaded FROM data_loader_status WHERE table_name = %s FOR UPDATE",
                    (self.table_name,),
                )
                result = cur.fetchone()

                # Validate monotonic increase before updating
                if symbols_loaded is not None and result and result[0] is not None:
                    old_symbols_loaded = result[0]
                    if symbols_loaded < old_symbols_loaded:
                        raise ValueError(
                            f"[STATUS_MANAGER] symbols_loaded cannot decrease: {old_symbols_loaded} -> {symbols_loaded}. "
                            f"This indicates a bug in the progress tracking logic (counts should only increase)."
                        )

                updates = {"last_updated": "NOW()"}
                params: list[Any] = []

                if symbols_loaded is not None:
                    updates["symbols_loaded"] = "%s"
                    params.append(symbols_loaded)

                if symbol_count is not None:
                    updates["symbol_count"] = "%s"
                    params.append(symbol_count)

                if completion_pct is not None:
                    if not (0 <= completion_pct <= 100):
                        logger.error(f"[STATUS_MANAGER] completion_pct must be 0-100, got {completion_pct}")
                        return
                    updates["completion_pct"] = "%s"
                    params.append(completion_pct)

                params.append(self.table_name)

                update_clause = ", ".join([f"{k} = {v}" for k, v in updates.items()])
                cur.execute(
                    f"UPDATE data_loader_status SET {update_clause} WHERE table_name = %s",
                    params,
                )

                pct_str = f"{completion_pct:.1f}%" if completion_pct is not None else "?"
                logger.debug(f"[STATUS] {self.table_name}: Progress {pct_str} ({symbols_loaded}/{symbol_count})")
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to update progress for {self.table_name}: {e}")

    def mark_completed(
        self,
        execution_duration_sec: float | None = None,
        http_status: int | None = None,
        rate_limit_quota: str | None = None,
        latest_date: Any | None = None,
        symbols_failed: int | None = None,
        current_run_symbols_loaded: int | None = None,
        current_run_symbol_count: int | None = None,
        min_completion_pct: float | None = None,
    ) -> None:
        """Mark loader as completed successfully.

        Sets: status=COMPLETED, execution_completed=NOW, completion_pct=100, error_message=NULL,
        last_success_at=NOW, consecutive_failures=0 (see migration 1163 - execution_completed
        alone can't distinguish "last finished successfully" from "last finished at all",
        since it's also stamped on FAILED/TIMEOUT).

        ISSUE #9 FIX: Uses SELECT FOR UPDATE for row-level locking within transaction.
        ERROR COUNT TRACKING: Now logs symbols_failed count for visibility into partial failures.

        PRODUCTION SAFETY FIX (2026-08-03): Don't mark as COMPLETED if completion_pct < 98%
        (previous runs marked 95.75% completion as COMPLETE, masking data integrity issues).
        Always use runner.py fail_rate check before calling mark_completed.

        Args:
            execution_duration_sec: Optional execution duration for performance tracking
            http_status: Optional HTTP status code from API call (200=ok)
            rate_limit_quota: Optional rate limit quota string for display
            latest_date: Optional latest date in the loaded data (for data freshness tracking)
            symbols_failed: Optional count of symbols that failed to load (allows partial success visibility)
            current_run_symbols_loaded: The CURRENT run's own verified symbols-loaded count. When
                provided (with current_run_symbol_count), the safety check below validates
                against these instead of re-reading symbol_count/symbols_loaded from the DB row.
            current_run_symbol_count: The CURRENT run's own expected total symbol count. See
                current_run_symbols_loaded.

                CRITICAL FIX (2026-08-03): callers that never call mark_running()/update_progress()
                during a run (e.g. load_prices.py - confirmed via repo-wide grep: zero call sites)
                leave symbol_count/symbols_loaded in data_loader_status holding whatever a PAST
                run last wrote - there is no reset-at-start, no progress-tracking-during-run for
                those callers. The safety check below used to unconditionally re-read those two
                columns and treat them as "this run's" numbers. Live-reproduced repeatedly on
                etf_price_daily (2026-08-03): a run that itself verified 5/5 symbols loaded (100%,
                confirmed via a direct DB re-query moments later) still got rejected here with
                "only 80.00% completion (4/5 symbols)" - a stale value from a genuinely-failed run
                from earlier, which then perpetuated forever since nothing here ever corrected it on
                a subsequent success. Passing the current run's own counts explicitly closes that
                gap for callers that supply them; callers that don't (unchanged) keep the exact
                prior DB-read-back behavior.
            min_completion_pct: Optional custom completion threshold. Use when a loader depends on
                upstream data and expects inherent incompleteness (e.g., buy_sell_daily depends on
                technical_data_daily which may not cover all symbols). If None, defaults to 98%.
        """
        try:
            with DatabaseContext("write") as cur:
                # CRITICAL SAFETY CHECK: Verify completion_pct before marking COMPLETED
                # SELECT FOR UPDATE locks the row within this transaction
                # This prevents marking as COMPLETE when data load was actually incomplete
                cur.execute(
                    "SELECT symbol_count, symbols_loaded, completion_pct FROM data_loader_status WHERE table_name = %s FOR UPDATE",
                    (self.table_name,),
                )
                status_row = cur.fetchone()
                if current_run_symbols_loaded is not None and current_run_symbol_count is not None:
                    total_symbols = current_run_symbol_count
                    loaded_symbols = current_run_symbols_loaded
                    current_completion_pct = None
                    status_row = (total_symbols, loaded_symbols, current_completion_pct)
                if status_row:
                    total_symbols = status_row[0]
                    loaded_symbols = status_row[1]
                    current_completion_pct = status_row[2]

                    # Calculate actual completion percentage from loader stats.
                    # BUG FOUND 2026-08-10: uncapped, this can exceed 100% when a caller's
                    # loaded_symbols count (e.g. a universe-wide "symbols successfully
                    # processed" counter) and total_symbols count (e.g. a same-date-scoped
                    # upstream-availability count) are drawn from different, not-strictly-
                    # nested populations - live-confirmed on buy_sell_daily: symbols_loaded=4884
                    # vs symbol_count=4768 produced completion_pct=102.43%, a nonsensical value
                    # that undermines confidence in this metric wherever it's displayed
                    # (dashboards, the orchestrator's proactive critical-loader-wait check).
                    # A completion percentage is bounded at 100% by definition; clamp it rather
                    # than let mismatched numerator/denominator sources produce garbage.
                    if total_symbols and total_symbols > 0:
                        actual_completion_pct = min(100.0, (loaded_symbols / total_symbols) * 100.0)
                    else:
                        actual_completion_pct = 0.0

                    # Use provided threshold or default to 98%
                    completion_threshold = min_completion_pct if min_completion_pct is not None else 98.0

                    # SAFETY: Never mark COMPLETE if completion is suspiciously low
                    # Default: Production loaders require 98% minimum completion (2% failure tolerance max)
                    # Exception: Loaders with upstream dependencies may specify custom threshold
                    # This catches cases where load_pct=95% but was marked COMPLETE due to bug
                    if actual_completion_pct < completion_threshold:
                        logger.critical(
                            f"[SAFETY CHECK] {self.table_name}: Cannot mark COMPLETED with only "
                            f"{actual_completion_pct:.2f}% completion ({loaded_symbols}/{total_symbols} symbols). "
                            f"Threshold: {completion_threshold:.2f}%. This indicates incomplete data load. Marking FAILED instead."
                        )
                        # Update status to FAILED within this same transaction (lock already held)
                        cur.execute(
                            """
                            UPDATE data_loader_status
                            SET status = %s, execution_completed = NOW(), completion_pct = %s,
                                error_message = %s, last_updated = NOW(),
                                consecutive_failures = consecutive_failures + 1
                            WHERE table_name = %s
                            """,
                            (
                                LoaderStatus.FAILED.value,
                                actual_completion_pct,
                                f"Incomplete load: only {loaded_symbols}/{total_symbols} symbols loaded ({actual_completion_pct:.2f}%)",
                                self.table_name,
                            ),
                        )
                        # Archive to history for pattern analysis
                        archived = self._archive_to_history(cur, LoaderStatus.FAILED.value)
                        if not archived:
                            logger.warning(
                                f"[STATUS_MANAGER] WARNING: {self.table_name} marked FAILED (incomplete) "
                                f"but history archiving failed. Dashboard failure-pattern analysis may be incomplete."
                            )
                        return  # Exit early - transaction commits with FAILED status

                # Calculate throughput if we have duration and symbols
                symbols_per_sec = None
                if execution_duration_sec and execution_duration_sec > 0:
                    if status_row:
                        symbols_per_sec = status_row[1] / execution_duration_sec

                # Use actual completion percentage for COMPLETED status
                # SESSION 108 FIX: Simplified confusing ternary - if we reach here, we already passed
                # the completion check at line 361, so actual_completion_pct >= threshold is always true.
                # The "else 100.0" was dead code and confusing. Just use the actual value.
                final_completion_pct = actual_completion_pct

                # CRITICAL FIX (2026-08-03): symbol_count/symbols_loaded were never written by
                # either branch below - callers that never call update_progress() during a run
                # (e.g. load_prices.py) left these two columns holding whatever a past run last
                # wrote, forever, even after this function marks the row COMPLETED at 100%. Any
                # later reader of this row (a dashboard, or this same safety check on a FUTURE
                # run that doesn't pass current_run_* overrides) would keep seeing stale counts
                # indefinitely. Refresh them here from whatever this call resolved
                # total_symbols/loaded_symbols to (either the current_run_* override or the
                # pre-existing DB-read fallback above).
                # Build dynamic SQL to optionally include latest_date
                if latest_date is not None:
                    cur.execute(
                        """
                        UPDATE data_loader_status
                        SET status = %s, execution_completed = NOW(), completion_pct = %s,
                            error_message = NULL, last_updated = NOW(),
                            last_success_at = NOW(), consecutive_failures = 0,
                            execution_duration_sec = %s, http_status_code = %s,
                            rate_limit_quota = %s, symbols_per_second = %s, latest_date = %s,
                            symbol_count = %s, symbols_loaded = %s, symbols_failed = %s
                        WHERE table_name = %s
                        """,
                        (
                            LoaderStatus.COMPLETED.value,
                            final_completion_pct,
                            execution_duration_sec,
                            http_status,
                            rate_limit_quota,
                            symbols_per_sec,
                            latest_date,
                            total_symbols,
                            loaded_symbols,
                            symbols_failed,
                            self.table_name,
                        ),
                    )
                    if cur.rowcount != 1:
                        raise RuntimeError(
                            f"[STATUS_MANAGER] CRITICAL: Failed to update {self.table_name} status. "
                            f"rowcount={cur.rowcount}, expected 1. Status row may be missing from data_loader_status."
                        )
                else:
                    cur.execute(
                        """
                        UPDATE data_loader_status
                        SET status = %s, execution_completed = NOW(), completion_pct = %s,
                            error_message = NULL, last_updated = NOW(),
                            last_success_at = NOW(), consecutive_failures = 0,
                            execution_duration_sec = %s, http_status_code = %s,
                            rate_limit_quota = %s, symbols_per_second = %s,
                            symbol_count = %s, symbols_loaded = %s, symbols_failed = %s
                        WHERE table_name = %s
                        """,
                        (
                            LoaderStatus.COMPLETED.value,
                            final_completion_pct,
                            execution_duration_sec,
                            http_status,
                            rate_limit_quota,
                            symbols_per_sec,
                            total_symbols,
                            loaded_symbols,
                            symbols_failed,
                            self.table_name,
                        ),
                    )
                if cur.rowcount != 1:
                    raise RuntimeError(
                        f"[STATUS_MANAGER] CRITICAL: Failed to update {self.table_name} status. "
                        f"rowcount={cur.rowcount}, expected 1. Status row may be missing from data_loader_status."
                    )
                # Archive to history table for failure pattern analysis
                archived = self._archive_to_history(cur, LoaderStatus.COMPLETED.value)
                if not archived:
                    logger.warning(
                        f"[STATUS_MANAGER] WARNING: {self.table_name} marked COMPLETED but history archiving failed. "
                        f"Dashboard failure-pattern analysis may be incomplete."
                    )

            # Log completion with error visibility (symbols_failed indicates partial success)
            duration_str = f"({execution_duration_sec:.1f}s)" if execution_duration_sec else ""
            if symbols_failed is not None and symbols_failed > 0:
                logger.warning(
                    f"[STATUS] {self.table_name}: COMPLETED with {symbols_failed} symbol failures {duration_str}"
                )
            else:
                logger.info(f"[STATUS] {self.table_name}: COMPLETED {duration_str}")
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to mark {self.table_name} as COMPLETED: {e}")
            raise

    def mark_failed(
        self,
        error_message: str,
        completion_pct: float | None = None,
        http_status: int | None = None,
        retry_count: int | None = None,
    ) -> None:
        """Mark loader as failed with error reason.

        ISSUE #9 FIX: Uses SELECT FOR UPDATE for row-level locking within transaction.

        Args:
            error_message: Description of what went wrong (max 1000 chars)
            completion_pct: Optional percentage completed before failure
            http_status: Optional HTTP status code from API call (429=rate limit, 401=auth, 503=service down)
            retry_count: Optional number of retries performed before failure
        """
        # Truncate message to 1000 chars to prevent DB column overflow
        msg = error_message[:1000]

        try:
            with DatabaseContext("write") as cur:
                # SELECT FOR UPDATE locks the row within this transaction
                cur.execute(
                    "SELECT table_name FROM data_loader_status WHERE table_name = %s FOR UPDATE",
                    (self.table_name,),
                )
                if completion_pct is not None:
                    cur.execute(
                        """
                        UPDATE data_loader_status
                        SET status = %s, execution_completed = NOW(), completion_pct = %s,
                            error_message = %s, last_updated = NOW(),
                            consecutive_failures = consecutive_failures + 1,
                            http_status_code = %s, retry_count = %s
                        WHERE table_name = %s
                        """,
                        (LoaderStatus.FAILED.value, completion_pct, msg, http_status, retry_count, self.table_name),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE data_loader_status
                        SET status = %s, execution_completed = NOW(), error_message = %s,
                            last_updated = NOW(), consecutive_failures = consecutive_failures + 1,
                            http_status_code = %s, retry_count = %s
                        WHERE table_name = %s
                        """,
                        (LoaderStatus.FAILED.value, msg, http_status, retry_count, self.table_name),
                    )
                if cur.rowcount != 1:
                    raise RuntimeError(
                        f"[STATUS_MANAGER] CRITICAL: Failed to update {self.table_name} status. "
                        f"rowcount={cur.rowcount}, expected 1. Status row may be missing from data_loader_status."
                    )
                # Archive to history table for failure pattern analysis
                archived = self._archive_to_history(cur, LoaderStatus.FAILED.value, http_status)
                if not archived:
                    logger.warning(
                        f"[STATUS_MANAGER] WARNING: {self.table_name} marked FAILED but history archiving failed. "
                        f"Dashboard failure-pattern analysis may be incomplete."
                    )

            logger.error(f"[STATUS] {self.table_name}: FAILED - {msg[:100]}")
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to mark {self.table_name} as FAILED: {e}")
            raise

    def mark_timeout(self, runtime_seconds: float, http_status: int | None = None) -> None:
        """Mark loader as timed out.

        ISSUE #9 FIX: Uses SELECT FOR UPDATE for row-level locking within transaction.

        Args:
            runtime_seconds: How long the loader ran before timing out
            http_status: Optional HTTP status code if the timeout was from an API call
        """
        msg = f"Timeout after {runtime_seconds:.0f} seconds"
        try:
            with DatabaseContext("write") as cur:
                # SELECT FOR UPDATE locks the row within this transaction
                cur.execute(
                    "SELECT table_name FROM data_loader_status WHERE table_name = %s FOR UPDATE",
                    (self.table_name,),
                )
                cur.execute(
                    """
                    UPDATE data_loader_status
                    SET status = %s, execution_completed = NOW(), error_message = %s, last_updated = NOW(),
                        consecutive_failures = consecutive_failures + 1,
                        execution_duration_sec = %s, http_status_code = %s
                    WHERE table_name = %s
                    """,
                    (LoaderStatus.TIMEOUT.value, msg, runtime_seconds, http_status, self.table_name),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(
                        f"[STATUS_MANAGER] CRITICAL: Failed to update {self.table_name} status. "
                        f"rowcount={cur.rowcount}, expected 1. Status row may be missing from data_loader_status."
                    )
                # Archive to history table for failure pattern analysis
                archived = self._archive_to_history(cur, LoaderStatus.TIMEOUT.value, http_status)
                if not archived:
                    logger.warning(
                        f"[STATUS_MANAGER] WARNING: {self.table_name} marked TIMEOUT but history archiving failed. "
                        f"Dashboard failure-pattern analysis may be incomplete."
                    )

            logger.error(f"[STATUS] {self.table_name}: TIMEOUT - {msg}")
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to mark {self.table_name} as TIMEOUT: {e}")
            raise

    def _archive_to_history(self, cur: Any, status: str, http_status: int | None = None) -> bool:
        """Archive current status to history table for pattern analysis.

        CRITICAL: Uses SAVEPOINT to ensure archive failures don't roll back the main status update.
        If archiving fails (e.g., history table full, permissions), we've already updated the main
        status table, so rolling back would leave the system in an inconsistent state.

        Args:
            cur: Database cursor
            status: Final status (COMPLETED, FAILED, TIMEOUT)
            http_status: Optional HTTP status code

        Returns:
            True if archiving succeeded, False if it failed (but main status update is still committed)
        """
        try:
            # Use a savepoint: if archive fails, the main UPDATE stays committed
            # Sanitize table name for use in savepoint (max 63 chars, no special chars)
            sanitized_name = self.table_name.replace("-", "_")[:50]
            savepoint_name = f"archive_{sanitized_name}_history"
            cur.execute(f"SAVEPOINT {savepoint_name}")

            # Fetch current status values
            cur.execute(
                """
                SELECT execution_started, execution_completed, error_message, row_count,
                       completion_pct, symbols_loaded, symbol_count
                FROM data_loader_status
                WHERE table_name = %s
                """,
                (self.table_name,),
            )
            result = cur.fetchone()
            if result:
                exec_started, exec_completed, error_msg, row_count, completion_pct, symbols_loaded, symbol_count = (
                    result
                )
                cur.execute(
                    """
                    INSERT INTO data_loader_status_history
                    (table_name, status, execution_started, execution_completed, error_message,
                     http_status_code, row_count, completion_pct, symbols_loaded, symbol_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        self.table_name,
                        status,
                        exec_started,
                        exec_completed,
                        error_msg,
                        http_status,
                        row_count,
                        completion_pct,
                        symbols_loaded,
                        symbol_count,
                    ),
                )
                # Clean up old history (keep only last 100 runs per table)
                cur.execute(
                    """
                    DELETE FROM data_loader_status_history
                    WHERE table_name = %s
                    AND id NOT IN (
                        SELECT id FROM data_loader_status_history
                        WHERE table_name = %s
                        ORDER BY execution_completed DESC NULLS LAST
                        LIMIT 100
                    )
                    """,
                    (self.table_name, self.table_name),
                )
                # Archive succeeded, release the savepoint
                cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                logger.info(f"[STATUS_MANAGER] Archived {self.table_name} history record: {status}")
                return True
            else:
                # No status row to archive - this shouldn't happen
                cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                logger.warning(f"[STATUS_MANAGER] No status row found to archive for {self.table_name}")
                return False
        except Exception as e:
            logger.warning(f"[STATUS_MANAGER] ARCHIVING FAILED for {self.table_name}: {e}")
            try:
                cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            except Exception as rollback_err:
                logger.warning(f"[STATUS_MANAGER] Failed to rollback savepoint for {self.table_name}: {rollback_err}")
            return False

    def update_final_status(
        self,
        status_string: str,
        completion_pct: float | None = None,
        symbols_loaded: int | None = None,
        symbol_count: int | None = None,
        error_message: str | None = None,
        row_count: int | None = None,
        execution_duration_sec: float | None = None,
        http_status: int | None = None,
        latest_date: Any | None = None,
    ) -> None:
        """Comprehensive final status update with all statistics.

        This is used by loaders' _update_final_status() / _update_loader_status() methods
        to record the full outcome: status, completion %, symbols loaded, etc.

        Args:
            status_string: Final status value (typically "ok", "failed", "error", "loading")
            completion_pct: Percentage of symbols successfully loaded (0-100)
            symbols_loaded: Number of symbols successfully loaded
            symbol_count: Total number of symbols to load
            error_message: Error description if failed
            row_count: Total rows inserted
            execution_duration_sec: How long loader ran
            http_status: HTTP status code if applicable
            latest_date: Latest date in loaded data (for freshness tracking)
        """
        try:
            with DatabaseContext("write") as cur:
                # Build dynamic SQL to only update non-None fields
                updates: dict[str, str] = {"last_updated": "NOW()"}
                params: list[Any] = []

                if status_string is not None:
                    updates["status"] = "%s"
                    params.append(status_string)

                if completion_pct is not None:
                    updates["completion_pct"] = "%s"
                    params.append(completion_pct)

                if symbols_loaded is not None:
                    updates["symbols_loaded"] = "%s"
                    params.append(symbols_loaded)

                if symbol_count is not None:
                    updates["symbol_count"] = "%s"
                    params.append(symbol_count)

                if error_message is not None:
                    updates["error_message"] = "%s"
                    params.append(error_message)

                if row_count is not None:
                    updates["row_count"] = "%s"
                    params.append(row_count)

                if execution_duration_sec is not None:
                    updates["execution_duration_sec"] = "%s"
                    params.append(execution_duration_sec)

                if http_status is not None:
                    updates["http_status_code"] = "%s"
                    params.append(http_status)

                if latest_date is not None:
                    updates["latest_date"] = "%s"
                    params.append(latest_date)

                if status_string in ("ok", "COMPLETED"):
                    updates["execution_completed"] = "NOW()"
                    updates["last_success_at"] = "NOW()"
                    updates["consecutive_failures"] = "0"
                elif status_string in ("failed", "error", "FAILED"):
                    updates["execution_completed"] = "NOW()"
                    updates["consecutive_failures"] = "consecutive_failures + 1"

                params.append(self.table_name)

                update_clause = ", ".join([f"{k} = {v}" for k, v in updates.items()])
                cur.execute(
                    f"UPDATE data_loader_status SET {update_clause} WHERE table_name = %s",
                    params,
                )

                if cur.rowcount != 1:
                    logger.warning(
                        f"[STATUS_MANAGER] update_final_status: rowcount={cur.rowcount}, expected 1 for {self.table_name}"
                    )

                # Archive to history for pattern analysis
                archived = self._archive_to_history(cur, status_string, http_status)
                if not archived:
                    logger.warning(
                        f"[STATUS_MANAGER] WARNING: {self.table_name} status updated to {status_string} "
                        f"but history archiving failed. Dashboard failure-pattern analysis may be incomplete."
                    )

            logger.info(
                f"[STATUS] {self.table_name}: Final update - status={status_string}, completion_pct={completion_pct}"
            )
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed final status update for {self.table_name}: {e}")
            raise

    def get_status(self) -> dict[str, Any] | None:
        """Fetch current status from database.

        Returns:
            Dict with status, completion_pct, error_message, etc. or None if not found.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT status, completion_pct, symbols_loaded, symbol_count, error_message,
                           execution_started, execution_completed, last_updated
                    FROM data_loader_status
                    WHERE table_name = %s
                    """,
                    (self.table_name,),
                )
                row = cur.fetchone()
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to fetch status for {self.table_name}: {e}")
            return None


def reap_stale_running_loaders(table_names: list[str] | None = None, max_age_hours: float | None = None) -> list[str]:
    """Mark any of the given tables' RUNNING status as FAILED if execution_started is older
    than max_age_hours.

    No local-dev process supervises data_loader_status independently of the loader process
    itself - a crashed process, a killed subprocess whose parent's subprocess.run(timeout=...)
    failed to reap it, or a scheduler still running old in-memory code from before a same-day
    timeout fix all leave the row stuck at RUNNING forever (see
    buy_sell_daily_stuck_running_74_hours_20260810: a prior incident required a one-off manual
    fix and explicitly recommended, but never implemented, an automatic version of this check).
    Production has an ECS-task-based equivalent (orchestrator._kill_long_running_loaders), but
    it makes real AWS ListTasks calls that always fail locally (no AWS credentials in
    LOCAL_MODE), so local runs had no equivalent safety net at all.

    Deliberately DB-only (no OS process management): the actual run-to-run exclusion is
    already enforced by utils/db/local_file_lock.py's own TTL, so a still-genuinely-running
    process that gets marked FAILED here only produces a transient, self-correcting status
    inaccuracy (overwritten the moment that process finishes and calls its own
    mark_completed()/mark_failed()) - not a second concurrent run of real work.

    Args:
        table_names: Tables to check, or None to check every table currently in
            data_loader_status (a stuck loader anywhere is worth correcting - this isn't
            scoped to a single pipeline run).
        max_age_hours: Ignored if table_names provided. Reaper now uses per-loader timeout.
            CRITICAL SESSION 106 FIX: Changed from longest_timeout * 1.5 (36h for prices)
            to per-loader timeout + 25% safety margin. This prevents short-timeout loaders
            (30m) from waiting 36h before reaper runs.

    Returns:
        Table names that were reaped (previously RUNNING, now marked FAILED).
    """
    from loaders.loader_timeout_config import get_loader_timeout

    reaped: list[str] = []
    try:
        with DatabaseContext("read") as cur:
            # Query all stuck loaders
            cur.execute(
                """
                SELECT table_name, execution_started
                FROM data_loader_status
                WHERE status = %s
                  AND execution_started IS NOT NULL
                """,
                (LoaderStatus.RUNNING.value,),
            )
            all_stuck = cur.fetchall()
    except Exception as e:
        error_msg = (
            f"[STATUS_MANAGER] Stale-loader reap check FAILED (not '0 stale loaders found' - "
            f"the query itself errored, so any genuinely stuck loader is NOT being detected "
            f"this cycle): {e}"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e

    from datetime import datetime, timezone

    for table_name, execution_started in all_stuck:
        try:
            # CRITICAL SESSION 106 FIX: Use per-loader timeout, not longest_timeout * 1.5
            loader_timeout_sec = get_loader_timeout(table_name, default_seconds=3600)
            max_age_sec = loader_timeout_sec * 1.25
            now_utc = datetime.now(timezone.utc)
            if execution_started.tzinfo is None:
                execution_started = execution_started.replace(tzinfo=timezone.utc)
            age_sec = (now_utc - execution_started).total_seconds()

            if age_sec > max_age_sec:
                max_age_hours_for_log = max_age_sec / 3600
                LoaderStatusManager(table_name).mark_failed(
                    error_message=(
                        f"[REAPED] Stuck in RUNNING since {execution_started} (>{max_age_hours_for_log:.1f}h ago, "
                        f"exceeds {loader_timeout_sec}s timeout + 25% margin). "
                        "No owning process alive - auto-marked FAILED."
                    )
                )
                logger.warning(
                    f"[STATUS_MANAGER] Reaped stale RUNNING loader: {table_name} "
                    f"(started {execution_started}, {age_sec:.0f}s > {max_age_sec:.0f}s threshold)"
                )
                reaped.append(table_name)
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to reap stale RUNNING loader {table_name}: {e}")

    return reaped
