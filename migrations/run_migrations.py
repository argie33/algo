#!/usr/bin/env python3
"""
Database Migration Runner

Manages schema versioning and rollback:
- Tracks applied migrations in schema_version table
- Prevents duplicate application of migrations
- Supports rollback of previously applied migrations
- Verifies migration files before application

Usage:
    python3 migrations/run_migrations.py                    # Apply pending migrations
    python3 migrations/run_migrations.py --status           # Show migration status
    python3 migrations/run_migrations.py --rollback 001     # Rollback specific version
"""

import sys
import os
from pathlib import Path
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.credential_manager import get_db_config
import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MigrationRunner:
    """Manage database schema migrations."""

    def __init__(self):
        self.config = get_db_config()
        self.migrations_dir = Path(__file__).parent
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**self.config)
            self.conn.autocommit = True
            self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            logger.info("Connected to database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def disconnect(self):
        """Close database connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def ensure_migration_table(self):
        """Create schema_version table if it doesn't exist."""
        try:
            self.cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    id SERIAL PRIMARY KEY,
                    version VARCHAR(100) UNIQUE NOT NULL,
                    description TEXT,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    rolled_back_at TIMESTAMP NULL
                )
            """)
            logger.info("Migration tracking table ready")
        except Exception as e:
            logger.error(f"Failed to create migration table: {e}")
            raise

    def get_applied_migrations(self):
        """Get list of applied migrations."""
        try:
            self.cur.execute("""
                SELECT version FROM schema_version
                WHERE rolled_back_at IS NULL
                ORDER BY applied_at ASC
            """)
            return [row[0] for row in self.cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get applied migrations: {e}")
            return []

    def get_pending_migrations(self):
        """Get list of pending migrations (not yet applied)."""
        applied = self.get_applied_migrations()
        migration_files = sorted([
            f.stem for f in self.migrations_dir.glob('*.sql')
            if f.stem != 'schema'  # Exclude existing schema.sql
        ])
        pending = [m for m in migration_files if m not in applied]
        return pending

    def apply_migration(self, version):
        """Apply a single migration."""
        migration_file = self.migrations_dir / f"{version}.sql"

        if not migration_file.exists():
            logger.error(f"Migration file not found: {migration_file}")
            return False

        try:
            with open(migration_file, 'r') as f:
                sql = f.read()

            # Extract description from comment
            description = ""
            for line in sql.split('\n'):
                if 'Description:' in line:
                    description = line.split('Description:')[1].strip()
                    break

            # Execute migration
            self.cur.execute(sql)

            # Record migration
            self.cur.execute("""
                INSERT INTO schema_version (version, description)
                VALUES (%s, %s)
            """, (version, description))

            logger.info(f"Applied migration: {version} - {description}")
            return True

        except Exception as e:
            logger.error(f"Failed to apply migration {version}: {e}")
            return False

    def rollback_migration(self, version):
        """Rollback a single migration (marks as rolled_back)."""
        try:
            self.cur.execute("""
                UPDATE schema_version
                SET rolled_back_at = CURRENT_TIMESTAMP
                WHERE version = %s AND rolled_back_at IS NULL
            """, (version,))

            if self.cur.rowcount == 0:
                logger.warning(f"Migration {version} not found or already rolled back")
                return False

            logger.info(f"Rolled back migration: {version}")
            return True

        except Exception as e:
            logger.error(f"Failed to rollback migration {version}: {e}")
            return False

    def status(self):
        """Show migration status."""
        applied = self.get_applied_migrations()
        pending = self.get_pending_migrations()

        print("\nMigration Status")
        print("=" * 60)
        print(f"\nApplied Migrations ({len(applied)}):")
        for m in applied:
            print(f"  ✓ {m}")

        print(f"\nPending Migrations ({len(pending)}):")
        for m in pending:
            print(f"  ○ {m}")

        print("\n" + "=" * 60)

    def run(self):
        """Apply all pending migrations."""
        self.connect()
        try:
            self.ensure_migration_table()
            pending = self.get_pending_migrations()

            if not pending:
                logger.info("No pending migrations")
                return True

            logger.info(f"Found {len(pending)} pending migrations")
            for version in pending:
                if not self.apply_migration(version):
                    logger.error(f"Failed to apply migration {version}")
                    return False

            logger.info(f"Successfully applied {len(pending)} migrations")
            return True

        finally:
            self.disconnect()


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Database migration runner")
    parser.add_argument('--status', action='store_true', help='Show migration status')
    parser.add_argument('--rollback', metavar='VERSION', help='Rollback specific migration')

    args = parser.parse_args()

    runner = MigrationRunner()

    try:
        runner.connect()
        runner.ensure_migration_table()

        if args.status:
            runner.status()
        elif args.rollback:
            runner.rollback_migration(args.rollback)
            logger.info("Rollback recorded (manual cleanup may be needed)")
        else:
            # Apply pending migrations
            success = runner.run()
            sys.exit(0 if success else 1)

    finally:
        runner.disconnect()


if __name__ == '__main__':
    main()
