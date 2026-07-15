"""Watermark management for incremental data loading."""

import logging
from datetime import date
from typing import Any

import psycopg2

from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table

logger = logging.getLogger(__name__)


class WatermarkManager:
    """Manages watermark state for per-symbol incremental loading.

    Watermark = highest watermark_field value seen for a symbol.
    Used to determine where to start incremental fetch on next load.
    """

    def __init__(self, table_name: str, watermark_field: str = "date"):
        self.table_name = table_name
        self.watermark_field = watermark_field
        self._marks: dict[str, Any] = {}  # in-memory cache

    def get(self, symbol: str) -> date | None:
        return self._marks.get(symbol)

    def set(self, symbol: str, value: date | None, rows_loaded: int = 0) -> None:
        if value is not None:
            self._marks[symbol] = value

    def read_from_db(self, symbol: str) -> date | None:
        """Read per-symbol watermark from database.

        Returns:
            date if watermark exists (data has been fetched before)
            None if no watermark row exists (never fetched)

        Raises:
            ValueError: If watermark_field is not configured (critical for incrementality)
            DatabaseError if DB query fails (distinguish from "never fetched")
        """
        # CRITICAL: If watermark_field is empty, loader cannot track incrementality
        # This is a configuration error that must fail fast
        if not self.watermark_field:
            raise ValueError(
                f"[CRITICAL] watermark_field not configured for {self.table_name}. "
                "Cannot determine incremental load state for {symbol}. "
                "Must configure watermark_field for incremental loading."
            )

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    f"SELECT MAX({self.watermark_field}) FROM {assert_safe_table(self.table_name)} WHERE symbol = %s",
                    (symbol,),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return self._parse_watermark_date(row[0])
                # No row or NULL value = never fetched before (first run, not an error)
                logger.debug(f"No watermark found for {symbol} in {self.table_name} - will perform full refresh")
                return None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"Failed to read watermark for {symbol} from {self.table_name}: {e}. "
                f"Database error prevents incremental loading - cannot determine if {symbol} has been fetched before."
            ) from e

    @staticmethod
    def _parse_watermark_date(value: Any) -> date:
        """Parse watermark value to date.

        Handles both date-based watermarks (e.g., "2026-06-28") and
        year-based watermarks (e.g., 2026 for fiscal_year).

        Raises:
            ValueError: If value is None or parsing fails (watermark is critical for incrementality)
        """
        if value is None:
            raise ValueError(
                "[CRITICAL] Watermark value is None. Cannot parse None to date. "
                "Watermark is required for incremental loader state tracking."
            )
        if isinstance(value, date):
            return value
        try:
            # For year-only values (e.g., fiscal_year = 2026), return Jan 1 of that year
            str_val = str(value).strip()
            if len(str_val) == 4 and str_val.isdigit():
                year = int(str_val)
                if 1990 < year < 2100:
                    return date(year, 1, 1)
            # For ISO date values (e.g., "2026-06-28"), parse normally
            return date.fromisoformat(str_val.split("T")[0])
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"[CRITICAL] Failed to parse watermark value {value!r} to date. "
                f"Invalid format for incremental loader watermark: {e}"
            ) from e
