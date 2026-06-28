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
        """Get cached watermark for a symbol."""
        return self._marks.get(symbol)

    def set(self, symbol: str, value: date | None, rows_loaded: int = 0) -> None:
        """Set watermark for a symbol (in-memory only)."""
        if value is not None:
            self._marks[symbol] = value

    def read_from_db(self, symbol: str) -> date | None:
        """Read per-symbol watermark from database.

        Returns:
            date if watermark exists (data has been fetched before)
            None if no watermark row exists (never fetched)

        Raises:
            DatabaseError if DB query fails (distinguish from "never fetched")
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    f"SELECT MAX({self.watermark_field}) FROM {assert_safe_table(self.table_name)} WHERE symbol = %s",
                    (symbol,),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return self._parse_watermark_date(row[0])
                # No row or NULL value = never fetched before (not an error)
                return None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"Failed to read watermark for {symbol} from {self.table_name}: {e}. "
                f"Database error prevents incremental loading — cannot determine if {symbol} has been fetched before."
            ) from e

    @staticmethod
    def _parse_watermark_date(value: Any) -> date | None:
        """Parse watermark value to date.

        Handles both date-based watermarks (e.g., "2026-06-28") and
        year-based watermarks (e.g., 2026 for fiscal_year).
        """
        if value is None:
            return None
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
        except (ValueError, TypeError):
            return None
