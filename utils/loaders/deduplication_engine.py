#!/usr/bin/env python3
"""Deduplication Engine - Detect and handle duplicate rows."""

import logging
from collections.abc import Sequence
from typing import Any


logger = logging.getLogger(__name__)


class DeduplicationEngine:
    """Detects and deduplicates rows based on primary keys."""

    def __init__(self, primary_key: Sequence[str]) -> None:
        """Initialize with primary key columns.

        Args:
            primary_key: Column names forming unique constraint
        """
        self.primary_key = tuple(primary_key)
        self.seen_keys: set[tuple[Any, ...]] = set()

    def get_key(self, row: dict[str, Any]) -> tuple[Any, ...]:
        """Extract primary key from row."""
        return tuple(row.get(col) for col in self.primary_key)

    def is_duplicate(self, row: dict[str, Any]) -> bool:
        """Check if row is a duplicate.

        Args:
            row: Row to check

        Returns:
            True if this key was previously seen
        """
        key = self.get_key(row)
        return key in self.seen_keys

    def mark_seen(self, row: dict[str, Any]) -> None:
        """Mark row as seen.

        Args:
            row: Row to track
        """
        key = self.get_key(row)
        self.seen_keys.add(key)

    def deduplicate_batch(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicates from batch, keeping first occurrence.

        Args:
            rows: Batch of rows

        Returns:
            Deduplicated batch
        """
        deduplicated = []
        duplicates_removed = 0
        for row in rows:
            if self.is_duplicate(row):
                duplicates_removed += 1
            else:
                deduplicated.append(row)
                self.mark_seen(row)

        if duplicates_removed > 0:
            logger.info(f"[DEDUP] Removed {duplicates_removed} duplicates from {len(rows)} rows")
        return deduplicated

    def get_seen_count(self) -> int:
        """Get number of unique keys seen."""
        return len(self.seen_keys)

    def reset(self) -> None:
        """Reset deduplication tracking."""
        self.seen_keys.clear()
