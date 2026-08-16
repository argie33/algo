"""Bulk insert operations for data loaders."""

import csv
import io
import logging
import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.sql

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

STAGING_TABLE_UUID_LENGTH = 12


class BulkInsertManager:
    """Manages bulk inserts with staging tables, constraint checking, and schema validation."""

    def __init__(self, table_name: str, primary_key: Sequence[str], chunk_size: int = 10_000):
        self.table_name = table_name
        self.primary_key = primary_key
        self.chunk_size = chunk_size
        self._schema_cols_cache: set[str] | None = None
        self._constraint_checked = False
        self._session_tz_cache: ZoneInfo | None = None

    def _session_timezone(self, cur: Any) -> ZoneInfo:
        """Session timezone Postgres uses to interpret naive `timestamp` values.

        `COPY ... FORMAT CSV` into a `timestamp without time zone` column silently
        DROPS any UTC offset present in the text instead of converting it (unlike a
        normal parameterized INSERT of a tz-aware datetime, which psycopg2 converts
        via this same session timezone before sending). Without this conversion,
        every tz-aware datetime bulk-inserted here would land in the DB shifted by
        the session's UTC offset (5-6h) and later misread as being in the future
        whenever compared against NOW() - reproduced live for stock_scores.updated_at.

        FIXED 2026-08-03: previously called the module-level get_db_timezone() helper,
        which opens its OWN nested `DatabaseContext("read")`. For a global_mode loader
        (OptimalLoader.load_global()), this whole call happens on a shared pooled
        connection reused across nested contexts ("externally managed" - see
        utils/db/context.py) - a nested read-role context still calls conn.rollback()
        on that SHARED connection on exit, which rolls back the CURRENT transaction, not
        just its own statements. Live-reproduced: called between _create_staging_table()
        (uncommitted CREATE UNLOGGED TABLE, same transaction) and copy_expert() - the
        nested rollback silently wiped out the staging table before COPY ran, crashing
        with "relation ... does not exist" on the very first bulk_insert() of a fresh
        process (only reproduces once per process - get_db_timezone()'s own module-level
        cache masks it on every later call). Fixed by using the cursor this method
        already receives directly instead of opening a second nested context.
        """
        if self._session_tz_cache is None:
            cur.execute("SHOW timezone")
            result = cur.fetchone()
            if not result:
                raise RuntimeError("Failed to retrieve database timezone - SHOW timezone returned no rows")
            self._session_tz_cache = ZoneInfo(result[0])
        return self._session_tz_cache

    def _create_staging_table(self, cur: Any) -> str:
        """Create staging table with unique UUID, retrying if conflict exists.

        Returns: Name of created staging table
        """
        unique_id = str(uuid.uuid4()).replace("-", "")[:STAGING_TABLE_UUID_LENGTH]
        staging = f"_stage_{self.table_name}_{unique_id}"

        try:
            cur.execute(
                psycopg2.sql.SQL("CREATE UNLOGGED TABLE {} (LIKE {} INCLUDING DEFAULTS)").format(
                    psycopg2.sql.Identifier(staging),
                    psycopg2.sql.Identifier(self.table_name),
                )
            )
            return staging
        except psycopg2.ProgrammingError as e:
            if e.pgcode == "42P07":  # relation already exists
                try:
                    cur.execute(
                        psycopg2.sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(psycopg2.sql.Identifier(staging))
                    )
                except psycopg2.Error as drop_err:
                    logger.warning(f"Failed to drop staging table {staging}: {drop_err}")
                # Retry with new UUID
                return self._create_staging_table(cur)
            raise

    def bulk_insert(  # noqa: C901
        self,
        rows: list[dict[str, Any]],
        symbol: str | None = None,
        new_watermark: date | None = None,
        watermark_mgr: Any = None,
    ) -> int:
        """Bulk insert rows and atomically update watermark if provided.

        Returns: Number of rows inserted.
        """
        if not rows:
            return 0

        with DatabaseContext("write") as cur:
            self._ensure_unique_constraint(cur)

            # Filter to columns that exist in target table
            if self._schema_cols_cache is None:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (self.table_name,),
                )
                self._schema_cols_cache = {r[0] for r in cur.fetchall()}
            existing_cols = self._schema_cols_cache
            if not rows:
                raise ValueError(f"No data rows provided to insert into {self.table_name}")
            # Union of keys across ALL rows, not just rows[0] - a batch mixing rows with
            # different key sets (e.g. a symbol's oldest fiscal year lacking a field that
            # its later years have, common with historical XBRL data where tagging
            # completeness improved over time) previously took its column list from
            # rows[0] alone, silently dropping any column absent from that one row for
            # the WHOLE batch - including rows that had real data for it. Order is
            # preserved (first-seen order across rows) for a deterministic column list.
            all_data_cols: list[str] = []
            seen_cols: set[str] = set()
            for row in rows:
                for k in row.keys():
                    if k not in seen_cols:
                        seen_cols.add(k)
                        all_data_cols.append(k)
            skipped = [c for c in all_data_cols if c not in existing_cols]
            if skipped:
                # GOVERNANCE MARKER DETECTION: a loader can correctly compute a
                # data_unavailable/reason-style governance marker and have it silently
                # vanish right here before ever reaching the DB - found 4 independent times
                # in one audit session (price_daily, quarterly statement tables,
                # signal_quality_scores, market_sentiment; see steering/DATA_LOADERS.md).
                # Each was invisible until someone happened to compare a loader's insert
                # dict against information_schema.columns by hand. Escalate these specific
                # names to ERROR (loggers.warning is the routine "missing upstream data"
                # bar per GOVERNANCE.md #5 - this is categorically worse, it's a bug, not
                # missing data) so the next instance shows up in log-based alerting instead
                # of waiting for the next manual audit. Not raised: schema drift is common
                # enough (renamed/added columns, hand-maintained schema_cols frozensets)
                # that a hard failure here would risk halting production loaders on a
                # column mismatch this function can't distinguish from an intentionally
                # optional/internal field.
                marker_like = [
                    c
                    for c in skipped
                    if c in ("data_unavailable", "reason", "reason_type", "data_completeness", "unavailable_components")
                    or c.endswith(("_unavailable", "_data_unavailable", "_unavailable_reason"))
                ]
                if marker_like:
                    raise RuntimeError(
                        f"GOVERNANCE VIOLATION: Loader {self.table_name}: governance marker columns {marker_like} "
                        f"do not exist on the target table. Cannot record data_unavailable flags for integrity tracking. "
                        f"Add these columns via migration (see steering/DATA_LOADERS.md for the pattern). "
                        f"Failing instead of silently dropping audit trail."
                    )
                non_marker = [c for c in skipped if c not in marker_like]
                if non_marker:
                    logger.warning(
                        "Loader %s: skipping columns not in DB schema: %s",
                        self.table_name,
                        non_marker,
                    )
            columns = [c for c in all_data_cols if c in existing_cols]
            if not columns:
                raise ValueError(f"No valid columns to write for {self.table_name}")

            staging = self._create_staging_table(cur)

            # Write CSV buffer
            session_tz = self._session_timezone(cur)
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
            for row in rows:
                normalized: dict[str, Any] = {}
                for k, v in row.items():
                    if isinstance(v, datetime) and v.tzinfo is not None:
                        # Convert to naive session-local wall-clock time - the same
                        # value a parameterized (non-COPY) insert would produce -
                        # since COPY/CSV would otherwise silently drop the offset.
                        v = v.astimezone(session_tz).replace(tzinfo=None)
                    normalized[k] = "" if v is None else v
                writer.writerow(normalized)
            buf.seek(0)

            # COPY from buffer
            col_ids = [psycopg2.sql.Identifier(c) for c in columns]
            cur.copy_expert(
                psycopg2.sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV, FORCE_NULL ({}))").format(
                    psycopg2.sql.Identifier(staging),
                    psycopg2.sql.SQL(",").join(col_ids),
                    psycopg2.sql.SQL(",").join(col_ids),
                ),
                buf,
            )

            # Build ON CONFLICT clause
            update_parts = [
                psycopg2.sql.SQL("{} = EXCLUDED.{}").format(psycopg2.sql.Identifier(c), psycopg2.sql.Identifier(c))
                for c in columns
                if c not in self.primary_key
            ]
            # ROOT-CAUSE FIX 2026-08-16: `updated_at` has DEFAULT now() in every table's
            # schema, but that default only fires on a fresh INSERT. Since loaders never
            # put `updated_at` in their row dicts, it was never in `columns`, so it was
            # never in this SET clause either - on the ON CONFLICT DO UPDATE path (i.e.
            # every re-run against a symbol the table already has) the column just kept
            # its original insert-time value forever. Live-confirmed on company_info_sec:
            # a 2026-08-16 run wrote today's `filing_date` to existing rows while
            # `updated_at` stayed frozen at 2026-07-22. This silently breaks two
            # consumers that treat updated_at as "last touched": the local scheduler's
            # stall watchdog (which uses row-count/updated_at movement as its liveness
            # signal for a loader whose own completion_pct only updates at the very end -
            # see _monitor_loader_progress) and monitor_data_staleness.py's freshness
            # buckets. Stamp it explicitly with NOW() on every update, independent of
            # whatever the loader did or didn't include.
            if "updated_at" in existing_cols and "updated_at" not in columns:
                update_parts.append(psycopg2.sql.SQL("updated_at = NOW()"))
            if update_parts:
                pk_ids = [psycopg2.sql.Identifier(pk) for pk in self.primary_key]
                on_conflict = psycopg2.sql.SQL("ON CONFLICT ({}) DO UPDATE SET {}").format(
                    psycopg2.sql.SQL(",").join(pk_ids),
                    psycopg2.sql.SQL(",").join(update_parts),
                )
            else:
                on_conflict = psycopg2.sql.SQL("ON CONFLICT DO NOTHING")

            # INSERT with ON CONFLICT
            cur.execute(
                psycopg2.sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {} {}").format(
                    psycopg2.sql.Identifier(self.table_name),
                    psycopg2.sql.SQL(",").join(col_ids),
                    psycopg2.sql.SQL(",").join(col_ids),
                    psycopg2.sql.Identifier(staging),
                    on_conflict,
                )
            )
            inserted = cast(int, cur.rowcount)

            cur.execute(psycopg2.sql.SQL("DROP TABLE {}").format(psycopg2.sql.Identifier(staging)))

        # CRITICAL FIX (Session 351): Validate inserted row count matches expected
        # Previously, only 4,890/8,905 rows persisted due to partial bulk insert,
        # but loader reported success. Now we verify data integrity before updating watermark.
        if not rows:
            return 0

        expected_rows = len(rows)
        if inserted < expected_rows:
            # Partial insert detected - this is a critical data integrity issue
            loss_pct = ((expected_rows - inserted) / expected_rows) * 100
            error_msg = (
                f"CRITICAL DATA LOSS: {self.table_name} bulk insert lost {expected_rows - inserted}/{expected_rows} rows ({loss_pct:.1f}%). "
                f"Attempted: {expected_rows}, Persisted: {inserted}. "
                f"This indicates database transaction failure, connection pool exhaustion, or timeout during bulk insert. "
                f"Failing hard to prevent silent data corruption and forcing retry at orchestration level."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        # CRITICAL FIX: Only advance watermark if rows were actually loaded
        # On weekends/holidays, loaders return zero rows. If we advance watermark anyway,
        # next run will start at Monday's date and skip the entire weekend (data never loaded)
        # See: BLOCKER #4 from comprehensive steering audit (watermark skips weekends forever)
        if inserted == 0:
            logger.info(
                f"[WATERMARK] Zero rows loaded for {symbol} on {new_watermark}. "
                f"Watermark NOT advanced - will retry this date on next load to catch any missing data."
            )
        elif symbol and new_watermark and watermark_mgr:
            try:
                from utils.data.watermark import WatermarkManager

                if isinstance(watermark_mgr, WatermarkManager):
                    success = watermark_mgr.advance_watermark(
                        new_watermark=new_watermark,
                        symbol=symbol,
                        rows_loaded=inserted,
                        in_transaction=False,
                    )
                    if not success:
                        raise RuntimeError(
                            f"Watermark advance returned False for {self.table_name}/{symbol}. "
                            f"Data was inserted but watermark did not advance, causing infinite re-loading."
                        )
                elif hasattr(watermark_mgr, "set"):
                    watermark_mgr.set(symbol, new_watermark, inserted)
                else:
                    raise RuntimeError(
                        f"watermark_mgr is neither Watermark nor has set() method. Type: {type(watermark_mgr).__name__}"
                    )
            except Exception as e:
                raise RuntimeError(
                    f"CRITICAL: Failed to advance watermark for {self.table_name}/{symbol} after inserting {inserted} rows: {e}. "
                    f"Data is in database but loader cannot track progress. Manual watermark reset required."
                ) from e

        return inserted

    def _ensure_unique_constraint(self, cur: Any) -> None:
        """Ensure primary_key columns have a UNIQUE constraint."""
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
            if row is None or len(row) < 1 or not row[0]:
                logger.warning(f"Table {self.table_name} does not exist")
                return

            # Check for existing UNIQUE constraint
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

            # Check if any constraint covers all primary_key columns
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
                    logger.debug(f"UNIQUE constraint {constraint} already exists on {self.table_name}({pk_cols})")
                    return

            # Check unique indexes
            cur.execute(
                """
            SELECT indexname, indexdef FROM pg_indexes
            WHERE tablename = %s AND indexdef ILIKE '%%UNIQUE%%'
            """,
                (self.table_name,),
            )
            for idx_name, idx_def in cur.fetchall():
                idx_cols_str = idx_def.split("(", 1)[-1].rstrip(")")
                idx_cols = {c.strip().strip('"').lower() for c in idx_cols_str.split(",")}
                pk_col_set = {c.lower() for c in self.primary_key}
                if idx_cols == pk_col_set:
                    logger.debug(f"Unique index {idx_name} already covers {self.table_name}({pk_cols})")
                    return

            # Create constraint if none exists
            constraint_name = f"{self.table_name}_{'_'.join(self.primary_key)}_unique"
            try:
                logger.info(f"Creating UNIQUE constraint {constraint_name} on {self.table_name}({pk_cols})")
                col_identifiers = psycopg2.sql.SQL(",").join([psycopg2.sql.Identifier(col) for col in self.primary_key])
                cur.execute(
                    psycopg2.sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} UNIQUE ({})").format(
                        psycopg2.sql.Identifier(self.table_name),
                        psycopg2.sql.Identifier(constraint_name),
                        col_identifiers,
                    )
                )
            except psycopg2.IntegrityError as e:
                logger.warning(f"Cannot create constraint (duplicates exist): {e}")
            except psycopg2.ProgrammingError as e:
                if e.pgcode == "42710":  # object already exists (PostgreSQL error code)
                    logger.debug(f"Constraint already exists: {e}")
                else:
                    logger.warning(f"Cannot create constraint: {e}")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Error checking/creating constraint: {e}")
