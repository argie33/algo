"""Bulk insert operations for data loaders."""

import csv
import io
import logging
import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any, cast

import psycopg2
import psycopg2.sql

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class BulkInsertManager:
    """Manages bulk inserts with staging tables, constraint checking, and schema validation."""

    def __init__(self, table_name: str, primary_key: Sequence[str], chunk_size: int = 10_000):
        self.table_name = table_name
        self.primary_key = primary_key
        self.chunk_size = chunk_size
        self._schema_cols_cache: set[str] | None = None
        self._constraint_checked = False

    def bulk_insert(
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

            # Use UUID for uniqueness across concurrent executions
            unique_id = str(uuid.uuid4()).replace("-", "")[:12]
            staging = f"_stage_{self.table_name}_{unique_id}"

            try:
                cur.execute(
                    psycopg2.sql.SQL("CREATE UNLOGGED TABLE {} (LIKE {} INCLUDING DEFAULTS)").format(
                        psycopg2.sql.Identifier(staging),
                        psycopg2.sql.Identifier(self.table_name),
                    )
                )
            except psycopg2.Error as e:
                if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                    try:
                        cur.execute(
                            psycopg2.sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(psycopg2.sql.Identifier(staging))
                        )
                    except psycopg2.Error as drop_err:
                        logger.warning(f"Failed to drop staging table {staging}: {drop_err}")
                    unique_id = str(uuid.uuid4()).replace("-", "")[:12]
                    staging = f"_stage_{self.table_name}_{unique_id}"
                    cur.execute(
                        psycopg2.sql.SQL("CREATE UNLOGGED TABLE {} (LIKE {} INCLUDING DEFAULTS)").format(
                            psycopg2.sql.Identifier(staging),
                            psycopg2.sql.Identifier(self.table_name),
                        )
                    )
                else:
                    raise

            # Write CSV buffer
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
            for row in rows:
                writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
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

            # Update watermark if provided
            if symbol and new_watermark and watermark_mgr:
                watermark_mgr.advance_watermark(
                    new_watermark=new_watermark,
                    symbol=symbol,
                    rows_loaded=inserted,
                    in_transaction=True,
                )

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
            if not row[0]:
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
                if "already exists" in str(e):
                    logger.debug(f"Constraint already exists: {e}")
                else:
                    logger.warning(f"Cannot create constraint: {e}")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Error checking/creating constraint: {e}")
