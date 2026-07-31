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
    """Manage loader status updates with validation and consistency checks."""

    def __init__(self, table_name: str) -> None:
        """Initialize status manager for a specific loader table.

        Args:
            table_name: Name of the table this loader updates (e.g., 'price_daily')
        """
        self.table_name = table_name
        self._ensure_status_row_exists()

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

    def mark_running(self) -> None:
        """Mark loader as starting execution now.

        Sets: status=RUNNING, execution_started=NOW
        """
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    UPDATE data_loader_status
                    SET status = %s, execution_started = NOW(), execution_completed = NULL, error_message = NULL
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

        Args:
            symbols_loaded: Number of symbols processed so far
            symbol_count: Total number of symbols to process
            completion_pct: Percentage complete (0-100)
        """
        try:
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
            with DatabaseContext("write") as cur:
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
    ) -> None:
        """Mark loader as completed successfully.

        Sets: status=COMPLETED, execution_completed=NOW, completion_pct=100, error_message=NULL,
        last_success_at=NOW, consecutive_failures=0 (see migration 1163 - execution_completed
        alone can't distinguish "last finished successfully" from "last finished at all",
        since it's also stamped on FAILED/TIMEOUT).

        Args:
            execution_duration_sec: Optional execution duration for performance tracking
            http_status: Optional HTTP status code from API call (200=ok)
            rate_limit_quota: Optional rate limit quota string for display
            latest_date: Optional latest date in the loaded data (for data freshness tracking)
        """
        try:
            with DatabaseContext("write") as cur:
                # Calculate throughput if we have duration and symbols
                symbols_per_sec = None
                if execution_duration_sec and execution_duration_sec > 0:
                    cur.execute("SELECT symbols_loaded FROM data_loader_status WHERE table_name = %s",
                               (self.table_name,))
                    result = cur.fetchone()
                    if result and result[0]:
                        symbols_per_sec = result[0] / execution_duration_sec

                # Build dynamic SQL to optionally include latest_date
                if latest_date is not None:
                    cur.execute(
                        """
                        UPDATE data_loader_status
                        SET status = %s, execution_completed = NOW(), completion_pct = 100.0,
                            error_message = NULL, last_updated = NOW(),
                            last_success_at = NOW(), consecutive_failures = 0,
                            execution_duration_sec = %s, http_status_code = %s,
                            rate_limit_quota = %s, symbols_per_second = %s, latest_date = %s
                        WHERE table_name = %s
                        """,
                        (LoaderStatus.COMPLETED.value, execution_duration_sec, http_status,
                         rate_limit_quota, symbols_per_sec, latest_date, self.table_name),
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
                        SET status = %s, execution_completed = NOW(), completion_pct = 100.0,
                            error_message = NULL, last_updated = NOW(),
                            last_success_at = NOW(), consecutive_failures = 0,
                            execution_duration_sec = %s, http_status_code = %s,
                            rate_limit_quota = %s, symbols_per_second = %s
                        WHERE table_name = %s
                        """,
                        (LoaderStatus.COMPLETED.value, execution_duration_sec, http_status,
                         rate_limit_quota, symbols_per_sec, self.table_name),
                    )
                if cur.rowcount != 1:
                    raise RuntimeError(
                        f"[STATUS_MANAGER] CRITICAL: Failed to update {self.table_name} status. "
                        f"rowcount={cur.rowcount}, expected 1. Status row may be missing from data_loader_status."
                    )
                # Archive to history table for failure pattern analysis
                self._archive_to_history(cur, LoaderStatus.COMPLETED.value)

            logger.info(f"[STATUS] {self.table_name}: COMPLETED ({execution_duration_sec:.1f}s)" if execution_duration_sec else f"[STATUS] {self.table_name}: COMPLETED")
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
                self._archive_to_history(cur, LoaderStatus.FAILED.value, http_status)

            logger.error(f"[STATUS] {self.table_name}: FAILED - {msg[:100]}")
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to mark {self.table_name} as FAILED: {e}")
            raise

    def mark_timeout(self, runtime_seconds: float, http_status: int | None = None) -> None:
        """Mark loader as timed out.

        Args:
            runtime_seconds: How long the loader ran before timing out
            http_status: Optional HTTP status code if the timeout was from an API call
        """
        msg = f"Timeout after {runtime_seconds:.0f} seconds"
        try:
            with DatabaseContext("write") as cur:
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
                self._archive_to_history(cur, LoaderStatus.TIMEOUT.value, http_status)

            logger.error(f"[STATUS] {self.table_name}: TIMEOUT - {msg}")
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to mark {self.table_name} as TIMEOUT: {e}")
            raise

    def _archive_to_history(self, cur: Any, status: str, http_status: int | None = None) -> None:
        """Archive current status to history table for pattern analysis.

        Args:
            cur: Database cursor
            status: Final status (COMPLETED, FAILED, TIMEOUT)
            http_status: Optional HTTP status code
        """
        try:
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
                exec_started, exec_completed, error_msg, row_count, completion_pct, symbols_loaded, symbol_count = result
                cur.execute(
                    """
                    INSERT INTO data_loader_status_history
                    (table_name, status, execution_started, execution_completed, error_message,
                     http_status_code, row_count, completion_pct, symbols_loaded, symbol_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (self.table_name, status, exec_started, exec_completed, error_msg,
                     http_status, row_count, completion_pct, symbols_loaded, symbol_count),
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
        except Exception as e:
            logger.debug(f"[STATUS_MANAGER] Failed to archive history for {self.table_name}: {e}")

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
                self._archive_to_history(cur, status_string, http_status)

            logger.info(f"[STATUS] {self.table_name}: Final update - status={status_string}, completion_pct={completion_pct}")
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
