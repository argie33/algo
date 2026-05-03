"""
Watermark-based incremental loading.

Each (loader, symbol) tracks its high-water mark — the latest timestamp/version
successfully loaded. Subsequent runs fetch only data after that watermark,
reducing API calls by 100x on incremental runs.

Storage:
    Watermarks live in a single PostgreSQL table (`loader_watermarks`).
    DynamoDB is faster but adds dependency; one table on existing DB is simpler.

Semantics:
    - Watermark advances only on successful insert (atomic).
    - Crash before commit = no advancement = next run retries (idempotent).
    - Watermark per (loader, symbol, granularity) tuple — lets daily and
      weekly loaders share a table without colliding.

Usage:
    from watermark_loader import Watermark

    wm = Watermark("price_daily")
    last = wm.get("AAPL")  # date or None
    new_data = fetch_after(last)
    insert(new_data)
    wm.set("AAPL", new_data[-1].date)

Or use the context manager (atomic update):
    with wm.advance("AAPL", target_date) as ctx:
        new_data = fetch_after(ctx.previous)
        insert(new_data)
        # commit on success advances watermark to target_date
"""

from __future__ import annotations

import contextlib
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterator, Optional, Union

import psycopg2
from psycopg2.extras import execute_values

log = logging.getLogger(__name__)

WatermarkValue = Union[date, datetime, str, int]


@dataclass
class WatermarkContext:
    """Returned by Watermark.advance(); commits on __exit__."""
    loader: str
    symbol: str
    granularity: str
    previous: Optional[WatermarkValue]


SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS loader_watermarks (
    loader TEXT NOT NULL,
    symbol TEXT NOT NULL,
    granularity TEXT NOT NULL DEFAULT 'default',
    watermark TEXT NOT NULL,
    rows_loaded BIGINT NOT NULL DEFAULT 0,
    last_run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_success_at TIMESTAMPTZ,
    error_count INT NOT NULL DEFAULT 0,
    last_error TEXT,
    PRIMARY KEY (loader, symbol, granularity)
);

CREATE INDEX IF NOT EXISTS idx_loader_watermarks_loader_run
    ON loader_watermarks (loader, last_run_at DESC);
"""


class Watermark:
    """Watermark store backed by PostgreSQL.

    Args:
        loader: Logical loader name (e.g. "price_daily", "annual_balance_sheet").
        granularity: Optional sub-scope when one loader handles multiple grains.
        connection_factory: Override for testing (returns psycopg2 connection).
    """

    def __init__(
        self,
        loader: str,
        granularity: str = "default",
        connection_factory=None,
    ):
        self.loader = loader
        self.granularity = granularity
        self._connection_factory = connection_factory or self._default_connection
        self._ensure_schema()

    @staticmethod
    def _default_connection():
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "stocks"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "stocks"),
        )

    def _ensure_schema(self) -> None:
        try:
            with self._connection_factory() as conn:
                with conn.cursor() as cur:
                    cur.execute(SCHEMA_DDL)
                conn.commit()
        except Exception as e:
            log.warning("Watermark schema init failed: %s", e)

    # ----- Read -----

    def get(self, symbol: str) -> Optional[WatermarkValue]:
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT watermark FROM loader_watermarks
                       WHERE loader=%s AND symbol=%s AND granularity=%s""",
                    (self.loader, symbol, self.granularity),
                )
                row = cur.fetchone()
                return row[0] if row else None

    def get_all(self) -> dict:
        """Bulk-read all watermarks for this loader. Returns {symbol: watermark}."""
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT symbol, watermark FROM loader_watermarks
                       WHERE loader=%s AND granularity=%s""",
                    (self.loader, self.granularity),
                )
                return dict(cur.fetchall())

    def stale_symbols(self, all_symbols: list, max_age: timedelta) -> list:
        """Return symbols whose watermark is older than max_age.

        Useful for prioritizing — load most-stale symbols first.
        """
        watermarks = self.get_all()
        cutoff = datetime.utcnow() - max_age
        result = []
        for symbol in all_symbols:
            wm = watermarks.get(symbol)
            if wm is None:
                result.append(symbol)
                continue
            try:
                wm_dt = datetime.fromisoformat(str(wm))
                if wm_dt < cutoff:
                    result.append(symbol)
            except (ValueError, TypeError):
                result.append(symbol)
        return result

    # ----- Write -----

    def set(
        self,
        symbol: str,
        watermark: WatermarkValue,
        rows_loaded: int = 0,
    ) -> None:
        wm_str = self._serialize(watermark)
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO loader_watermarks
                       (loader, symbol, granularity, watermark, rows_loaded,
                        last_run_at, last_success_at, error_count, last_error)
                       VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), 0, NULL)
                       ON CONFLICT (loader, symbol, granularity) DO UPDATE SET
                         watermark = EXCLUDED.watermark,
                         rows_loaded = loader_watermarks.rows_loaded + EXCLUDED.rows_loaded,
                         last_run_at = NOW(),
                         last_success_at = NOW(),
                         error_count = 0,
                         last_error = NULL""",
                    (self.loader, symbol, self.granularity, wm_str, rows_loaded),
                )
                conn.commit()

    def set_batch(self, updates: list) -> None:
        """Batch update watermarks. updates = [(symbol, watermark, rows_loaded), ...]."""
        if not updates:
            return
        rows = [(self.loader, s, self.granularity, self._serialize(w), r) for s, w, r in updates]
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO loader_watermarks
                       (loader, symbol, granularity, watermark, rows_loaded,
                        last_run_at, last_success_at, error_count, last_error)
                       VALUES %s
                       ON CONFLICT (loader, symbol, granularity) DO UPDATE SET
                         watermark = EXCLUDED.watermark,
                         rows_loaded = loader_watermarks.rows_loaded + EXCLUDED.rows_loaded,
                         last_run_at = NOW(),
                         last_success_at = NOW(),
                         error_count = 0,
                         last_error = NULL""",
                    [
                        (loader, symbol, gran, wm, rows, datetime.utcnow(),
                         datetime.utcnow(), 0, None)
                        for loader, symbol, gran, wm, rows in rows
                    ],
                    template="(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                )
                conn.commit()

    def record_error(self, symbol: str, error: str) -> None:
        """Increment error count without advancing watermark."""
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO loader_watermarks
                       (loader, symbol, granularity, watermark, last_run_at, error_count, last_error)
                       VALUES (%s, %s, %s, '0', NOW(), 1, %s)
                       ON CONFLICT (loader, symbol, granularity) DO UPDATE SET
                         last_run_at = NOW(),
                         error_count = loader_watermarks.error_count + 1,
                         last_error = EXCLUDED.last_error""",
                    (self.loader, symbol, self.granularity, error[:500]),
                )
                conn.commit()

    # ----- Atomic context manager -----

    @contextlib.contextmanager
    def advance(self, symbol: str, target: WatermarkValue) -> Iterator[WatermarkContext]:
        """Yield context with previous watermark; commit advances to `target`.

        On exception inside the with block, watermark is NOT advanced —
        and an error is recorded. This guarantees idempotency: a failed
        run leaves watermark at last successful position.
        """
        previous = self.get(symbol)
        try:
            yield WatermarkContext(
                loader=self.loader,
                symbol=symbol,
                granularity=self.granularity,
                previous=previous,
            )
            self.set(symbol, target)
        except Exception as e:
            self.record_error(symbol, str(e))
            raise

    # ----- Helpers -----

    @staticmethod
    def _serialize(value: WatermarkValue) -> str:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value)

    @staticmethod
    def parse_date(watermark: Optional[str]) -> Optional[date]:
        """Convert stored string watermark back to a date."""
        if not watermark:
            return None
        try:
            return date.fromisoformat(watermark.split("T")[0])
        except ValueError:
            return None
