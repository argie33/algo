#!/usr/bin/env python3
"""
Schema migration runner with versioning and rollback support.

Usage:
    python migrations/run.py apply <version>    # Apply a specific migration
    python migrations/run.py apply --all         # Apply all pending migrations
    python migrations/run.py status              # Show applied/pending migrations
    python migrations/run.py rollback <version>  # Rollback a specific migration

Credentials can be provided via environment variables or stdin JSON (--credentials-from-stdin).
"""

import os
import sys
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple
import psycopg2
from psycopg2.extras import execute_values

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def _load_credentials():
    """Load database credentials from environment or stdin."""
    # Check if credentials should be loaded from stdin
    if '--credentials-from-stdin' in sys.argv:
        try:
            creds_json = sys.stdin.read()
            creds = json.loads(creds_json)
            return (
                creds.get('host', 'localhost'),
                int(creds.get('port', 5432)),
                creds.get('username', 'postgres'),
                creds.get('password', ''),
                creds.get('dbname', 'algo'),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse credentials from stdin: {e}")
            sys.exit(1)

    # Fall back to environment variables
    return (
        os.getenv('DB_HOST', 'localhost'),
        int(os.getenv('DB_PORT', 5432)),
        os.getenv('DB_USER', 'postgres'),
        os.getenv('DB_PASSWORD', ''),
        os.getenv('DB_NAME', 'algo'),
    )

# Database connection details from environment or stdin
DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME = _load_credentials()

# Map environment DB_SSL values to psycopg2 SSL modes
_ssl_map = {'true': 'require', 'false': 'disable', 'disable': 'disable', 'prefer': 'prefer', 'require': 'require'}
DB_SSL = _ssl_map.get(os.getenv('DB_SSL', 'require').lower(), 'require')

MIGRATIONS_DIR = Path(__file__).parent / 'versions'


class MigrationRunner:
    """Manages schema migrations with versioning."""

    def __init__(self):
        self.conn = None
        self.cursor = None

    def connect(self):
        """Establish database connection."""
        try:
            self.conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                sslmode=DB_SSL
            )
            self.cursor = self.conn.cursor()
            logger.info(f"Connected to {DB_NAME} at {DB_HOST}:{DB_PORT}")
        except psycopg2.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def disconnect(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("Disconnected from database")

    def ensure_schema_version_table(self):
        """Ensure schema_version table exists."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS schema_version (
            id SERIAL PRIMARY KEY,
            version VARCHAR(100) UNIQUE NOT NULL,
            description TEXT,
            applied_at TIMESTAMP DEFAULT NOW(),
            rolled_back_at TIMESTAMP NULL
        );
        CREATE INDEX IF NOT EXISTS idx_schema_version_version ON schema_version(version);
        CREATE INDEX IF NOT EXISTS idx_schema_version_applied_at ON schema_version(applied_at);
        """
        try:
            self.cursor.execute(create_table_sql)
            self.conn.commit()
            logger.info("schema_version table ready")
        except psycopg2.Error as e:
            logger.error(f"Failed to create schema_version table: {e}")
            self.conn.rollback()
            raise

    def get_applied_migrations(self) -> List[str]:
        """Get list of applied migrations that haven't been rolled back."""
        query = "SELECT version FROM schema_version WHERE rolled_back_at IS NULL ORDER BY applied_at"
        try:
            self.cursor.execute(query)
            return [row[0] for row in self.cursor.fetchall()]
        except psycopg2.Error as e:
            logger.warning(f"Could not fetch applied migrations: {e}")
            return []

    def get_pending_migrations(self) -> List[Tuple[str, Path]]:
        """Get list of migration files that haven't been applied."""
        applied = set(self.get_applied_migrations())

        # Find all .sql migration files
        migration_files = sorted(MIGRATIONS_DIR.glob('*.sql'))

        pending = []
        for mig_file in migration_files:
            version = mig_file.stem  # e.g., "001_schema_versioning"
            if version not in applied:
                pending.append((version, mig_file))

        return pending

    def record_migration(self, version: str, description: str = ""):
        """Record a migration as applied."""
        query = """
        INSERT INTO schema_version (version, description, applied_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (version) DO UPDATE SET
            rolled_back_at = NULL,
            applied_at = NOW()
        """
        try:
            self.cursor.execute(query, (version, description))
            self.conn.commit()
            logger.info(f"✓ Recorded migration: {version}")
        except psycopg2.Error as e:
            logger.error(f"Failed to record migration {version}: {e}")
            self.conn.rollback()
            raise

    def record_rollback(self, version: str):
        """Record a migration as rolled back."""
        query = """
        UPDATE schema_version
        SET rolled_back_at = NOW()
        WHERE version = %s
        """
        try:
            self.cursor.execute(query, (version,))
            self.conn.commit()
            logger.info(f"✓ Recorded rollback: {version}")
        except psycopg2.Error as e:
            logger.error(f"Failed to record rollback {version}: {e}")
            self.conn.rollback()
            raise

    def apply_migration(self, version: str, mig_path: Path):
        """Execute a migration (either SQL file or Python module with up() function)."""
        try:
            if mig_path.suffix == '.sql':
                # Handle SQL migrations
                with open(mig_path, 'r') as f:
                    sql = f.read()

                # Split by ';' to handle multiple statements
                statements = [s.strip() for s in sql.split(';') if s.strip()]

                for statement in statements:
                    logger.debug(f"Executing SQL: {statement[:80]}...")
                    self.cursor.execute(statement)

                self.conn.commit()

            elif mig_path.suffix == '.py':
                # Handle Python migrations: import module and call up()
                import importlib.util
                spec = importlib.util.spec_from_file_location(version, mig_path)
                migration_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration_module)

                if not hasattr(migration_module, 'up'):
                    raise AttributeError(f"Migration {version} has no up() function")

                logger.info(f"Running Python migration: {version}")
                migration_module.up()
                logger.debug(f"Completed Python migration: {version}")

            else:
                raise ValueError(f"Unknown migration file type: {mig_path.suffix}")

            self.record_migration(version)
            logger.info(f"✓ Applied migration: {version}")
            return True

        except psycopg2.Error as e:
            logger.error(f"Migration failed for {version}: {e}")
            self.conn.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error in {version}: {e}")
            self.conn.rollback()
            return False

    def rollback_migration(self, version: str):
        """Rollback a migration by marking it as rolled back."""
        try:
            self.record_rollback(version)
            logger.info(f"✓ Rolled back migration: {version}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback {version}: {e}")
            return False

    def show_status(self):
        """Display migration status."""
        applied = self.get_applied_migrations()
        pending = self.get_pending_migrations()

        print("\n" + "="*60)
        print("MIGRATION STATUS")
        print("="*60)

        if applied:
            print("\nApplied Migrations:")
            for version in applied:
                print(f"  [OK] {version}")
        else:
            print("\nNo migrations applied yet.")

        if pending:
            print(f"\nPending Migrations ({len(pending)}):")
            for version, _ in pending:
                print(f"  [--] {version}")
        else:
            print("\nAll migrations applied.")

        print("="*60 + "\n")

    def apply_all_pending(self) -> bool:
        """Apply all pending migrations."""
        pending = self.get_pending_migrations()

        if not pending:
            logger.info("No pending migrations")
            return True

        logger.info(f"Found {len(pending)} pending migration(s)")

        success = True
        for version, sql_path in pending:
            if not self.apply_migration(version, sql_path):
                success = False
                logger.error(f"Stopped at failed migration: {version}")
                break

        return success


def main():
    """CLI entry point."""
    # Filter out --credentials-from-stdin from sys.argv for cleaner argument parsing
    if '--credentials-from-stdin' in sys.argv:
        sys.argv.remove('--credentials-from-stdin')

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    runner = MigrationRunner()

    try:
        runner.connect()
        runner.ensure_schema_version_table()

        if command == 'apply':
            if len(sys.argv) > 2 and sys.argv[2] == '--all':
                success = runner.apply_all_pending()
                sys.exit(0 if success else 1)
            elif len(sys.argv) > 2:
                version = sys.argv[2]
                # Look for both .sql and .py migrations
                migration_files = list(MIGRATIONS_DIR.glob(f'{version}.sql'))
                if not migration_files:
                    migration_files = list(MIGRATIONS_DIR.glob(f'{version}.py'))
                if not migration_files:
                    logger.error(f"Migration {version} not found (.sql or .py)")
                    sys.exit(1)
                success = runner.apply_migration(version, migration_files[0])
                sys.exit(0 if success else 1)
            else:
                print("Usage: apply <version> or apply --all")
                sys.exit(1)

        elif command == 'status':
            runner.show_status()
            sys.exit(0)

        elif command == 'rollback':
            if len(sys.argv) < 3:
                print("Usage: rollback <version>")
                sys.exit(1)
            version = sys.argv[2]
            success = runner.rollback_migration(version)
            sys.exit(0 if success else 1)

        else:
            print(f"Unknown command: {command}")
            print(__doc__)
            sys.exit(1)

    finally:
        runner.disconnect()


if __name__ == '__main__':
    main()
