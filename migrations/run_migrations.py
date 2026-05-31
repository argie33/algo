#!/usr/bin/env python3
"""
Schema Migration Runner

Applies pending migrations in order, tracking applied versions in schema_version table.
Supports rollback for migrations that define a down() function.

Usage:
    python migrations/run_migrations.py --apply
    python migrations/run_migrations.py --status
    python migrations/run_migrations.py --rollback 001_initial_schema
"""

import os
import sys
import logging
import hashlib
import importlib.util
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional
import argparse

# Add parent directory to path so utils can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

MIGRATIONS_DIR = Path(__file__).parent


def load_migration(migration_file: Path):
    """Load a migration module dynamically."""
    spec = importlib.util.spec_from_file_location("migration", migration_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_migration_files() -> List[tuple]:
    """Get all migration files in order (sorted by version number)."""
    migrations = []
    for f in sorted(MIGRATIONS_DIR.glob("versions/*.py")):
        if f.name.startswith("_"):
            continue
        # Extract version from filename: 001_description.py → 001
        version = f.name.split("_")[0]
        migrations.append((version, f))
    return migrations


def get_applied_migrations() -> Dict[str, dict]:
    """Get all applied migrations from database."""
    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT version, applied_at, description, checksum
                FROM schema_version
                WHERE rolled_back_at IS NULL
                ORDER BY applied_at ASC
            """)
            return {row['version']: row for row in cur.fetchall()}
    except Exception as e:
        logger.debug(f"Could not read schema_version table (may not exist yet): {e}")
        return {}


def calculate_checksum(migration_file: Path) -> str:
    """Calculate SHA256 checksum of migration file."""
    with open(migration_file, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def ensure_schema_version_table():
    """Create schema_version table if it doesn't exist."""
    try:
        with DatabaseContext('write') as cur:
            schema_sql = Path(MIGRATIONS_DIR / 'schema_version.sql').read_text()
            cur.execute(schema_sql)
        logger.info("✓ schema_version table ready")
    except Exception as e:
        logger.error(f"Failed to create schema_version table: {e}")
        raise


def apply_migration(version: str, migration_file: Path) -> bool:
    """Apply a single migration. Returns True if successful."""
    logger.info(f"Applying migration {version}...")

    try:
        module = load_migration(migration_file)
        checksum = calculate_checksum(migration_file)
        description = getattr(module, 'DESCRIPTION', 'No description')

        # Execute up() function if it exists
        if hasattr(module, 'up'):
            module.up()

        # Record in schema_version table
        with DatabaseContext('write') as cur:
            cur.execute("""
                INSERT INTO schema_version (version, description, checksum, applied_by)
                VALUES (%s, %s, %s, %s)
            """, (version, description, checksum, os.getenv('USER', 'unknown')))

        logger.info(f"✓ Migration {version} applied successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Migration {version} failed: {e}")
        return False


def rollback_migration(version: str) -> bool:
    """Rollback a migration. Returns True if successful."""
    logger.info(f"Rolling back migration {version}...")

    try:
        migration_files = get_migration_files()
        migration_file = next(f for v, f in migration_files if v == version)
        module = load_migration(migration_file)

        # Execute down() function if it exists
        if not hasattr(module, 'down'):
            logger.error(f"Migration {version} does not define down() function")
            return False

        module.down()

        # Mark as rolled back in schema_version table
        with DatabaseContext('write') as cur:
            cur.execute("""
                UPDATE schema_version
                SET rolled_back_at = CURRENT_TIMESTAMP
                WHERE version = %s
            """, (version,))

        logger.info(f"✓ Migration {version} rolled back successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Rollback {version} failed: {e}")
        return False


def apply_all_pending():
    """Apply all pending migrations in order."""
    ensure_schema_version_table()

    applied = get_applied_migrations()
    migrations = get_migration_files()
    pending = [(v, f) for v, f in migrations if v not in applied]

    if not pending:
        logger.info("No pending migrations")
        return True

    logger.info(f"Found {len(pending)} pending migrations")

    for version, migration_file in pending:
        if not apply_migration(version, migration_file):
            logger.error(f"Stopping migration run due to failure at {version}")
            return False

    logger.info("All pending migrations applied successfully")
    return True


def show_status():
    """Show current migration status."""
    ensure_schema_version_table()

    applied = get_applied_migrations()
    migrations = get_migration_files()

    if not migrations:
        logger.info("No migrations found")
        return

    logger.info("\nMigration Status:")
    logger.info("-" * 80)

    for version, migration_file in migrations:
        status = "✓ APPLIED" if version in applied else "⊘ PENDING"
        app = applied[version] if version in applied else {}
        applied_time = app.get('applied_at', '-')
        logger.info(f"{version}: {status} - {app.get('description', 'No description')} ({applied_time})")

    logger.info("-" * 80)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Schema migration runner')
    parser.add_argument('--apply', action='store_true', help='Apply all pending migrations')
    parser.add_argument('--status', action='store_true', help='Show migration status')
    parser.add_argument('--rollback', metavar='VERSION', help='Rollback a specific migration')

    args = parser.parse_args()

    try:
        if args.apply:
            success = apply_all_pending()
            sys.exit(0 if success else 1)
        elif args.rollback:
            success = rollback_migration(args.rollback)
            sys.exit(0 if success else 1)
        else:
            show_status()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
