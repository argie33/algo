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
            logger.info(f"[STATUS] {self.table_name}: RUNNING")
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to mark {self.table_name} as RUNNING: {e}")

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

    def mark_completed(self) -> None:
        """Mark loader as completed successfully.

        Sets: status=COMPLETED, execution_completed=NOW, completion_pct=100, error_message=NULL
        """
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    UPDATE data_loader_status
                    SET status = %s, execution_completed = NOW(), completion_pct = 100.0,
                        error_message = NULL, last_updated = NOW()
                    WHERE table_name = %s
                    """,
                    (LoaderStatus.COMPLETED.value, self.table_name),
                )
            logger.info(f"[STATUS] {self.table_name}: COMPLETED")
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to mark {self.table_name} as COMPLETED: {e}")

    def mark_failed(self, error_message: str, completion_pct: float | None = None) -> None:
        """Mark loader as failed with error reason.

        Args:
            error_message: Description of what went wrong (max 1000 chars)
            completion_pct: Optional percentage completed before failure
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
                            error_message = %s, last_updated = NOW()
                        WHERE table_name = %s
                        """,
                        (LoaderStatus.FAILED.value, completion_pct, msg, self.table_name),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE data_loader_status
                        SET status = %s, execution_completed = NOW(), error_message = %s,
                            last_updated = NOW()
                        WHERE table_name = %s
                        """,
                        (LoaderStatus.FAILED.value, msg, self.table_name),
                    )
            logger.error(f"[STATUS] {self.table_name}: FAILED - {msg[:100]}")
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to mark {self.table_name} as FAILED: {e}")

    def mark_timeout(self, runtime_seconds: float) -> None:
        """Mark loader as timed out.

        Args:
            runtime_seconds: How long the loader ran before timing out
        """
        msg = f"Timeout after {runtime_seconds:.0f} seconds"
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    UPDATE data_loader_status
                    SET status = %s, execution_completed = NOW(), error_message = %s, last_updated = NOW()
                    WHERE table_name = %s
                    """,
                    (LoaderStatus.TIMEOUT.value, msg, self.table_name),
                )
            logger.error(f"[STATUS] {self.table_name}: TIMEOUT - {msg}")
        except Exception as e:
            logger.error(f"[STATUS_MANAGER] Failed to mark {self.table_name} as TIMEOUT: {e}")

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
