#!/usr/bin/env python3
"""Heartbeat Monitor - Track loader progress and detect stalls."""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class HeartbeatMonitor:
    """Monitors loader progress via heartbeat updates."""

    def __init__(self, table_name: str, heartbeat_interval_seconds: int = 60) -> None:
        """Initialize heartbeat monitor.

        Args:
            table_name: Table being loaded
            heartbeat_interval_seconds: Interval between heartbeats
        """
        self.table_name = table_name
        self.heartbeat_interval = heartbeat_interval_seconds
        self.last_heartbeat_time = time.time()
        self.batch_count = 0
        self.total_rows = 0
        self.start_time = time.time()

    def heartbeat(self, rows_in_batch: int = 0) -> None:
        """Record a heartbeat (progress update).

        Args:
            rows_in_batch: Number of rows processed in this batch
        """
        self.last_heartbeat_time = time.time()
        self.batch_count += 1
        self.total_rows += rows_in_batch

        elapsed = time.time() - self.start_time
        rate = self.total_rows / elapsed if elapsed > 0 else 0
        logger.info(
            f"[HEARTBEAT] {self.table_name}: batch {self.batch_count}, {self.total_rows} rows, {rate:.0f} rows/sec"
        )

    def is_stalled(self) -> bool:
        """Check if loader is stalled (no heartbeat for timeout period).

        Returns:
            True if stalled
        """
        elapsed_since_heartbeat = time.time() - self.last_heartbeat_time
        stalled = elapsed_since_heartbeat > (self.heartbeat_interval * 3)
        if stalled:
            logger.warning(f"[HEARTBEAT] {self.table_name}: STALLED (no heartbeat for {elapsed_since_heartbeat:.0f}s)")
        return stalled

    def get_status(self) -> dict[str, Any]:
        """Get current loader status.

        Returns:
            Status dictionary
        """
        elapsed = time.time() - self.start_time
        return {
            "table_name": self.table_name,
            "batches_processed": self.batch_count,
            "total_rows": self.total_rows,
            "elapsed_seconds": elapsed,
            "rate_rows_per_sec": self.total_rows / elapsed if elapsed > 0 else 0,
            "time_since_last_heartbeat": time.time() - self.last_heartbeat_time,
        }

    def reset(self) -> None:
        """Reset heartbeat monitor."""
        self.last_heartbeat_time = time.time()
        self.batch_count = 0
        self.total_rows = 0
        self.start_time = time.time()
