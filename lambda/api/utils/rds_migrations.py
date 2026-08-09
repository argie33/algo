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
    # Migration: downside volatility metrics (2026-07-30)
    (
        "stability_metrics.downside_volatility_30d",
        "SELECT 1 FROM information_schema.columns WHERE table_name='stability_metrics' AND column_name='downside_volatility_30d'",
        "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS downside_volatility_30d NUMERIC(10, 4)",
        "Add 30d downside volatility to stability_metrics",
    ),
    (
        "stability_metrics.downside_volatility_60d",
        "SELECT 1 FROM information_schema.columns WHERE table_name='stability_metrics' AND column_name='downside_volatility_60d'",
        "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS downside_volatility_60d NUMERIC(10, 4)",
        "Add 60d downside volatility to stability_metrics",
    ),
    (
        "stability_metrics.downside_volatility_252d",
        "SELECT 1 FROM information_schema.columns WHERE table_name='stability_metrics' AND column_name='downside_volatility_252d'",
        "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS downside_volatility_252d NUMERIC(10, 4)",
        "Add 252d downside volatility to stability_metrics",
    ),
    (
        "stability_metrics.downside_volatility_30d_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='stability_metrics' AND column_name='downside_volatility_30d_unavailable_reason'",
        "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS downside_volatility_30d_unavailable_reason VARCHAR(255)",
        "Add 30d downside volatility unavailable reason to stability_metrics",
    ),
    (
        "stability_metrics.downside_volatility_60d_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='stability_metrics' AND column_name='downside_volatility_60d_unavailable_reason'",
        "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS downside_volatility_60d_unavailable_reason VARCHAR(255)",
        "Add 60d downside volatility unavailable reason to stability_metrics",
    ),
    (
        "stability_metrics.downside_volatility_252d_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='stability_metrics' AND column_name='downside_volatility_252d_unavailable_reason'",
        "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS downside_volatility_252d_unavailable_reason VARCHAR(255)",
        "Add 252d downside volatility unavailable reason to stability_metrics",
    ),
    # Migration: quarterly metrics (2026-08-09)
    (
        "growth_metrics.consecutive_positive_quarters",
        "SELECT 1 FROM information_schema.columns WHERE table_name='growth_metrics' AND column_name='consecutive_positive_quarters'",
        "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS consecutive_positive_quarters INTEGER",
        "Add consecutive_positive_quarters to growth_metrics",
    ),
    (
        "growth_metrics.earnings_growth_4q_avg",
        "SELECT 1 FROM information_schema.columns WHERE table_name='growth_metrics' AND column_name='earnings_growth_4q_avg'",
        "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS earnings_growth_4q_avg NUMERIC(10, 2)",
        "Add earnings_growth_4q_avg to growth_metrics",
    ),
    (
        "growth_metrics.quarterly_growth_momentum",
        "SELECT 1 FROM information_schema.columns WHERE table_name='growth_metrics' AND column_name='quarterly_growth_momentum'",
        "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS quarterly_growth_momentum NUMERIC(10, 2)",
        "Add quarterly_growth_momentum to growth_metrics",
    ),
    (
        "growth_metrics.eps_growth_stability",
        "SELECT 1 FROM information_schema.columns WHERE table_name='growth_metrics' AND column_name='eps_growth_stability'",
        "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS eps_growth_stability NUMERIC(10, 2)",
        "Add eps_growth_stability to growth_metrics",
    ),
    (
        "quality_metrics.consecutive_positive_quarters",
        "SELECT 1 FROM information_schema.columns WHERE table_name='quality_metrics' AND column_name='consecutive_positive_quarters'",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS consecutive_positive_quarters INTEGER",
        "Add consecutive_positive_quarters to quality_metrics",
    ),
    (
        "quality_metrics.earnings_growth_4q_avg",
        "SELECT 1 FROM information_schema.columns WHERE table_name='quality_metrics' AND column_name='earnings_growth_4q_avg'",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS earnings_growth_4q_avg NUMERIC(10, 2)",
        "Add earnings_growth_4q_avg to quality_metrics",
    ),
    (
        "quality_metrics.eps_growth_stability",
        "SELECT 1 FROM information_schema.columns WHERE table_name='quality_metrics' AND column_name='eps_growth_stability'",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS eps_growth_stability NUMERIC(10, 2)",
        "Add eps_growth_stability to quality_metrics",
    ),
    # Migration: quarterly unavailable reason fields
    (
        "growth_metrics.consecutive_positive_quarters_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='growth_metrics' AND column_name='consecutive_positive_quarters_unavailable_reason'",
        "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS consecutive_positive_quarters_unavailable_reason VARCHAR(255)",
        "Add consecutive_positive_quarters unavailable reason to growth_metrics",
    ),
    (
        "growth_metrics.earnings_growth_4q_avg_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='growth_metrics' AND column_name='earnings_growth_4q_avg_unavailable_reason'",
        "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS earnings_growth_4q_avg_unavailable_reason VARCHAR(255)",
        "Add earnings_growth_4q_avg unavailable reason to growth_metrics",
    ),
    (
        "growth_metrics.eps_growth_stability_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='growth_metrics' AND column_name='eps_growth_stability_unavailable_reason'",
        "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS eps_growth_stability_unavailable_reason VARCHAR(255)",
        "Add eps_growth_stability unavailable reason to growth_metrics",
    ),
    (
        "quality_metrics.consecutive_positive_quarters_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='quality_metrics' AND column_name='consecutive_positive_quarters_unavailable_reason'",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS consecutive_positive_quarters_unavailable_reason VARCHAR(255)",
        "Add consecutive_positive_quarters unavailable reason to quality_metrics",
    ),
    (
        "quality_metrics.earnings_growth_4q_avg_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='quality_metrics' AND column_name='earnings_growth_4q_avg_unavailable_reason'",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS earnings_growth_4q_avg_unavailable_reason VARCHAR(255)",
        "Add earnings_growth_4q_avg unavailable reason to quality_metrics",
    ),
    (
        "quality_metrics.eps_growth_stability_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='quality_metrics' AND column_name='eps_growth_stability_unavailable_reason'",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS eps_growth_stability_unavailable_reason VARCHAR(255)",
        "Add eps_growth_stability unavailable reason to quality_metrics",
    ),
]


def check_migration_needed(conn: Any, check_query: str) -> bool:
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
