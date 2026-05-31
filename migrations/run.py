#!/usr/bin/env python3
"""Database schema migration runner.

Manages versioning and execution of SQL migrations with rollback support.

Usage:
    python migrations/run.py apply                # Apply all pending migrations
    python migrations/run.py rollback <version>   # Rollback to version
    python migrations/run.py status               # Show migration status
    python migrations/run.py list                 # List all migrations
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime
import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.database_context import DatabaseContext

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "versions"


class MigrationRunner:
    def __init__(self):
        self.migrations_dir = MIGRATIONS_DIR
        self.migrations_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_tracking_table(self, cur):
        """Ensure schema_version table exists."""
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                id INT PRIMARY KEY,
                version VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                rolled_back_at TIMESTAMP NULL
            )
        """)

    def _get_applied_versions(self, cur) -> set:
        """Return set of applied migration versions."""
        self._ensure_tracking_table(cur)
        cur.execute("SELECT version FROM schema_version WHERE rolled_back_at IS NULL ORDER BY id")
        return {row[0] for row in cur.fetchall()}

    def _get_pending_migrations(self) -> list:
        """Return list of (version, path) for migrations not yet applied."""
        if not self.migrations_dir.exists():
            return []

        migration_files = sorted(self.migrations_dir.glob("*.sql"))
        with DatabaseContext('read') as cur:
            applied = self._get_applied_versions(cur)

        pending = []
        for path in migration_files:
            version = path.stem
            if version not in applied:
                pending.append((version, path))
        return pending

    def _read_migration_file(self, path: Path) -> tuple:
        """Parse migration file into up and down SQL.

        Format:
        -- Up
        CREATE TABLE ...;
        -- Down
        DROP TABLE ...;
        """
        content = path.read_text()
        parts = content.split("-- Down")
        up_sql = parts[0].replace("-- Up", "").strip() if len(parts) > 0 else ""
        down_sql = parts[1].strip() if len(parts) > 1 else ""
        return up_sql, down_sql

    def apply_migration(self, version: str, path: Path) -> bool:
        """Apply a single migration and record in schema_version."""
        try:
            up_sql, _ = self._read_migration_file(path)
            if not up_sql:
                logger.warning(f"Migration {version}: no Up SQL found")
                return False

            with DatabaseContext('write') as cur:
                self._ensure_tracking_table(cur)
                logger.info(f"Applying migration {version}...")
                cur.execute(up_sql)
                cur.execute(
                    "INSERT INTO schema_version (id, version, description) VALUES (%s, %s, %s)",
                    (self._next_version_id(cur), version, path.stem)
                )
                logger.info(f"✅ Migration {version} applied successfully")
                return True
        except Exception as e:
            logger.error(f"❌ Migration {version} failed: {e}")
            return False

    def _next_version_id(self, cur) -> int:
        """Get next ID for migration tracking."""
        cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM schema_version")
        return cur.fetchone()[0]

    def rollback_migration(self, version: str) -> bool:
        """Rollback a migration and mark as rolled back."""
        try:
            path = self.migrations_dir / f"{version}.sql"
            if not path.exists():
                logger.error(f"Migration file not found: {version}")
                return False

            _, down_sql = self._read_migration_file(path)
            if not down_sql:
                logger.warning(f"Migration {version}: no Down SQL found, skipping rollback")
                return False

            with DatabaseContext('write') as cur:
                self._ensure_tracking_table(cur)
                logger.info(f"Rolling back migration {version}...")
                cur.execute(down_sql)
                cur.execute(
                    "UPDATE schema_version SET rolled_back_at = CURRENT_TIMESTAMP WHERE version = %s",
                    (version,)
                )
                logger.info(f"✅ Migration {version} rolled back successfully")
                return True
        except Exception as e:
            logger.error(f"❌ Rollback {version} failed: {e}")
            return False

    def status(self):
        """Display migration status."""
        try:
            with DatabaseContext('read') as cur:
                applied = self._get_applied_versions(cur)
            pending = self._get_pending_migrations()

            print(f"\n📊 Migration Status")
            print(f"  Applied: {len(applied)}")
            print(f"  Pending: {len(pending)}")

            if applied:
                print(f"\n✅ Applied Migrations:")
                for v in sorted(applied):
                    print(f"   • {v}")

            if pending:
                print(f"\n⏳ Pending Migrations:")
                for version, _ in pending:
                    print(f"   • {version}")
            else:
                print(f"\n✨ All migrations applied!")
        except Exception as e:
            logger.error(f"Error checking status: {e}")

    def list_migrations(self):
        """List all available migrations."""
        if not self.migrations_dir.exists() or not list(self.migrations_dir.glob("*.sql")):
            print("No migrations found")
            return

        print("\n📋 Available Migrations:")
        for path in sorted(self.migrations_dir.glob("*.sql")):
            print(f"   • {path.stem}")

    def apply_all(self) -> bool:
        """Apply all pending migrations."""
        pending = self._get_pending_migrations()
        if not pending:
            logger.info("✨ All migrations already applied")
            return True

        success = True
        for version, path in pending:
            if not self.apply_migration(version, path):
                success = False
        return success


def main():
    runner = MigrationRunner()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "apply":
        success = runner.apply_all()
        sys.exit(0 if success else 1)
    elif command == "rollback" and len(sys.argv) > 2:
        version = sys.argv[2]
        success = runner.rollback_migration(version)
        sys.exit(0 if success else 1)
    elif command == "status":
        runner.status()
    elif command == "list":
        runner.list_migrations()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
