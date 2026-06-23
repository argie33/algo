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
        """Read per-symbol watermark from database."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    f"SELECT MAX({self.watermark_field}) FROM {assert_safe_table(self.table_name)} WHERE symbol = %s",
                    (symbol,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return self._parse_watermark_date(row[0])
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Failed to read watermark for {symbol}: {e}")
        return None

    @staticmethod
    def _parse_watermark_date(value: Any) -> date | None:
        """Parse watermark value to date."""
        if value is None:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value).split("T")[0])
        except (ValueError, TypeError):
            return None
