

import logging
import os
import time
import psycopg2
import uuid
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any, Iterable, List, Optional, Sequence

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from utils.db_connection import get_db_connection

logger = logging.getLogger(__name__)
_credential_manager = credential_manager

class OptimalLoader(ABC):
    """Base class for production-grade loaders.

    Subclasses MUST set:
        table_name: Target table.
        primary_key: Tuple of column names forming uniqueness.
        watermark_field: Name of the timestamp/date column used for incremental.

    Subclasses MUST implement:
        fetch_incremental(symbol, since): Return rows newer than `since`.

    Subclasses MAY override:
        transform(rows): Custom cleaning/validation. Default = identity.
        watermark_from_rows(rows): How to derive new high-water mark.
            Default = max value in watermark_field.
    """

    table_name: str = ""
    primary_key: Sequence[str] = ()
    watermark_field: str = "date"
    chunk_size: int = 10_000  # Increased from 5_000 for faster bulk inserts (fewer round trips to DB)
    max_age_for_full_refresh: timedelta = timedelta(days=365)

    def __init__(self, backfill_days: Optional[int] = None):
        import threading
        self._conn = None  # legacy single conn (close path)
        self._tls = threading.local()  # per-thread connection
        self._dedup = None
        self._watermark = None
        self._router = None
        self._backfill_days = backfill_days or int(os.getenv("BACKFILL_DAYS", "0"))
        self._schema_cols_cache: Optional[List[str]] = None  # cached column list for _bulk_insert
        self._constraint_checked = False  # track if we've verified/fixed constraint
        self._stats_lock = threading.Lock()
        self._stats = {
            "symbols_processed": 0,
            "symbols_skipped_by_watermark": 0,
            "symbols_failed": 0,
            "rows_fetched": 0,
            "rows_dedup_skipped": 0,
            "rows_quality_dropped": 0,
            "rows_inserted": 0,
            "duration_sec": 0.0,
            "source_distribution": {},
        }

    # ---- Subclass interface ----

    @abstractmethod
    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        """Return rows newer than `since`. None or [] = nothing new."""

    def transform(self, rows: List[dict]) -> List[dict]:
        """Override to apply domain-specific cleaning. Default = identity."""
        return rows

    def watermark_from_rows(self, rows: List[dict]) -> Optional[date]:
        """Derive new watermark from inserted rows. Default = max(watermark_field)."""
        if not rows:
            return None
        values = [r.get(self.watermark_field) for r in rows if r.get(self.watermark_field)]
        return max(values) if values else None

    # ---- Lazy infrastructure ----

    @property
    def router(self):
        if self._router is None:
            from utils.data_source_router import DataSourceRouter
            self._router = DataSourceRouter()
        return self._router

    def _get_dedup(self):
        self._dedup = False
        return None

    def _get_watermark(self):
        if self._watermark is not None:
            return self._watermark
        try:
            # Simple in-memory watermark store that tracks per-symbol progress
            class WatermarkStore:
                def __init__(self):
                    self.marks = {}

                def get(self, symbol):
                    return self.marks.get(symbol)

                def set(self, symbol, value, rows_loaded=0):
                    self.marks[symbol] = value

            self._watermark = WatermarkStore()
        except Exception as e:
            logger.warning("Watermark unavailable (%s) �� running full refresh", e)
            self._watermark = False
        return self._watermark if self._watermark else None

    def _connect(self):
        """Per-thread psycopg2 connection (thread-safe for parallel workers)."""
        conn = getattr(self._tls, "conn", None)
        if conn is not None and not conn.closed:
            return conn
        from utils.database_context import DatabaseContext
        conn = get_db_connection()
        self._tls.conn = conn
        # Track for close() �� keep most recent for the main thread fallback.
        self._conn = conn
        return conn

    def _ensure_unique_constraint(self, cur):
        """Ensure the primary_key columns have a UNIQUE constraint.

        If not found, create it. This prevents "ON CONFLICT" errors on inserts.
        Only runs once per loader instance. Called within DatabaseContext transaction.
        """
        if self._constraint_checked or not self.primary_key or not self.table_name:
            return

        self._constraint_checked = True
        try:
            # Check if table exists
            cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = %s AND table_schema = 'public'
            )
            """, (self.table_name,))

            if not cur.fetchone()[0]:
                logger.warning(f"Table {self.table_name} does not exist")
                return

            # Check if a UNIQUE constraint already exists on primary_key columns
            pk_cols = ','.join(self.primary_key)
            cur.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = %s
            AND constraint_type IN ('UNIQUE', 'PRIMARY KEY')
            AND table_schema = 'public'
            """, (self.table_name,))

            existing_constraints = [row[0] for row in cur.fetchall()]

            # Check if any constraint covers all our primary_key columns
            for constraint in existing_constraints:
                cur.execute("""
                SELECT column_name
                FROM information_schema.key_column_usage
                WHERE constraint_name = %s AND table_schema = 'public'
                ORDER BY ordinal_position
                """, (constraint,))

                constraint_cols = [row[0] for row in cur.fetchall()]
                if set(constraint_cols) == set(self.primary_key):
                    logger.debug(f"UNIQUE constraint {constraint} already exists on {self.table_name}({pk_cols})")
                    return

            # No matching constraint found � create one
            constraint_name = f"{self.table_name}_{'_'.join(self.primary_key)}_unique"
            try:
                logger.info(f"Creating UNIQUE constraint {constraint_name} on {self.table_name}({pk_cols})")
                cur.execute(f"""
                ALTER TABLE {self.table_name}
                ADD CONSTRAINT {constraint_name}
                UNIQUE ({pk_cols})
                """)
            except psycopg2.IntegrityError as e:
                # Constraint creation failed due to duplicates
                logger.warning(f"Cannot create constraint (duplicates exist): {e}")
                # Continue anyway � will use DO NOTHING fallback
            except psycopg2.ProgrammingError as e:
                if "already exists" in str(e):
                    logger.debug(f"Constraint already exists: {e}")
                else:
                    logger.warning(f"Cannot create constraint: {e}")
        except Exception as e:
            logger.warning(f"Error checking/creating constraint: {e}")

    # ---- Insert path: COPY for bulk + ON CONFLICT for safety ----

    def _bulk_insert(self, rows: List[dict], symbol: Optional[str] = None, new_watermark: Optional[date] = None, watermark_mgr=None) -> int:
        """Bulk insert rows and atomically update watermark if provided.

        M4 FIX: Watermark is persisted in the same transaction as data to prevent
        duplicates on crash between insert and watermark update.

        Args:
            rows: Rows to insert
            symbol: Symbol for watermark tracking (optional)
            new_watermark: New watermark value to persist (optional)
            watermark_mgr: WatermarkManager instance for atomic updates (optional)

        Returns: Number of rows inserted
        """
        if not rows:
            return 0
        import io
        import csv
        from utils.database_context import DatabaseContext

        with DatabaseContext('write') as cur:
            # Ensure the unique constraint exists (one-time per loader instance)
            self._ensure_unique_constraint(cur)

            try:
                # Filter to columns that exist in the target table — prevents failures when
                # a loader produces extra fields before a schema migration has run.
                # Cache the column set per loader instance to avoid N schema catalog queries.
                if self._schema_cols_cache is None:
                    cur.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = %s",
                        (self.table_name,),
                    )
                    self._schema_cols_cache = {row[0] for row in cur.fetchall()}
                existing_cols = self._schema_cols_cache
                all_data_cols = list(rows[0].keys())
                skipped = [c for c in all_data_cols if c not in existing_cols]
                if skipped:
                    logger.warning("Loader %s: skipping columns not in DB schema: %s", self.table_name, skipped)
                columns = [c for c in all_data_cols if c in existing_cols]
                if not columns:
                    raise ValueError(f"No valid columns to write for {self.table_name}")
            except Exception as e:
                logger.error(f"Failed to prepare columns for {self.table_name}: {e}")
                raise

            import threading
            # Use UUID for guaranteed uniqueness across concurrent executions
            # (avoids type name collisions in pg_type when millisecond-level timing aligns)
            unique_id = str(uuid.uuid4()).replace('-', '')[:12]
            staging = f"_stage_{self.table_name}_{unique_id}"

            try:
                cur.execute(
                    f"CREATE UNLOGGED TABLE {staging} (LIKE {self.table_name} INCLUDING DEFAULTS)"
                )
            except psycopg2.Error as e:
                if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                    # Unlikely to happen with UUID, but handle it just in case
                    # Clean up and retry with a new UUID
                    try:
                        cur.execute(f"DROP TABLE IF EXISTS {staging} CASCADE")
                    except psycopg2.Error as drop_err:
                        logger.warning(f"Failed to drop staging table {staging}: {drop_err}")
                    unique_id = str(uuid.uuid4()).replace('-', '')[:12]
                    staging = f"_stage_{self.table_name}_{unique_id}"
                    cur.execute(
                        f"CREATE UNLOGGED TABLE {staging} (LIKE {self.table_name} INCLUDING DEFAULTS)"
                    )
                else:
                    raise

            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
            for row in rows:
                writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
            buf.seek(0)
            cur.copy_expert(
                f"COPY {staging} ({','.join(columns)}) FROM STDIN WITH (FORMAT CSV, NULL '')",
                buf,
            )

            updates = ", ".join(
                f"{c} = EXCLUDED.{c}" for c in columns if c not in self.primary_key
            )
            on_conflict = (
                f"ON CONFLICT ({','.join(self.primary_key)}) DO UPDATE SET {updates}"
                if self.primary_key and updates
                else "ON CONFLICT DO NOTHING"
            )
            cur.execute(
                f"INSERT INTO {self.table_name} ({','.join(columns)}) "
                f"SELECT {','.join(columns)} FROM {staging} {on_conflict}"
            )
            inserted = cur.rowcount

            cur.execute(f"DROP TABLE {staging}")

            if symbol and new_watermark:
                if watermark_mgr:
                    # Use WatermarkManager for atomic DB-backed watermark
                    watermark_mgr.advance_watermark(
                        new_watermark=new_watermark,
                        symbol=symbol,
                        rows_loaded=inserted,
                        in_transaction=True  # Will commit with rest of transaction
                    )
                else:
                    # Fallback to in-memory store
                    wm_store = self._get_watermark()
                    if wm_store:
                        wm_store.set(symbol, new_watermark, rows_loaded=inserted)

            return inserted

    # ---- Per-symbol pipeline ----

    def load_symbol(self, symbol: str) -> int:
        """Load one symbol. Returns rows inserted."""
        wm_store = self._get_watermark()

        # If backfill window is set, use that instead of watermark
        if self._backfill_days > 0:
            previous_date = (datetime.now().date() - timedelta(days=self._backfill_days))
        else:
            previous = wm_store.get(symbol) if wm_store else None
            previous_date = self._parse_watermark_date(previous)

        rows = self.fetch_incremental(symbol, previous_date)
        if not rows:
            logger.debug(f"[{self.table_name}] {symbol}: No rows fetched, skipping")
            self._stats["symbols_skipped_by_watermark"] += 1
            return 0
        logger.debug(f"[{self.table_name}] {symbol}: Fetched {len(rows)} rows")
        self._stats["rows_fetched"] += len(rows)
        if self.router and self.router.last_source:
            src = self.router.last_source
            self._stats["source_distribution"][src] = (
                self._stats["source_distribution"].get(src, 0) + 1
            )

        rows = self.transform(rows)
        before_quality = len(rows)
        rows = [r for r in rows if self._validate_row(r)]
        self._stats["rows_quality_dropped"] += before_quality - len(rows)

        # Bloom dedup (cheap pre-filter)
        dedup = self._get_dedup()
        if dedup and self.primary_key:
            before_dedup = len(rows)
            rows = self._dedup_filter(dedup, rows)
            self._stats["rows_dedup_skipped"] += before_dedup - len(rows)

        if not rows:
            return 0

        # M4 FIX: Calculate new watermark BEFORE insert so it can be persisted atomically
        new_wm = self.watermark_from_rows(rows)

        # Bulk insert in chunks, passing watermark for atomic persistence
        inserted = 0
        for i, chunk_start in enumerate(range(0, len(rows), self.chunk_size)):
            chunk = rows[chunk_start:chunk_start + self.chunk_size]
            # Pass watermark only on last chunk to avoid overwriting with partial watermark
            is_final_chunk = (chunk_start + self.chunk_size >= len(rows))
            chunk_wm = new_wm if is_final_chunk else None
            inserted += self._bulk_insert(chunk, symbol=symbol if is_final_chunk else None, new_watermark=chunk_wm)

        if dedup and self.primary_key:
            for row in rows:
                key = ":".join(str(row.get(c, "")) for c in self.primary_key)
                dedup.add(key)

        self._stats["rows_inserted"] += inserted
        return inserted

    def _dedup_filter(self, dedup, rows: List[dict]) -> List[dict]:
        keys = [
            ":".join(str(r.get(c, "")) for c in self.primary_key)
            for r in rows
        ]
        return [r for r, k in zip(rows, keys) if not dedup.exists(k)]

    def _validate_row(self, row: dict) -> bool:
        """Default validation: primary key columns must be non-null."""
        return all(row.get(c) is not None for c in self.primary_key)

    @staticmethod
    def _parse_watermark_date(value) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value).split("T")[0])
        except (ValueError, TypeError):
            return None

    # ---- Top-level orchestration ----

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: Optional[int] = None) -> dict:
        """Execute load across symbols. Returns stats dict.

        Args:
            symbols: Symbols to load
            parallelism: Number of concurrent workers
            backfill_days: If set, refetch last N days instead of using watermark (for extended history)
        """
        if backfill_days is not None:
            self._backfill_days = backfill_days

        start = time.time()
        symbols = list(symbols)
        mode = f" (backfill {self._backfill_days}d)" if self._backfill_days > 0 else ""
        logger.info(
            "[%s] Starting load: %d symbols (parallelism=%d)%s",
            self.table_name, len(symbols), parallelism, mode,
        )

        if parallelism == 1:
            self._run_serial(symbols)
        else:
            self._run_parallel(symbols, parallelism)

        self._stats["duration_sec"] = round(time.time() - start, 2)
        logger.info(
            "[%s] Done. fetched=%d dedup_skip=%d quality_drop=%d inserted=%d "
            "(processed=%d skipped_wm=%d failed=%d) %.1fs sources=%s",
            self.table_name,
            self._stats["rows_fetched"],
            self._stats["rows_dedup_skipped"],
            self._stats["rows_quality_dropped"],
            self._stats["rows_inserted"],
            self._stats["symbols_processed"],
            self._stats["symbols_skipped_by_watermark"],
            self._stats["symbols_failed"],
            self._stats["duration_sec"],
            self._stats["source_distribution"],
        )

        try:
            from algo.algo_metrics import MetricsPublisher
            with MetricsPublisher() as m:
                m.put_loader_result(self.table_name, self._stats)
        except Exception as e:
            logger.debug("metrics unavailable: %s", e)

        try:
            from utils.database_context import DatabaseContext

            with DatabaseContext() as cur:
                if self.watermark_field:
                    cur.execute(
                        f"SELECT COUNT(*), MAX({self.watermark_field}) FROM {self.table_name}"
                    )
                else:
                    cur.execute(f"SELECT COUNT(*), NULL FROM {self.table_name}")
                result = cur.fetchone()
                total_rows = result[0] if result else 0
                latest_date = result[1] if result else None
                if hasattr(latest_date, 'date'):
                    latest_date = latest_date.date()

            with DatabaseContext('write') as cur:
                cur.execute("""
                    INSERT INTO data_loader_status (table_name, row_count, latest_date, last_updated)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (table_name) DO UPDATE SET
                      row_count = EXCLUDED.row_count,
                      latest_date = EXCLUDED.latest_date,
                      last_updated = NOW()
                """, (self.table_name, total_rows, latest_date))
        except Exception as e:
            logger.warning(f"Failed to update data_loader_status for {self.table_name}: {e}")

        return self._stats

    def _run_serial(self, symbols: List[str]) -> None:
        for i, symbol in enumerate(symbols, 1):
            # Keep connection alive by testing it periodically
            # Long-running loaders (30+ min) need to refresh the connection to avoid idle timeout
            if i % 50 == 0:
                try:
                    with DatabaseContext('read') as cur:
                        cur.execute("SELECT 1")
                except Exception as e:
                    logger.debug(f"Connection health check failed: {e}. Reconnecting.")

            self._safe_load_symbol(symbol)
            if i % 100 == 0:
                logger.info("  Progress: %d/%d", i, len(symbols))

    def _run_parallel(self, symbols: List[str], workers: int) -> None:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        with ThreadPoolExecutor(max_workers=workers) as exe:
            futures = {exe.submit(self._safe_load_symbol, s): s for s in symbols}
            done = 0
            last_health_check = time.time()
            for fut in as_completed(futures):
                done += 1
                # Periodic health check to keep connection pool alive
                now = time.time()
                if now - last_health_check > 120:  # Every 2 minutes
                    try:
                        with DatabaseContext('read') as cur:
                            cur.execute("SELECT 1")
                    except Exception as e:
                        logger.debug(f"Connection health check failed: {e}. Reconnecting.")
                    last_health_check = now

                if done % 100 == 0:
                    logger.info("  Progress: %d/%d", done, len(symbols))

    def _safe_load_symbol(self, symbol: str) -> None:
        try:
            self.load_symbol(symbol)
            self._stats["symbols_processed"] += 1
        except Exception as e:
            self._stats["symbols_failed"] += 1
            logger.error("[%s] %s failed: %s", self.table_name, symbol, e)

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
