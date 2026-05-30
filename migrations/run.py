#!/usr/bin/env python3
"""
Database Migration Runner

Manages schema migrations with version tracking and rollback support.

Usage:
    python migrations/run.py --apply      # Apply pending migrations
    python migrations/run.py --status     # Show migration status
    python migrations/run.py --rollback <version>  # Rollback specific version
"""

import os
import sys
import hashlib
import argparse
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.credential_manager import get_db_config
import psycopg2
from psycopg2.extras import DictCursor

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class MigrationRunner:
    """Manages database migrations with version tracking."""

    def __init__(self):
        self.migrations_dir = Path(__file__).parent / 'versions'
        self.init_file = Path(__file__).parent / '0001_init_schema_version.sql'
        self.db_config = get_db_config()
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.cur = self.conn.cursor(cursor_factory=DictCursor)
            logger.info("Connected to database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
            logger.info("Disconnected from database")

    def init_schema_version_table(self):
        """Create schema_version table if it doesn't exist."""
        try:
            with open(self.init_file, 'r') as f:
                sql = f.read()

            self.cur.execute(sql)
            self.conn.commit()
            logger.info("Initialized schema_version table")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to initialize schema_version table: {e}")
            raise

    def get_applied_migrations(self):
        """Get list of applied migrations."""
        try:
            self.cur.execute(
                "SELECT version FROM schema_version WHERE rolled_back_at IS NULL ORDER BY applied_at"
            )
            return [row['version'] for row in self.cur.fetchall()]
        except psycopg2.errors.UndefinedTable:
            return []

    def get_pending_migrations(self):
        """Get list of migrations that need to be applied."""
        if not self.migrations_dir.exists():
            return []

        applied = self.get_applied_migrations()
        pending = []

        for migration_file in sorted(self.migrations_dir.glob('*.sql')):
            version = migration_file.stem
            if version not in applied:
                pending.append({
                    'version': version,
                    'file': migration_file,
                    'description': self._get_description(migration_file)
                })

        return pending

    def _get_description(self, migration_file):
        """Extract description from migration file."""
        try:
            with open(migration_file, 'r') as f:
                for line in f:
                    if 'Description:' in line:
                        return line.split('Description:')[1].strip()
        except:
            pass
        return ""

    def _calculate_checksum(self, sql_content):
        """Calculate SHA-256 checksum of SQL content."""
        return hashlib.sha256(sql_content.encode()).hexdigest()

    def apply_migration(self, version, migration_file):
        """Apply a single migration."""
        try:
            with open(migration_file, 'r') as f:
                sql = f.read()

            # Execute migration
            self.cur.execute(sql)

            # Record in schema_version table
            checksum = self._calculate_checksum(sql)
            description = self._get_description(migration_file)

            self.cur.execute(
                """INSERT INTO schema_version (version, description, checksum, applied_at)
                   VALUES (%s, %s, %s, %s)""",
                (version, description, checksum, datetime.now())
            )

            self.conn.commit()
            logger.info(f"✓ Applied migration: {version}")
            return True
        except Exception as e:
            self.conn.rollback()
            logger.error(f"✗ Failed to apply migration {version}: {e}")
            return False

    def apply_all_pending(self):
        """Apply all pending migrations."""
        self.connect()
        try:
            self.init_schema_version_table()
            pending = self.get_pending_migrations()

            if not pending:
                logger.info("No pending migrations")
                return True

            logger.info(f"Found {len(pending)} pending migrations")
            success = True

            for migration in pending:
                if not self.apply_migration(migration['version'], migration['file']):
                    success = False
                    break

            return success
        finally:
            self.disconnect()

    def show_status(self):
        """Show migration status."""
        self.connect()
        try:
            applied = self.get_applied_migrations()
            pending = self.get_pending_migrations()

            logger.info("\n" + "="*70)
            logger.info("MIGRATION STATUS")
            logger.info("="*70)

            if applied:
                logger.info(f"\nApplied ({len(applied)}):")
                for version in applied:
                    logger.info(f"  ✓ {version}")
            else:
                logger.info("\nApplied: None")

            if pending:
                logger.info(f"\nPending ({len(pending)}):")
                for m in pending:
                    logger.info(f"  ○ {m['version']} - {m['description']}")
            else:
                logger.info("\nPending: None (database is up-to-date)")

            logger.info("="*70 + "\n")
        finally:
            self.disconnect()

    def rollback_migration(self, version):
        """Rollback a specific migration."""
        logger.warning(f"Rollback requested for {version}")
        logger.warning("Rollback functionality requires reverse migrations - not yet implemented")
        logger.warning("To rollback: restore database from backup and re-apply remaining migrations")
        return False


def main():
    parser = argparse.ArgumentParser(description='Database migration runner')
    parser.add_argument('--apply', action='store_true', help='Apply pending migrations')
    parser.add_argument('--status', action='store_true', help='Show migration status')
    parser.add_argument('--rollback', type=str, help='Rollback specific version')

    args = parser.parse_args()

    runner = MigrationRunner()

    if args.apply:
        success = runner.apply_all_pending()
        sys.exit(0 if success else 1)
    elif args.status:
        runner.show_status()
        sys.exit(0)
    elif args.rollback:
        success = runner.rollback_migration(args.rollback)
        sys.exit(0 if success else 1)
    else:
        runner.show_status()
        sys.exit(0)


if __name__ == '__main__':
    main()
