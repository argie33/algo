#!/usr/bin/env python3
"""
AUTHORITATIVE Database Schema Initialization

Schema is loaded from: terraform/modules/database/init.sql (Single Source of Truth)

All environments (local, AWS) use the same schema file - no duplication.
Local dev schema = AWS schema (prevents "works locally but not in AWS" bugs).

To maintain schema:
1. Edit terraform/modules/database/init.sql
2. This file loads it automatically
3. All loaders use this centralized schema
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.credential_helper import get_db_config
import psycopg2
import logging

logger = logging.getLogger(__name__)
DB_CONFIG = get_db_config()


def _load_schema_from_sql():
    """Load schema from authoritative Terraform SQL file (single source)."""
    schema_path = Path(__file__).parent.parent / 'terraform' / 'modules' / 'database' / 'init.sql'
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    return schema_path.read_text(encoding='utf-8', errors='ignore')


def _run_migrations(conn, cur):
    """Apply schema migrations for existing databases (idempotent ADD COLUMN IF NOT EXISTS)."""
    migrations = [
        "ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS event_id VARCHAR(100)",
        "ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS event_date DATE",
        "ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS event_time TIME",
        "ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS category VARCHAR(100)",
        "ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS forecast_value DECIMAL(12, 4)",
        "ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS actual_value DECIMAL(12, 4)",
        "ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS previous_value DECIMAL(12, 4)",
        "ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "UPDATE economic_calendar SET event_date = date WHERE event_date IS NULL AND date IS NOT NULL",
        "UPDATE economic_calendar SET forecast_value = forecast WHERE forecast_value IS NULL AND forecast IS NOT NULL",
        "UPDATE economic_calendar SET actual_value = actual WHERE actual_value IS NULL AND actual IS NOT NULL",
        "UPDATE economic_calendar SET previous_value = previous WHERE previous_value IS NULL AND previous IS NOT NULL",
    ]

    succeeded = 0
    for stmt in migrations:
        try:
            cur.execute(stmt)
            succeeded += 1
        except Exception:
            pass

    conn.commit()
    if succeeded:
        logger.info(f"  ✓ Applied {succeeded} schema migrations")


def _init_timescaledb(conn, cur):
    """Initialize TimescaleDB extension for 10-100x faster time-series queries."""
    try:
        logger.info("  [1/4] Enabling TimescaleDB extension...")
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb WITH SCHEMA public CASCADE")
            logger.info("    ✓ TimescaleDB extension enabled")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("    ✓ TimescaleDB extension already enabled")
            else:
                logger.info(f"    ⚠ {str(e)[:80]}")

        logger.info("  [2/4] Converting price_daily to hypertable...")
        try:
            cur.execute("SELECT EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'price_daily')")
            is_hypertable = cur.fetchone()[0]
            if is_hypertable:
                logger.info("    ✓ price_daily already a hypertable")
            else:
                cur.execute("SELECT create_hypertable('price_daily', 'date', if_not_exists => TRUE, chunk_time_interval => INTERVAL '3 months')")
                logger.info("    ✓ price_daily converted to hypertable")
        except Exception as e:
            logger.info(f"    ⚠ {str(e)[:80]}")

        logger.info("  [3/4] Enabling compression...")
        try:
            cur.execute("""ALTER TABLE price_daily SET (
                timescaledb.compress = true,
                timescaledb.compress_segmentby = 'symbol',
                timescaledb.compress_orderby = 'date DESC'
            )""")
            cur.execute("SELECT add_compression_policy('price_daily', INTERVAL '30 days', if_not_exists => TRUE)")
            logger.info("    ✓ Compression enabled")
        except Exception as e:
            logger.info(f"    ⚠ {str(e)[:80]}")

        logger.info("  [4/4] Creating continuous aggregate...")
        try:
            cur.execute("""CREATE MATERIALIZED VIEW IF NOT EXISTS price_daily_agg WITH (
                timescaledb.continuous, timescaledb.materialized_only = false
            ) AS
            SELECT time_bucket('1 day', date) as day, symbol,
                   FIRST(open, date) as open, MAX(high) as high,
                   MIN(low) as low, LAST(close, date) as close, SUM(volume) as volume
            FROM price_daily GROUP BY day, symbol WITH DATA""")
            cur.execute("""SELECT add_continuous_aggregate_policy(
                'price_daily_agg', start_offset => INTERVAL '7 days',
                end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '1 hour',
                if_not_exists => TRUE)""")
            logger.info("    ✓ Continuous aggregate created")
        except Exception as e:
            logger.info(f"    ⚠ {str(e)[:80]}")

        conn.commit()
        logger.info()
        logger.info("✓ TimescaleDB initialization complete!")
        logger.info()
    except Exception as e:
        logger.info(f"ERROR in TimescaleDB init: {e}")


def init_database():
    """Initialize database schema from authoritative Terraform SQL file."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        logger.info("╔════════════════════════════════════════════════════════╗")
        logger.info("║  Initializing Database Schema (AUTHORITATIVE)         ║")
        logger.info("║  Source: terraform/modules/database/init.sql         ║")
        logger.info("╚════════════════════════════════════════════════════════╝")
        logger.info()

        schema = _load_schema_from_sql()
        statements = [s.strip() for s in schema.split(';') if s.strip()]

        succeeded = 0
        failed = 0

        for i, stmt in enumerate(statements, 1):
            try:
                cur.execute(stmt)
                logger.info(f"  ✓ [{i:3d}/{len(statements)}]")
                succeeded += 1
            except Exception as e:
                logger.info(f"  ✗ [{i:3d}/{len(statements)}] {str(e)[:50]}")
                failed += 1

        conn.commit()
        logger.info()
        logger.info(f"✓ Schema initialization complete!")
        logger.info(f"  Succeeded: {succeeded}")
        logger.info(f"  Failed: {failed}")
        logger.info()

        _run_migrations(conn, cur)

        logger.info("╔════════════════════════════════════════════════════════╗")
        logger.info("║  Initializing TimescaleDB for Time-Series (10-100x)   ║")
        logger.info("╚════════════════════════════════════════════════════════╝")
        logger.info()
        _init_timescaledb(conn, cur)

        logger.info()
        logger.info("Schema is now READY for loaders to use")
        logger.info()
        return failed == 0

    except Exception as e:
        logger.info(f"ERROR: {e}")
        return False
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def main():
    return init_database()


if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
