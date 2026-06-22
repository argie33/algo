#!/usr/bin/env python3
"""Watermark Manager - Manage incremental load watermarks."""

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class WatermarkManager:
    """Manages watermark tracking for incremental loads."""

    def __init__(self, table_name: str, watermark_field: str = "date") -> None:
        """Initialize watermark manager."""
        self.table_name = table_name
        self.watermark_field = watermark_field
        self.current_watermark: Any | None = None

    def read_watermark(self, cur: Any) -> Any | None:
        """Read current watermark from database."""
        try:
            cur.execute(f"SELECT MAX({self.watermark_field}) FROM {self.table_name}")
            row = cur.fetchone()
            if row and row[0]:
                self.current_watermark = row[0]
                logger.debug(f"[WATERMARK] {self.table_name}: {self.current_watermark}")
                return self.current_watermark
            return None
        except Exception as e:
            logger.error(f"[WATERMARK] Failed to read for {self.table_name}: {e}")
            return None

    def update_watermark(self, cur: Any, new_value: Any) -> None:
        """Update watermark after successful load."""
        self.current_watermark = new_value
        logger.info(f"[WATERMARK] {self.table_name}: updated to {new_value}")

    def should_backfill(self, row_count: int, backfill_threshold: int = 5) -> bool:
        """Determine if table needs backfilling based on row count."""
        if row_count < backfill_threshold:
            logger.info(f"[WATERMARK] {self.table_name}: {row_count} rows < {backfill_threshold}, backfilling")
            return True
        return False

    def get_since_date(self, cur: Any, backfill_days: int = 365) -> datetime:
        """Get the 'since' date for incremental load."""
        watermark = self.read_watermark(cur)
        if watermark:
            # Ensure watermark is a datetime before arithmetic
            if isinstance(watermark, datetime):
                return watermark - timedelta(days=100)
            return datetime.now() - timedelta(days=backfill_days)
        return datetime.now() - timedelta(days=backfill_days)

    def get_current_watermark(self) -> Any | None:
        """Get current cached watermark."""
        return self.current_watermark
