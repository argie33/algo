"""RDS schema management and migration handling for Lambda.

Ensures critical database migrations are applied on Lambda cold start.
This is a safety mechanism to handle migrations that should be applied
before the API can safely execute queries.
"""

import logging

logger = logging.getLogger(__name__)

# Critical migrations that must be applied for the API to function
CRITICAL_MIGRATIONS = [
    (
        "data_unavailable_columns",
        [
            """ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE""",
            """ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE""",
            """ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE""",
            """ALTER TABLE positioning_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE""",
            """ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE""",
        ],
    ),
]


def apply_critical_migrations() -> tuple[bool, str]:
    """Apply critical database migrations on Lambda cold start.

    This ensures that required columns and schema changes are present
    before any Lambda code attempts to query the database.

    Returns:
        (success: bool, message: str)
    """
    try:
        from api_utils.database_context import DatabaseContext

        applied_count = 0
        failed_migrations = []

        for migration_name, sql_statements in CRITICAL_MIGRATIONS:
            try:
                with DatabaseContext("write") as cur:
                    for stmt in sql_statements:
                        cur.execute(stmt)
                    applied_count += 1
                    logger.info(f"[SCHEMA] Applied migration: {migration_name}")
            except Exception as e:
                error_msg = f"Migration {migration_name} failed: {e}"
                logger.error(f"[SCHEMA] {error_msg}")
                failed_migrations.append(error_msg)

        if failed_migrations:
            msg = f"Partial migration success ({applied_count} applied, {len(failed_migrations)} failed): {'; '.join(failed_migrations)}"
            logger.warning(f"[SCHEMA] {msg}")
            return False, msg

        msg = f"All {applied_count} critical migrations applied successfully"
        logger.info(f"[SCHEMA] {msg}")
        return True, msg

    except Exception as e:
        error_msg = f"Failed to apply critical migrations: {e}"
        logger.error(f"[SCHEMA] {error_msg}")
        return False, error_msg
