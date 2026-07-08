"""RDS Database Migration Handler - Auto-apply migrations on Lambda cold-start."""

import logging
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)

# All migrations to apply, in order.
# Each entry: (name, check_query, migration_sql, description)
MIGRATIONS = [
    # Migration: data_unavailable on metric tables
    (
        "quality_metrics.data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='quality_metrics' AND column_name='data_unavailable'",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
        "Add data_unavailable flag to quality_metrics",
    ),
    (
        "growth_metrics.data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='growth_metrics' AND column_name='data_unavailable'",
        "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
        "Add data_unavailable flag to growth_metrics",
    ),
    (
        "value_metrics.data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='value_metrics' AND column_name='data_unavailable'",
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
        "Add data_unavailable flag to value_metrics",
    ),
    (
        "positioning_metrics.data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='positioning_metrics' AND column_name='data_unavailable'",
        "ALTER TABLE positioning_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
        "Add data_unavailable flag to positioning_metrics",
    ),
    (
        "stability_metrics.data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='stability_metrics' AND column_name='data_unavailable'",
        "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
        "Add data_unavailable flag to stability_metrics",
    ),
    # Migration: reason on metric tables
    (
        "quality_metrics.reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='quality_metrics' AND column_name='reason'",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS reason VARCHAR(500)",
        "Add reason field to quality_metrics",
    ),
    (
        "stability_metrics.reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='stability_metrics' AND column_name='reason'",
        "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS reason VARCHAR(500)",
        "Add reason field to stability_metrics",
    ),
]


def check_migration_needed(conn: Any, check_query: str) -> bool:
    """Check if a migration has already been applied."""
    try:
        with conn.cursor() as cur:
            cur.execute(check_query)
            result = cur.fetchone()
            return result is not None
    except psycopg2.Error:
        return False


def apply_migration(conn: Any, migration_sql: str) -> bool:
    """Apply a single migration."""
    try:
        with conn.cursor() as cur:
            cur.execute(migration_sql)
        conn.commit()
        return True
    except psycopg2.Error as e:
        conn.rollback()
        logger.warning(f"Migration failed: {e}")
        return False


def auto_apply_migrations(conn: Any) -> dict[str, Any]:
    """Auto-apply all pending migrations.

    Args:
        conn: Database connection object

    Returns:
        Dict with migration results: {name: {'applied': bool, 'description': str}}
    """
    results = {}

    for name, check_query, migration_sql, description in MIGRATIONS:
        try:
            # Check if already applied
            if check_migration_needed(conn, check_query):
                results[name] = {
                    "applied": False,
                    "reason": "already_exists",
                    "description": description,
                }
                logger.debug(f"[MIGRATION] {name}: Already applied")
                continue

            # Apply migration
            if apply_migration(conn, migration_sql):
                results[name] = {
                    "applied": True,
                    "description": description,
                }
                logger.info(f"[MIGRATION] {name}: Applied successfully")
            else:
                results[name] = {
                    "applied": False,
                    "reason": "execution_failed",
                    "description": description,
                }
                logger.warning(f"[MIGRATION] {name}: Failed to apply")
        except Exception as e:
            results[name] = {
                "applied": False,
                "reason": str(e),
                "description": description,
            }
            logger.error(f"[MIGRATION] {name}: Exception: {e}")

    return results
