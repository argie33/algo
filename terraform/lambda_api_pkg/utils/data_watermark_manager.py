#!/usr/bin/env python3

import logging
import json
from datetime import date as _date, datetime
from typing import Optional, Dict, Any
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

class WatermarkManager:
    """Manages atomic watermark updates for incremental data loading."""

    def __init__(
        self,
        loader_name: str,
        table_name: str,
        db_conn=None,  # Deprecated: kept for backwards compatibility, no longer used
        granularity: str = "symbol",  # 'symbol', 'global', or custom
    ):
        self.loader_name = loader_name
        self.table_name = table_name
        self.granularity = granularity

    def get_current_watermark(
        self,
        symbol: Optional[str] = None,
        granularity_key: Optional[str] = None,
    ) -> Optional[_date]:
        """
        Get the current watermark (last successfully loaded data point).

        Args:
            symbol: Symbol (if granularity='symbol')
            granularity_key: Custom key (if granularity is custom)

        Returns:
            watermark date, or None if never loaded
        """
        try:
            with DatabaseContext('read') as cur:
                if self.granularity == "symbol":
                    if not symbol:
                        raise ValueError("symbol required for granularity='symbol'")
                    cur.execute(
                        """
                        SELECT watermark FROM loader_watermarks
                        WHERE loader = %s AND symbol = %s AND granularity = %s
                        """,
                        (self.loader_name, symbol, "symbol"),
                    )
                elif self.granularity == "global":
                    cur.execute(
                        """
                        SELECT watermark FROM loader_watermarks
                        WHERE loader = %s AND symbol IS NULL AND granularity = %s
                        """,
                        (self.loader_name, "global"),
                    )
                else:
                    # Custom granularity
                    cur.execute(
                        """
                        SELECT watermark FROM loader_watermarks
                        WHERE loader = %s AND symbol = %s AND granularity = %s
                        """,
                        (self.loader_name, granularity_key, self.granularity),
                    )

                row = cur.fetchone()
                if row:
                    watermark_str = row[0]
                    if watermark_str:
                        return _date.fromisoformat(watermark_str)
                return None
        except Exception as e:
            logger.error(f"Error getting watermark: {e}")
            return None

    def advance_watermark(
        self,
        new_watermark: _date,
        symbol: Optional[str] = None,
        granularity_key: Optional[str] = None,
        rows_loaded: int = 0,
        in_transaction: bool = False,  # Deprecated: ignored, DatabaseContext handles it
    ) -> bool:
        """
        Atomically advance the watermark. Call this AFTER successfully inserting data.

        Args:
            new_watermark: The new watermark date (usually today)
            symbol: Symbol (if granularity='symbol')
            granularity_key: Custom key (if granularity is custom)
            rows_loaded: Number of rows loaded in this batch (for tracking)
            in_transaction: Deprecated - no longer used (DatabaseContext handles transactions)

        Returns:
            True if watermark was updated, False if failed
        """
        try:
            with DatabaseContext('write') as cur:
                watermark_str = new_watermark.isoformat()

                if self.granularity == "symbol":
                    if not symbol:
                        raise ValueError("symbol required for granularity='symbol'")
                    cur.execute(
                        """
                        INSERT INTO loader_watermarks
                        (loader, symbol, granularity, watermark, rows_loaded, last_run_at, last_success_at)
                        VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (loader, symbol, granularity)
                        DO UPDATE SET
                            watermark = %s,
                            rows_loaded = rows_loaded + %s,
                            last_run_at = NOW(),
                            last_success_at = NOW(),
                            error_count = 0,
                            last_error = NULL
                        """,
                        (
                            self.loader_name,
                            symbol,
                            "symbol",
                            watermark_str,
                            rows_loaded,
                            watermark_str,
                            rows_loaded,
                        ),
                    )

                elif self.granularity == "global":
                    cur.execute(
                        """
                        INSERT INTO loader_watermarks
                        (loader, symbol, granularity, watermark, rows_loaded, last_run_at, last_success_at)
                        VALUES (%s, NULL, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (loader, symbol, granularity)
                        DO UPDATE SET
                            watermark = %s,
                            rows_loaded = rows_loaded + %s,
                            last_run_at = NOW(),
                            last_success_at = NOW(),
                            error_count = 0,
                            last_error = NULL
                        """,
                        (
                            self.loader_name,
                            "global",
                            watermark_str,
                            rows_loaded,
                            watermark_str,
                            rows_loaded,
                        ),
                    )

                else:
                    # Custom granularity
                    cur.execute(
                        """
                        INSERT INTO loader_watermarks
                        (loader, symbol, granularity, watermark, rows_loaded, last_run_at, last_success_at)
                        VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (loader, symbol, granularity)
                        DO UPDATE SET
                            watermark = %s,
                            rows_loaded = rows_loaded + %s,
                            last_run_at = NOW(),
                            last_success_at = NOW(),
                            error_count = 0,
                            last_error = NULL
                        """,
                        (
                            self.loader_name,
                            granularity_key,
                            self.granularity,
                            watermark_str,
                            rows_loaded,
                            watermark_str,
                            rows_loaded,
                        ),
                    )

                return True

        except Exception as e:
            logger.error(f"Error advancing watermark: {e}")
            return False

    def record_error(
        self,
        symbol: Optional[str] = None,
        granularity_key: Optional[str] = None,
        error_message: str = "",
    ):
        """Record an error for this watermark entry."""
        try:
            with DatabaseContext('write') as cur:
                if self.granularity == "symbol":
                    if not symbol:
                        raise ValueError("symbol required")
                    cur.execute(
                        """
                        INSERT INTO loader_watermarks
                        (loader, symbol, granularity, last_error, last_error_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT (loader, symbol, granularity)
                        DO UPDATE SET
                            error_count = error_count + 1,
                            last_error = %s,
                            last_error_at = NOW()
                        """,
                        (self.loader_name, symbol, "symbol", error_message, error_message),
                    )
                elif self.granularity == "global":
                    cur.execute(
                        """
                        INSERT INTO loader_watermarks
                        (loader, symbol, granularity, last_error, last_error_at)
                        VALUES (%s, NULL, %s, %s, NOW())
                        ON CONFLICT (loader, symbol, granularity)
                        DO UPDATE SET
                            error_count = error_count + 1,
                            last_error = %s,
                            last_error_at = NOW()
                        """,
                        (self.loader_name, "global", error_message, error_message),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO loader_watermarks
                        (loader, symbol, granularity, last_error, last_error_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT (loader, symbol, granularity)
                        DO UPDATE SET
                            error_count = error_count + 1,
                            last_error = %s,
                            last_error_at = NOW()
                        """,
                        (self.loader_name, granularity_key, self.granularity, error_message, error_message),
                    )
        except Exception as e:
            logger.error(f"Failed to record error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get status of all watermarks for this loader."""
        try:

            with DatabaseContext('read') as cur:
                cur.execute(
                    "SELECT symbol, granularity, watermark, error_count, last_error FROM loader_watermarks WHERE loader = %s",
                    (self.loader_name,),
                )
                rows = cur.fetchall()
                return {"loader": self.loader_name, "watermarks": rows}

        except Exception as e:
            logger.error(f"Error getting watermark status: {e}")
            return {"error": str(e)}
