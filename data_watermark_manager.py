#!/usr/bin/env python3
"""
Atomic Watermark Manager - Guarantee "load only once" even if loader crashes.

The problem it solves:
  Loader starts, fetches data from day 1-100
  Inserts rows 1-50 successfully
  Insert row 51 FAILS (DB connection drops)
  Loader retries, fetches day 1-100 again
  Now we'd insert rows 1-50 again (DUPLICATION)

The solution:
  Use database transactions to make watermark updates ATOMIC with data inserts.
  Either both succeed or both fail together.
  Retry is safe: will just reload the same data again (idempotent).

How it works:
  1. Get current watermark (e.g., "2026-05-08")
  2. Load data from (watermark + 1 day) through today
  3. Insert all rows to database
  4. Update watermark ONLY if insert succeeded
  5. Commit transaction atomically

  If step 3 fails: watermark doesn't update, next run will retry same data
  If step 4 fails: worst case is we reload yesterday's data again (safe)

USAGE:
  wm = WatermarkManager(loader_name='loadpricedaily', table_name='price_daily')
  watermark = wm.get_current_watermark(symbol='AAPL')  # Returns last loaded date

  # Fetch data from (watermark + 1) through today
  start = watermark + timedelta(days=1) if watermark else some_old_date
  rows = fetch_data(symbol, start, today)
  insert_into_db(rows)

  # Atomically update watermark (only if DB is still connected)
  success = wm.advance_watermark(symbol='AAPL', new_watermark=today)
  if not success:
    raise Exception("Failed to update watermark - next run will retry")
"""

import logging
import psycopg2
import json
from datetime import date as _date, datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class WatermarkManager:
    """Manages atomic watermark updates for incremental data loading."""

    def __init__(
        self,
        loader_name: str,
        table_name: str,
        db_conn: psycopg2.extensions.connection,
        granularity: str = "symbol",  # 'symbol', 'global', or custom
    ):
        """
        Args:
            loader_name: Name of the loader (e.g., 'loadpricedaily')
            table_name: Table being loaded (e.g., 'price_daily')
            db_conn: Database connection
            granularity: Watermark scope
              - 'symbol': separate watermark per symbol
              - 'global': single watermark for all symbols
              - custom: custom granularity key
        """
        self.loader_name = loader_name
        self.table_name = table_name
        self.db_conn = db_conn
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
            with self.db_conn.cursor() as cur:
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
        in_transaction: bool = False,
    ) -> bool:
        """
        Atomically advance the watermark. Call this AFTER successfully inserting data.

        Args:
            new_watermark: The new watermark date (usually today)
            symbol: Symbol (if granularity='symbol')
            granularity_key: Custom key (if granularity is custom)
            rows_loaded: Number of rows loaded in this batch (for tracking)
            in_transaction: If True, don't commit (caller will commit)

        Returns:
            True if watermark was updated, False if failed

        Usage:
            # Start transaction
            db_conn.autocommit = False
            try:
                # Insert data
                cur.execute("INSERT INTO price_daily VALUES (...)")
                # Update watermark atomically
                if wm.advance_watermark(new_watermark=today, symbol='AAPL', in_transaction=True):
                    db_conn.commit()  # All or nothing
                else:
                    db_conn.rollback()
                    raise Exception("Watermark update failed")
            except Exception as e:
                db_conn.rollback()
                raise
        """
        try:
            with self.db_conn.cursor() as cur:
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

            if not in_transaction:
                self.db_conn.commit()
            return True

        except Exception as e:
            logger.error(f"Error advancing watermark: {e}")
            if not in_transaction:
                self.db_conn.rollback()
            return False

    def record_failure(
        self,
        error_message: str,
        symbol: Optional[str] = None,
        granularity_key: Optional[str] = None,
    ):
        """
        Record that a load attempt failed (watermark doesn't advance).
        Next run will retry from the same watermark.

        Args:
            error_message: What went wrong
            symbol: Symbol (if granularity='symbol')
            granularity_key: Custom key (if granularity is custom)
        """
        try:
            with self.db_conn.cursor() as cur:
                if self.granularity == "symbol":
                    cur.execute(
                        """
                        INSERT INTO loader_watermarks
                        (loader, symbol, granularity, watermark, error_count, last_error)
                        VALUES (%s, %s, %s, %s, 1, %s)
                        ON CONFLICT (loader, symbol, granularity)
                        DO UPDATE SET
                            error_count = error_count + 1,
                            last_error = %s,
                            last_run_at = NOW()
                        """,
                        (
                            self.loader_name,
                            symbol,
                            "symbol",
                            None,
                            error_message,
                            error_message,
                        ),
                    )
                elif self.granularity == "global":
                    cur.execute(
                        """
                        INSERT INTO loader_watermarks
                        (loader, symbol, granularity, watermark, error_count, last_error)
                        VALUES (%s, NULL, %s, %s, 1, %s)
                        ON CONFLICT (loader, symbol, granularity)
                        DO UPDATE SET
                            error_count = error_count + 1,
                            last_error = %s,
                            last_run_at = NOW()
                        """,
                        (
                            self.loader_name,
                            "global",
                            None,
                            error_message,
                            error_message,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO loader_watermarks
                        (loader, symbol, granularity, watermark, error_count, last_error)
                        VALUES (%s, %s, %s, %s, 1, %s)
                        ON CONFLICT (loader, symbol, granularity)
                        DO UPDATE SET
                            error_count = error_count + 1,
                            last_error = %s,
                            last_run_at = NOW()
                        """,
                        (
                            self.loader_name,
                            granularity_key,
                            self.granularity,
                            None,
                            error_message,
                            error_message,
                        ),
                    )

            self.db_conn.commit()
            logger.warning(
                f"[{self.loader_name}] Recorded failure: {error_message}"
            )

        except Exception as e:
            logger.error(f"Error recording failure: {e}")
            self.db_conn.rollback()

    def get_watermark_status(self) -> Dict[str, Any]:
        """
        Get status of all watermarks for this loader.
        Use for monitoring/debugging.

        Returns:
            Dict with watermark status for all symbols/keys
        """
        try:
            with self.db_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT loader, symbol, granularity, watermark,
                           rows_loaded, error_count, last_error,
                           last_run_at, last_success_at
                    FROM loader_watermarks
                    WHERE loader = %s
                    ORDER BY symbol, granularity
                    """,
                    (self.loader_name,),
                )
                rows = cur.fetchall()
                return {"loader": self.loader_name, "watermarks": rows}

        except Exception as e:
            logger.error(f"Error getting watermark status: {e}")
            return {"error": str(e)}
