"""Auto-healing schema validator - creates missing columns if needed.

This module provides a defensive mechanism for loaders to ensure their target
tables have all required columns. If columns are missing (e.g., due to incomplete
migrations), they are created automatically on first loader run.

This prevents silent data loss from BulkInsertManager column-skipping and enables
graceful deployment when migrations haven't been fully applied to all environments.
"""

import logging
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)


def ensure_columns_exist(
    cur: Any, table_name: str, required_columns: dict[str, str]
) -> tuple[bool, list[str]]:
    """Ensure all required columns exist in table, creating missing ones.

    Args:
        cur: Database cursor
        table_name: Target table name
        required_columns: Dict of {column_name: data_type} to ensure exist

    Returns:
        Tuple of (all_exist, created_columns)
        - all_exist: True if all columns exist (either already or just created)
        - created_columns: List of column names that were just created

    Raises:
        psycopg2.Error: On database operation failure
    """
    # Get existing columns
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (table_name,),
    )
    existing = {row[0] for row in cur.fetchall()}

    created = []
    missing = {col: dtype for col, dtype in required_columns.items() if col not in existing}

    if not missing:
        logger.info(f"[SCHEMA_HEALER] {table_name}: All {len(required_columns)} required columns exist")
        return True, []

    logger.warning(
        f"[SCHEMA_HEALER] {table_name}: {len(missing)}/{len(required_columns)} required columns missing. "
        f"Auto-creating: {list(missing.keys())}"
    )

    for col_name, col_type in missing.items():
        try:
            sql = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
            logger.info(f"[SCHEMA_HEALER] Creating {table_name}.{col_name} ({col_type})")
            cur.execute(sql)
            created.append(col_name)
        except psycopg2.Error as e:
            logger.error(f"[SCHEMA_HEALER] Failed to create {table_name}.{col_name}: {e}")
            raise RuntimeError(
                f"[SCHEMA_HEALER] Failed to auto-create schema for {table_name}.{col_name}: {e}"
            ) from e

    logger.warning(f"[SCHEMA_HEALER] {table_name}: Created {len(created)} columns. Loader will proceed.")
    return True, created
