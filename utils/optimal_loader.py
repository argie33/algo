import logging
import os
import signal
import threading
import time
import uuid
from abc import ABC
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Sequence

import psycopg2
import psycopg2.sql

from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)


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
    chunk_size: int = (
        10_000  # Increased from 5_000 for faster bulk inserts (fewer round trips to DB)
    )
    max_age_for_full_refresh: timedelta = timedelta(days=365)

    def __init__(self, backfill_days: Optional[int] = None):
        self._dedup = None
        self._watermark = None
        self._router = None
        self._backfill_days = backfill_days or int(os.getenv("BACKFILL_DAYS", "0"))
        self._schema_cols_cache: Optional[List[str]] = (
            None  # cached column list for _bulk_insert
        )
        self._constraint_checked = False  # track if we've verified/fixed constraint
        self._stats_lock = threading.Lock()
        self._shutdown_requested = False
        self._shutdown_lock = threading.Lock()
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
        self._heartbeat_thread = None
        self._heartbeat_running = False
        self._heartbeat_lock = threading.Lock()
        self._heartbeat_interval = 60  # ISSUE #12 FIX: 1-minute interval for responsive hung detection
        self._setup_signal_handlers()
        self._validate_runtime_config()

    def _setup_signal_handlers(self) -> None:
        """Register SIGTERM handler for graceful shutdown on ECS task termination."""

        def handle_shutdown(signum, frame):
            with self._shutdown_lock:
                if not self._shutdown_requested:
                    self._shutdown_requested = True
                    logger.warning(
                        f"[{self.table_name}] SIGTERM received - graceful shutdown requested"
                    )

        signal.signal(signal.SIGTERM, handle_shutdown)

    def _start_heartbeat(self) -> None:
        """Start a background thread that updates loader status every 60 seconds.

        ISSUE #12 FIX: Increased frequency from every 5 minutes to every 60 seconds.
        This heartbeat mechanism allows Phase 1 to detect hung/stalled loader tasks.
        Phase 1 considers task hung if no heartbeat for >3 minutes (default timeout).
        With 60-second updates, hung tasks are detected within 3-5 minutes instead of 8-10.
        """
        with self._heartbeat_lock:
            if self._heartbeat_running:
                return
            self._heartbeat_running = True

        def heartbeat_worker():
            while self._heartbeat_running:
                try:
                    time.sleep(self._heartbeat_interval)
                    if self._heartbeat_running:
                        # Update last_updated timestamp to signal loader is alive
                        with DatabaseContext("write") as cur:
                            cur.execute(
                                "UPDATE data_loader_status SET last_updated = NOW() "
                                "WHERE table_name = %s AND status = %s",
                                (self.table_name, "RUNNING")
                            )
                except Exception as e:
                    logger.debug(f"Heartbeat update failed: {e}")

        self._heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        """Stop the heartbeat background thread."""
        with self._heartbeat_lock:
            self._heartbeat_running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)

    def _update_loader_status(self, status: str) -> None:
        """Update loader status in data_loader_status table.

        Status values: 'RUNNING' (loader started), 'COMPLETED' (loader finished).
        Used by Phase 1 to detect if loader is in progress vs finished.
        """
        try:
            with DatabaseContext("write") as cur:
                if status == "RUNNING":
                    # Mark loader as running, preserve prior stats if any
                    # ISSUE #2 FIX: Set execution_started to track when loader began
                    cur.execute(
                        "UPDATE data_loader_status SET status = %s, last_updated = NOW(), execution_started = NOW() "
                        "WHERE table_name = %s",
                        (status, self.table_name)
                    )
                    if cur.rowcount == 0:
                        # First run, insert entry
                        cur.execute(
                            "INSERT INTO data_loader_status (table_name, status, last_updated, execution_started) "
                            "VALUES (%s, %s, NOW(), NOW())",
                            (self.table_name, status)
                        )
                    logger.debug(f"[{self.table_name}] Status updated to RUNNING, execution_started recorded")
                elif status == "COMPLETED":
                    # Mark loader as completed with current timestamp
                    # ISSUE #2 FIX: Set execution_completed to detect post-completion crashes (>10 min old = likely crash)
                    cur.execute(
                        "UPDATE data_loader_status SET status = %s, last_updated = NOW(), execution_completed = NOW() "
                        "WHERE table_name = %s",
                        (status, self.table_name)
                    )
                    logger.debug(f"[{self.table_name}] Status updated to COMPLETED, execution_completed timestamp recorded")
        except Exception as e:
            logger.warning(f"[{self.table_name}] Failed to update status to {status}: {e}")

    def _validate_runtime_config(self) -> None:
        """Validate runtime configuration to detect infrastructure drift and security issues.

        Checks:
        1. table_name is in approved whitelist (Security M-001: SQL injection prevention)
        2. LOADER_PARALLELISM env var is set and has a reasonable value
        3. Logs parallelism for operational visibility
        Raises ValueError if table_name is invalid. Warnings if other values seem wrong.
        """
        try:
            assert_safe_table(self.table_name)
        except ValueError as e:
            logger.error(f"[SECURITY] {e}")
            raise

        try:
            loader_parallelism = os.getenv("LOADER_PARALLELISM", "")
            if loader_parallelism:
                try:
                    parallelism_value = int(loader_parallelism)
                    if parallelism_value < 1 or parallelism_value > 32:
                        logger.warning(
                            f"[CONFIG] LOADER_PARALLELISM={parallelism_value} is outside normal range (1-32). "
                            f"Check Terraform task definition (terraform/modules/loaders/main.tf)."
                        )
                    logger.info(f"[CONFIG] LOADER_PARALLELISM={parallelism_value}")
                except ValueError:
                    logger.warning(
                        f"[CONFIG] LOADER_PARALLELISM='{loader_parallelism}' is not a valid integer"
                    )
            else:
                logger.warning(
                    "[CONFIG] LOADER_PARALLELISM not set in environment. "
                    "Using default. Check ECS task environment variables."
                )

            # Log other critical environment variables for diagnostics
            aws_region = os.getenv("AWS_REGION", "not set")
            db_name = os.getenv("DB_NAME", "not set")
            logger.debug(f"[CONFIG] AWS_REGION={aws_region}, DB_NAME={db_name}")
        except Exception as e:
            logger.debug(f"[CONFIG] Runtime validation check failed: {e}")

    def _get_rds_connection_count(self) -> Optional[int]:
        """Get current RDS active connection count from CloudWatch metrics.

        Returns:
            Current active connections or None if unavailable.

        This helps determine if RDS Proxy pool is approaching saturation.
        Pool saturation = active_connections > 80% of max_db_connections (500).
        """
        try:
            import boto3
            from datetime import datetime, timedelta

            cloudwatch = boto3.client("cloudwatch")
            aws_region = os.getenv("AWS_REGION", "us-east-1")

            response = cloudwatch.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName="DatabaseConnections",
                Dimensions=[
                    {"Name": "DBInstanceIdentifier", "Value": "algo-db"}
                ],
                StartTime=datetime.utcnow() - timedelta(minutes=5),
                EndTime=datetime.utcnow(),
                Period=60,
                Statistics=["Average"]
            )

            if response["Datapoints"]:
                # Get the most recent data point
                latest = max(response["Datapoints"], key=lambda x: x["Timestamp"])
                return int(latest["Average"])
        except Exception as e:
            logger.debug(f"Could not fetch RDS connection count: {e}")

        return None

    def _should_reduce_parallelism(self, parallelism: int) -> tuple:
        """Check if RDS connection pool is saturated and reduce parallelism if needed.

        Returns:
            (adjusted_parallelism, was_reduced): boolean tuple indicating if adjustment happened

        Logic:
        - If RDS active connections > 400 (80% of 500 max): reduce parallelism by 50%
        - If RDS active connections > 450 (90% of 500 max): reduce parallelism to 1 (serial)
        - This prevents "too many connections" errors during peak EOD or morning prep loads
        """
        if parallelism <= 1:
            return parallelism, False

        try:
            conn_count = self._get_rds_connection_count()
            if conn_count is None:
                # CloudWatch unavailable, proceed with requested parallelism
                return parallelism, False

            max_db_connections = 500  # RDS max_connections parameter
            saturation_high = max_db_connections * 0.90  # 450
            saturation_medium = max_db_connections * 0.80  # 400

            if conn_count > saturation_high:
                # Extreme saturation: go serial to minimize connection overhead
                logger.warning(
                    f"[{self.table_name}] RDS connection pool saturation HIGH ({conn_count}/{max_db_connections}). "
                    f"Reducing parallelism {parallelism}→1 (serial mode)"
                )
                return 1, True
            elif conn_count > saturation_medium:
                # Moderate saturation: reduce parallelism by 50%
                adjusted = max(1, parallelism // 2)
                if adjusted < parallelism:
                    logger.warning(
                        f"[{self.table_name}] RDS connection pool saturation MEDIUM ({conn_count}/{max_db_connections}). "
                        f"Reducing parallelism {parallelism}→{adjusted}"
                    )
                return adjusted, adjusted < parallelism
        except Exception as e:
            logger.debug(f"Parallelism adjustment check failed: {e}")

        return parallelism, False

    def _check_shutdown_requested(self) -> bool:
        """Check if graceful shutdown was requested."""
        with self._shutdown_lock:
            return self._shutdown_requested

    # ---- Subclass interface ----

    def fetch_incremental(
        self, symbol: str, since: Optional[date]
    ) -> Optional[List[dict]]:
        """Return rows newer than `since` for the given symbol. Override for per-symbol loaders."""
        raise NotImplementedError(
            "Implement fetch_incremental (per-symbol) or fetch_global (market-wide)"
        )

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Return new rows for market-wide data (no symbol dimension). Override for global loaders."""
        return None

    def transform(self, rows: List[dict]) -> List[dict]:
        """Override to apply domain-specific cleaning. Default = identity."""
        return rows

    def watermark_from_rows(self, rows: List[dict]) -> Optional[date]:
        """Derive new watermark from inserted rows. Default = max(watermark_field)."""
        if not rows:
            return None
        values = [
            r.get(self.watermark_field) for r in rows if r.get(self.watermark_field)
        ]
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
            cur.execute(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = %s AND table_schema = 'public'
            )
            """,
                (self.table_name,),
            )

            row = cur.fetchone()
            if not row[0]:
                logger.warning(f"Table {self.table_name} does not exist")
                return

            # Check if a UNIQUE constraint already exists on primary_key columns
            pk_cols = ",".join(self.primary_key)
            cur.execute(
                """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = %s
            AND constraint_type IN ('UNIQUE', 'PRIMARY KEY')
            AND table_schema = 'public'
            """,
                (self.table_name,),
            )

            existing_constraints = [r[0] for r in cur.fetchall()]

            # Check if any constraint covers all our primary_key columns
            for constraint in existing_constraints:
                cur.execute(
                    """
                SELECT column_name
                FROM information_schema.key_column_usage
                WHERE constraint_name = %s AND table_schema = 'public'
                ORDER BY ordinal_position
                """,
                    (constraint,),
                )

                constraint_cols = [r[0] for r in cur.fetchall()]
                if set(constraint_cols) == set(self.primary_key):
                    logger.debug(
                        f"UNIQUE constraint {constraint} already exists on {self.table_name}({pk_cols})"
                    )
                    return

            # Also check unique indexes created via CREATE UNIQUE INDEX — these don't appear
            # in information_schema.table_constraints but are valid for ON CONFLICT clauses.
            cur.execute(
                """
            SELECT indexname, indexdef FROM pg_indexes
            WHERE tablename = %s AND indexdef ILIKE '%%UNIQUE%%'
            """,
                (self.table_name,),
            )
            for idx_name, idx_def in cur.fetchall():
                idx_cols_str = idx_def.split("(", 1)[-1].rstrip(")")
                idx_cols = set(
                    c.strip().strip('"').lower() for c in idx_cols_str.split(",")
                )
                pk_col_set = set(c.lower() for c in self.primary_key)
                if idx_cols == pk_col_set:
                    logger.debug(
                        f"Unique index {idx_name} already covers {self.table_name}({pk_cols})"
                    )
                    return

            # No matching constraint or unique index found � create one
            constraint_name = f"{self.table_name}_{'_'.join(self.primary_key)}_unique"
            try:
                logger.info(
                    f"Creating UNIQUE constraint {constraint_name} on {self.table_name}({pk_cols})"
                )
                col_identifiers = psycopg2.sql.SQL(",").join(
                    [psycopg2.sql.Identifier(col) for col in self.primary_key]
                )
                cur.execute(
                    psycopg2.sql.SQL(
                        "ALTER TABLE {} ADD CONSTRAINT {} UNIQUE ({})"
                    ).format(
                        psycopg2.sql.Identifier(self.table_name),
                        psycopg2.sql.Identifier(constraint_name),
                        col_identifiers,
                    )
                )
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

    def _bulk_insert(
        self,
        rows: List[dict],
        symbol: Optional[str] = None,
        new_watermark: Optional[date] = None,
        watermark_mgr=None,
    ) -> int:
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
        import csv
        import io

        with DatabaseContext("write") as cur:
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
                    self._schema_cols_cache = {r[0] for r in cur.fetchall()}
                existing_cols = self._schema_cols_cache
                all_data_cols = list(rows[0].keys())
                skipped = [c for c in all_data_cols if c not in existing_cols]
                if skipped:
                    logger.warning(
                        "Loader %s: skipping columns not in DB schema: %s",
                        self.table_name,
                        skipped,
                    )
                columns = [c for c in all_data_cols if c in existing_cols]
                if not columns:
                    raise ValueError(f"No valid columns to write for {self.table_name}")
            except Exception as e:
                logger.error(f"Failed to prepare columns for {self.table_name}: {e}")
                raise

            # Use UUID for guaranteed uniqueness across concurrent executions
            # (avoids type name collisions in pg_type when millisecond-level timing aligns)
            unique_id = str(uuid.uuid4()).replace("-", "")[:12]
            staging = f"_stage_{self.table_name}_{unique_id}"

            try:
                cur.execute(
                    psycopg2.sql.SQL(
                        "CREATE UNLOGGED TABLE {} (LIKE {} INCLUDING DEFAULTS)"
                    ).format(
                        psycopg2.sql.Identifier(staging),
                        psycopg2.sql.Identifier(self.table_name),
                    )
                )
            except psycopg2.Error as e:
                if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                    try:
                        cur.execute(
                            psycopg2.sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                                psycopg2.sql.Identifier(staging)
                            )
                        )
                    except psycopg2.Error as drop_err:
                        logger.warning(
                            f"Failed to drop staging table {staging}: {drop_err}"
                        )
                    unique_id = str(uuid.uuid4()).replace("-", "")[:12]
                    staging = f"_stage_{self.table_name}_{unique_id}"
                    cur.execute(
                        psycopg2.sql.SQL(
                            "CREATE UNLOGGED TABLE {} (LIKE {} INCLUDING DEFAULTS)"
                        ).format(
                            psycopg2.sql.Identifier(staging),
                            psycopg2.sql.Identifier(self.table_name),
                        )
                    )
                else:
                    raise

            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
            for row in rows:
                writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
            buf.seek(0)
            col_ids = [psycopg2.sql.Identifier(c) for c in columns]
            cur.copy_expert(
                psycopg2.sql.SQL(
                    "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, NULL '')"
                ).format(
                    psycopg2.sql.Identifier(staging),
                    psycopg2.sql.SQL(",").join(col_ids),
                ),
                buf,
            )

            update_parts = [
                psycopg2.sql.SQL("{} = EXCLUDED.{}").format(
                    psycopg2.sql.Identifier(c), psycopg2.sql.Identifier(c)
                )
                for c in columns
                if c not in self.primary_key
            ]
            if update_parts:
                pk_ids = [psycopg2.sql.Identifier(pk) for pk in self.primary_key]
                on_conflict = psycopg2.sql.SQL(
                    "ON CONFLICT ({}) DO UPDATE SET {}"
                ).format(
                    psycopg2.sql.SQL(",").join(pk_ids),
                    psycopg2.sql.SQL(",").join(update_parts),
                )
            else:
                on_conflict = psycopg2.sql.SQL("ON CONFLICT DO NOTHING")

            cur.execute(
                psycopg2.sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {} {}").format(
                    psycopg2.sql.Identifier(self.table_name),
                    psycopg2.sql.SQL(",").join(col_ids),
                    psycopg2.sql.SQL(",").join(col_ids),
                    psycopg2.sql.Identifier(staging),
                    on_conflict,
                )
            )
            inserted = cur.rowcount

            cur.execute(
                psycopg2.sql.SQL("DROP TABLE {}").format(
                    psycopg2.sql.Identifier(staging)
                )
            )

            if symbol and new_watermark:
                if watermark_mgr:
                    # Use WatermarkManager for atomic DB-backed watermark
                    watermark_mgr.advance_watermark(
                        new_watermark=new_watermark,
                        symbol=symbol,
                        rows_loaded=inserted,
                        in_transaction=True,  # Will commit with rest of transaction
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
            previous_date = datetime.now().date() - timedelta(days=self._backfill_days)
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
        validated_rows = []
        for r in rows:
            if not self._validate_row(r):
                logger.debug(
                    f"Row validation failed: {r.get('symbol', 'unknown')} "
                    f"[{r.get('date', 'unknown')}] — missing required field"
                )
            else:
                validated_rows.append(r)
        rows = validated_rows
        dropped_count = before_quality - len(rows)
        if dropped_count > 0:
            logger.warning(
                f"Quality check: Dropped {dropped_count} row(s) due to validation failure"
            )
        self._stats["rows_quality_dropped"] += dropped_count

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
            chunk = rows[chunk_start : chunk_start + self.chunk_size]
            # Pass watermark only on last chunk to avoid overwriting with partial watermark
            is_final_chunk = chunk_start + self.chunk_size >= len(rows)
            chunk_wm = new_wm if is_final_chunk else None
            inserted += self._bulk_insert(
                chunk, symbol=symbol if is_final_chunk else None, new_watermark=chunk_wm
            )

        if dedup and self.primary_key:
            for row in rows:
                key = ":".join(str(row.get(c, "")) for c in self.primary_key)
                dedup.add(key)

        self._stats["rows_inserted"] += inserted
        return inserted

    def _dedup_filter(self, dedup, rows: List[dict]) -> List[dict]:
        keys = [":".join(str(r.get(c, "")) for c in self.primary_key) for r in rows]
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

    def _check_upstream_completeness(self, expected_symbols: int) -> bool:
        """ISSUE #5 FIX: Check if upstream dependencies have adequate symbol coverage (>95%).

        Loaders in the morning prep chain depend on previous loaders:
        - technical_data_daily depends on price_daily
        - buy_sell_daily depends on technical_data_daily
        - signal_quality_scores depends on buy_sell_daily
        - swing_trader_scores depends on all above

        If upstream data <95% complete, downstream should not proceed (prevents silent data loss).

        Args:
            expected_symbols: Expected number of symbols for this run

        Returns:
            True if upstream complete (>95%), False if incomplete (should abort this load)
        """
        # Define upstream dependencies per table
        upstream_deps = {
            'technical_data_daily': 'price_daily',
            'buy_sell_daily': 'technical_data_daily',
            'signal_quality_scores': 'buy_sell_daily',
            'swing_trader_scores': 'signal_quality_scores',
        }

        upstream_table = upstream_deps.get(self.table_name)
        if not upstream_table:
            # No upstream dependency, proceed normally
            return True

        try:
            with DatabaseContext('read') as cur:
                # Check upstream table completeness via data_loader_status
                cur.execute(
                    "SELECT completion_pct, symbols_loaded, symbol_count FROM data_loader_status "
                    "WHERE table_name = %s AND status IN ('COMPLETED', 'INCOMPLETE')",
                    (upstream_table,)
                )
                result = cur.fetchone()
                if not result:
                    # No upstream status — assume upstream hasn't run yet
                    logger.error(
                        f"[UPSTREAM] {self.table_name} requires {upstream_table}, but {upstream_table} "
                        f"has no status. Aborting to prevent silent data loss."
                    )
                    return False

                completion_pct, symbols_loaded, symbol_count = result
                if completion_pct < 95:
                    logger.critical(
                        f"[UPSTREAM] {self.table_name} depends on {upstream_table}, which is only "
                        f"{completion_pct:.1f}% complete ({symbols_loaded}/{symbol_count} symbols). "
                        f"Aborting to prevent incomplete data from flowing downstream."
                    )
                    # Update our status to FAILED so Phase 1 detects it
                    try:
                        with DatabaseContext('write') as write_cur:
                            write_cur.execute(
                                "UPDATE data_loader_status SET status = %s WHERE table_name = %s",
                                ('FAILED', self.table_name)
                            )
                    except Exception:
                        pass
                    return False

                logger.info(f"[UPSTREAM] {self.table_name} upstream check passed: {upstream_table} "
                           f"{completion_pct:.1f}% complete ({symbols_loaded}/{symbol_count} symbols)")
                return True

        except Exception as e:
            logger.warning(f"[UPSTREAM] Could not check upstream completeness: {e}, proceeding anyway")
            return True  # Don't abort if we can't check

    def run(
        self,
        symbols: Iterable[str],
        parallelism: int = 1,
        backfill_days: Optional[int] = None,
    ) -> dict:
        """Execute load across symbols. Returns stats dict.

        Args:
            symbols: Symbols to load
            parallelism: Number of concurrent workers
            backfill_days: If set, refetch last N days instead of using watermark (for extended history)
        """
        # Distributed lock using DynamoDB (FIXED Issue #31: advisory locks don't work with RDS Proxy pooling)
        # DynamoDB locks are atomic, auto-expiring, and work across network boundaries.
        lock_manager = None
        try:
            from utils.dynamodb_lock_manager import DynamoDBLockManager

            lock_table = os.getenv(
                "LOADER_LOCKS_TABLE",
                f'{os.getenv("PROJECT_NAME", "algo")}-loader-locks-{os.getenv("ENVIRONMENT", "dev")}',
            )
            lock_manager = DynamoDBLockManager(
                table_name=lock_table, lock_duration_seconds=1800
            )
            acquired = lock_manager.acquire(lock_key=self.table_name, timeout_seconds=5)
            if not acquired:
                logger.warning(
                    "[%s] Skipping: another instance already running (DynamoDB lock held)",
                    self.table_name,
                )
                return self._stats
        except Exception as _lock_err:
            logger.warning(
                "[%s] DynamoDB lock check failed (%s) — proceeding without lock (not recommended)",
                self.table_name,
                _lock_err,
            )
            lock_manager = None

        try:
            if backfill_days is not None:
                self._backfill_days = backfill_days

            # Mark loader as RUNNING so Phase 1 knows it's in progress
            self._update_loader_status("RUNNING")

            # Start heartbeat thread to signal loader is alive (for hung task detection)
            self._start_heartbeat()

            # ISSUE #5 FIX: Check upstream completeness before proceeding
            symbols = list(symbols)
            if not self._check_upstream_completeness(len(symbols)):
                # Upstream incomplete — abort this load to prevent silent data loss
                logger.error(f"[{self.table_name}] Aborting due to incomplete upstream data")
                self._update_loader_status("FAILED")
                self._stop_heartbeat()
                return self._stats

            start = time.time()
            mode = (
                f" (backfill {self._backfill_days}d)" if self._backfill_days > 0 else ""
            )

            # Check RDS connection pool health and adjust parallelism if needed
            original_parallelism = parallelism
            parallelism, was_adjusted = self._should_reduce_parallelism(parallelism)

            logger.info(
                "[%s] Starting load: %d symbols (parallelism=%d%s)%s",
                self.table_name,
                len(symbols),
                parallelism,
                " (reduced from " + str(original_parallelism) + ")" if was_adjusted else "",
                mode,
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
                with DatabaseContext("read") as cur:
                    if self.watermark_field:
                        cur.execute(
                            psycopg2.sql.SQL("SELECT COUNT(*), MAX({}) FROM {}").format(
                                psycopg2.sql.Identifier(self.watermark_field),
                                psycopg2.sql.Identifier(self.table_name),
                            )
                        )
                    else:
                        cur.execute(
                            psycopg2.sql.SQL("SELECT COUNT(*), NULL FROM {}").format(
                                psycopg2.sql.Identifier(self.table_name),
                            )
                        )
                    result = cur.fetchone()
                    total_rows = result[0] if result else 0
                    latest_date = result[1] if result else None
                    if hasattr(latest_date, "date"):
                        latest_date = latest_date.date()

                # ISSUE #2 FIX: Track completion percentage and mark INCOMPLETE if <95%
                symbols_expected = len(symbols) if symbols else 1
                symbols_successfully_loaded = self._stats.get("symbols_processed", 0)
                completion_pct = (symbols_successfully_loaded / symbols_expected * 100) if symbols_expected > 0 else 100.0

                # Determine status: INCOMPLETE if coverage <95%, else COMPLETED
                loader_status = 'COMPLETED'
                if completion_pct < 95:
                    loader_status = 'INCOMPLETE'
                    logger.warning(
                        f"[{self.table_name}] Load completed but INCOMPLETE: "
                        f"{symbols_successfully_loaded}/{symbols_expected} symbols ({completion_pct:.1f}%) — "
                        f"Phase 1 will detect this and trigger failsafe retry"
                    )

                with DatabaseContext("write") as cur:
                    # ISSUE #2 FIX: Preserve execution_started timestamp across DELETE+INSERT
                    # Read current execution_started before wiping it out
                    cur.execute(
                        "SELECT execution_started FROM data_loader_status WHERE table_name = %s",
                        (self.table_name,),
                    )
                    existing = cur.fetchone()
                    execution_started = existing[0] if existing and existing[0] else "NOW()"

                    # Use DELETE + INSERT for robustness — avoids ON CONFLICT constraint
                    # dependency (works even if PRIMARY KEY was added after initial creation)
                    cur.execute(
                        "DELETE FROM data_loader_status WHERE table_name = %s",
                        (self.table_name,),
                    )

                    # Include execution_started (preserved) and execution_completed (set now) in INSERT
                    if execution_started == "NOW()":
                        # execution_started was null, set it now
                        cur.execute(
                            "INSERT INTO data_loader_status "
                            "(table_name, row_count, latest_date, last_updated, status, "
                            "completion_pct, symbol_count, symbols_loaded, execution_started, execution_completed) "
                            "VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, NOW(), NOW())",
                            (self.table_name, total_rows, latest_date, loader_status,
                             completion_pct, symbols_expected, symbols_successfully_loaded),
                        )
                    else:
                        # execution_started already exists, preserve it
                        cur.execute(
                            "INSERT INTO data_loader_status "
                            "(table_name, row_count, latest_date, last_updated, status, "
                            "completion_pct, symbol_count, symbols_loaded, execution_started, execution_completed) "
                            "VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, %s, NOW())",
                            (self.table_name, total_rows, latest_date, loader_status,
                             completion_pct, symbols_expected, symbols_successfully_loaded, execution_started),
                        )
            except Exception as e:
                logger.warning(
                    f"Failed to update data_loader_status for {self.table_name}: {e}"
                )

            # ISSUE #7 FIX: Invalidate data_loader_status cache when loader completes
            # Prevents Phase 1 from using stale cache that shows old completion status
            try:
                import boto3
                dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                cache_table_name = os.getenv('CACHE_TABLE', 'algo_phase1_cache')
                cache_table = dynamodb.Table(cache_table_name)

                # Invalidate any cached data_loader_status entries
                run_date = _date.today().isoformat()
                cache_key = f"data_loader_status-{run_date}"
                try:
                    cache_table.delete_item(Key={'cache_key': cache_key})
                    logger.debug(f"[CACHE] Invalidated {cache_key} on {self.table_name} completion")
                except Exception as cache_err:
                    logger.debug(f"[CACHE] Could not invalidate cache: {cache_err}")
            except Exception as cache_setup_err:
                logger.debug(f"[CACHE] Cache invalidation unavailable: {cache_setup_err}")

            # Stop heartbeat thread before returning
            self._stop_heartbeat()

            return self._stats
        finally:
            # Ensure heartbeat stops even on error
            self._stop_heartbeat()
            if lock_manager:
                try:
                    lock_manager.release(lock_key=self.table_name)
                except Exception as e:
                    logger.warning(f"Failed to release DynamoDB lock: {e}")

    def close(self) -> None:
        """No-op. DatabaseContext handles connection cleanup automatically."""
        pass

    def load_global(self) -> int:
        """Execute a market-wide data load using fetch_global(). Returns rows inserted.

        For loaders that handle aggregate/market-wide data (e.g. sentiment surveys,
        economic indicators) rather than per-symbol incremental data.

        Steps:
          1. Read current max(watermark_field) from the table as the 'since' date.
          2. Call fetch_global(since) to retrieve new rows.
          3. Transform, bulk-insert, and update data_loader_status.
          4. Return count of rows inserted.
        """

        lock_manager = None
        try:
            from utils.dynamodb_lock_manager import DynamoDBLockManager

            lock_table = os.getenv(
                "LOADER_LOCKS_TABLE",
                f'{os.getenv("PROJECT_NAME", "algo")}-loader-locks-{os.getenv("ENVIRONMENT", "dev")}',
            )
            lock_manager = DynamoDBLockManager(
                table_name=lock_table, lock_duration_seconds=1800
            )
            acquired = lock_manager.acquire(lock_key=self.table_name, timeout_seconds=5)
            if not acquired:
                logger.warning(
                    "[%s] Skipping global load: another instance already running (DynamoDB lock held)",
                    self.table_name,
                )
                return 0
        except Exception as _lock_err:
            logger.warning(
                "[%s] DynamoDB lock check failed (%s) — proceeding without lock (not recommended)",
                self.table_name,
                _lock_err,
            )
            lock_manager = None

        try:
            # Mark loader as RUNNING so Phase 1 knows it's in progress
            self._update_loader_status("RUNNING")

            start = time.time()
            logger.info("[%s] Starting global load", self.table_name)

            # Get current watermark from DB so fetch_global can do incremental loads
            since = None
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        psycopg2.sql.SQL("SELECT MAX({}) FROM {}").format(
                            psycopg2.sql.Identifier(self.watermark_field),
                            psycopg2.sql.Identifier(self.table_name),
                        )
                    )
                    row = cur.fetchone()
                    since = (
                        self._parse_watermark_date(row[0]) if row and row[0] else None
                    )
            except Exception as e:
                logger.warning(
                    "[%s] Could not read watermark: %s — doing full refresh",
                    self.table_name,
                    e,
                )

            rows = self.fetch_global(since)
            if not rows:
                logger.info("[%s] fetch_global returned no rows", self.table_name)
                return 0

            rows = self.transform(rows)
            inserted = self._bulk_insert(rows)

            duration = round(time.time() - start, 2)
            logger.info(
                "[%s] load_global done: %d rows inserted in %.1fs",
                self.table_name,
                inserted,
                duration,
            )

            # Update data_loader_status
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        psycopg2.sql.SQL("SELECT COUNT(*), MAX({}) FROM {}").format(
                            psycopg2.sql.Identifier(self.watermark_field),
                            psycopg2.sql.Identifier(self.table_name),
                        )
                    )
                    result = cur.fetchone()
                    total_rows = result[0] if result else 0
                    latest_date = result[1] if result else None
                    if hasattr(latest_date, "date"):
                        latest_date = latest_date.date()
                with DatabaseContext("write") as cur:
                    # ISSUE #2 FIX: Preserve execution_started timestamp across DELETE+INSERT
                    cur.execute(
                        "SELECT execution_started FROM data_loader_status WHERE table_name = %s",
                        (self.table_name,),
                    )
                    existing = cur.fetchone()
                    execution_started = existing[0] if existing and existing[0] else "NOW()"

                    cur.execute(
                        "DELETE FROM data_loader_status WHERE table_name = %s",
                        (self.table_name,),
                    )

                    # Include execution_started (preserved) and execution_completed (set now) in INSERT
                    if execution_started == "NOW()":
                        # execution_started was null, set it now
                        cur.execute(
                            "INSERT INTO data_loader_status "
                            "(table_name, row_count, latest_date, last_updated, status, execution_started, execution_completed) "
                            "VALUES (%s, %s, %s, NOW(), %s, NOW(), NOW())",
                            (self.table_name, total_rows, latest_date, 'COMPLETED'),
                        )
                    else:
                        # execution_started already exists, preserve it
                        cur.execute(
                            "INSERT INTO data_loader_status "
                            "(table_name, row_count, latest_date, last_updated, status, execution_started, execution_completed) "
                            "VALUES (%s, %s, %s, NOW(), %s, %s, NOW())",
                            (self.table_name, total_rows, latest_date, 'COMPLETED', execution_started),
                        )
            except Exception as e:
                logger.warning(
                    f"Failed to update data_loader_status for {self.table_name}: {e}"
                )

            return inserted
        finally:
            if lock_manager:
                try:
                    lock_manager.release(lock_key=self.table_name)
                except Exception as e:
                    logger.warning(f"Failed to release DynamoDB lock: {e}")

    def _run_serial(self, symbols: List[str]) -> None:
        for i, symbol in enumerate(symbols, 1):
            if self._check_shutdown_requested():
                logger.warning(
                    f"[{self.table_name}] Graceful shutdown - stopping after {i-1} symbols"
                )
                break

            # Keep connection alive by testing it periodically
            # Long-running loaders (30+ min) need to refresh the connection to avoid idle timeout
            if i % 50 == 0:
                try:
                    with DatabaseContext("read") as cur:
                        cur.execute("SELECT 1")
                except Exception as e:
                    logger.debug(f"Connection health check failed: {e}. Reconnecting.")

            self._safe_load_symbol(symbol)
            if i % 100 == 0:
                logger.info("  Progress: %d/%d", i, len(symbols))

    def _run_parallel(self, symbols: List[str], workers: int) -> None:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=workers) as exe:
            futures = {exe.submit(self._safe_load_symbol, s): s for s in symbols}
            done = 0
            last_health_check = time.time()
            for fut in as_completed(futures):
                if self._check_shutdown_requested():
                    logger.warning(
                        f"[{self.table_name}] Graceful shutdown - cancelling remaining {len(futures)-done} tasks"
                    )
                    for f in futures:
                        f.cancel()
                    break

                done += 1
                # Periodic health check to keep connection pool alive
                now = time.time()
                if now - last_health_check > 120:  # Every 2 minutes
                    try:
                        with DatabaseContext("read") as cur:
                            cur.execute("SELECT 1")
                    except Exception as e:
                        logger.debug(
                            f"Connection health check failed: {e}. Reconnecting."
                        )
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
