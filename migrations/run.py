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

import json
import logging
import os
import sys
from pathlib import Path

# When run inside the db-migration Lambda, psycopg2 is expected to come from the shared
# algo-psycopg2-layer-dev layer at /opt/python/lib/python3.12/site-packages. Similarly,
# migrations that import from utils need the Lambda function directory (/var/task). The
# Lambda function invokes this script as a subprocess with PYTHONPATH set to include both
# /var/task and /opt/python paths. Python automatically adds PYTHONPATH to sys.path, but
# we also explicitly add them here to ensure they're available before any imports.
lambda_root_dir = str(Path(__file__).parent.parent)
if lambda_root_dir not in sys.path:
    sys.stderr.write(f"[DIAG] Adding Lambda root to sys.path: {lambda_root_dir}\n")
    sys.path.insert(0, lambda_root_dir)

if os.path.isdir("/opt"):
    for _root in ("/opt", "/opt/python"):
        if os.path.isdir(_root):
            sys.stderr.write(f"[DIAG] {_root} contents: {os.listdir(_root)}\n")
    for _candidate in (
        "/opt/python/lib/python3.12/site-packages",
        "/opt/python/lib/python3.11/site-packages",
        "/opt/python",
    ):
        if os.path.isdir(_candidate) and _candidate not in sys.path:
            sys.stderr.write(f"[DIAG] Adding to sys.path: {_candidate}\n")
            sys.path.insert(0, _candidate)

import psycopg2

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _has_sql_content(stmt: str) -> bool:
    """Return True if stmt has any SQL beyond whitespace and -- line comments."""
    for line in stmt.splitlines():
        s = line.strip()
        if s and not s.startswith("--"):
            return True
    return False


def _split_sql_statements(sql: str) -> list:
    """Split SQL into individual statements on ';', respecting dollar-quoted strings.

    PostgreSQL functions use dollar-quoting ($$ ... $$ or $tag$ ... $tag$).
    A naive sql.split(';') breaks inside function bodies that contain semicolons.
    Filters out empty or comment-only fragments (psycopg2 rejects empty queries).
    """
    statements = []
    current = []
    dollar_tag = None  # None = not in dollar-quote; set to tag string when inside
    i = 0
    n = len(sql)

    while i < n:
        ch = sql[i]

        # Skip line comments (-- ...) without treating their ; as statement separators
        if dollar_tag is None and ch == "-" and i + 1 < n and sql[i + 1] == "-":
            while i < n and sql[i] != "\n":
                current.append(sql[i])
                i += 1
            continue

        if dollar_tag is None and ch == "$":
            # Scan potential dollar-quote opening tag: $identchars$
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            if j < n and sql[j] == "$":
                tag = sql[i : j + 1]
                dollar_tag = tag
                current.append(tag)
                i = j + 1
                continue
        elif dollar_tag is not None and ch == "$":
            end = i + len(dollar_tag)
            if sql[i:end] == dollar_tag:
                current.append(dollar_tag)
                i = end
                dollar_tag = None
                continue

        if ch == ";" and dollar_tag is None:
            stmt = "".join(current).strip()
            if _has_sql_content(stmt):
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
        i += 1

    stmt = "".join(current).strip()
    if _has_sql_content(stmt):
        statements.append(stmt)

    return statements


def _load_credentials():
    """Load database credentials from environment or stdin.

    DB_HOST is required - no localhost fallback for safety. All credentials
    must be explicitly set via environment or stdin to prevent accidental
    misconfiguration.
    """
    # Check if credentials should be loaded from stdin
    if "--credentials-from-stdin" in sys.argv:
        try:
            creds_json = sys.stdin.read()
            creds = json.loads(creds_json)
            host = creds.get("host")
            if not host:
                logger.error("ERROR: 'host' is required in credentials JSON (no localhost fallback for safety)")
                sys.exit(1)
            password = creds.get("password")
            if not password:
                logger.error("[CRITICAL] Password missing from credentials JSON — cannot authenticate to database")
                sys.exit(1)
            return (
                host,
                int(creds.get("port", 5432)),
                creds.get("username", "postgres"),
                password,
                creds.get("dbname", "algo"),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse credentials from stdin: {e}")
            sys.exit(1)

    # DB_HOST is required - no localhost fallback for safety
    db_host = os.getenv("DB_HOST")
    if not db_host:
        logger.error("ERROR: DB_HOST environment variable is required (no localhost fallback for safety)")
        sys.exit(1)

    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        logger.error("[CRITICAL] DB_PASSWORD environment variable is required — cannot authenticate to database")
        sys.exit(1)

    return (
        db_host,
        int(os.getenv("DB_PORT", 5432)),
        os.getenv("DB_USER", "postgres"),
        db_password,
        os.getenv("DB_NAME", "algo"),
    )


# Database connection details from environment or stdin
DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME = _load_credentials()

# Map environment DB_SSL values to psycopg2 SSL modes
_ssl_map = {
    "true": "require",
    "false": "disable",
    "disable": "disable",
    "prefer": "prefer",
    "require": "require",
}
DB_SSL = _ssl_map.get(os.getenv("DB_SSL", "require").lower(), "require")

MIGRATIONS_DIR = Path(__file__).parent / "versions"


class MigrationRunner:
    """Manages schema migrations with versioning."""

    def __init__(self):
        self.conn = None
        self.cursor = None

    def connect(self):
        """Establish database connection.

        Sets an explicit lock_timeout on the session. The RDS parameter group sets
        statement_timeout=900000ms (15min) cluster-wide (terraform/modules/database/main.tf)
        but nothing bounds how long a DDL statement (ALTER TABLE, CREATE INDEX, etc.) waits
        to *acquire* its lock before it even starts executing -- statement_timeout's clock
        only starts once the statement begins running. Confirmed live 2026-07-07: three
        consecutive db-migration Lambda invocations each hung for ~850s (the subprocess
        wrapper's own kill timeout, always firing 50s before the 900s statement_timeout
        could) with zero indication of what was blocked -- consistent with a migration
        stuck waiting on a lock held by another long-lived connection (orchestrator,
        leaked idle-in-transaction session, etc.) rather than a slow-but-progressing query.
        A short lock_timeout makes that failure mode fail fast with an actionable Postgres
        error ("could not obtain lock ... due to lock timeout") instead of silently hanging
        for minutes. connect_timeout guards against a similarly silent hang during the
        initial TCP/SSL handshake if the DB is unreachable.
        """
        try:
            self.conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                sslmode=DB_SSL,
                connect_timeout=10,
            )
            self.cursor = self.conn.cursor()
            self.cursor.execute("SET lock_timeout = '300s'")
            self.conn.commit()
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

    def get_applied_migrations(self) -> list[str]:
        """Get list of applied migrations that haven't been rolled back."""
        query = "SELECT version FROM schema_version WHERE rolled_back_at IS NULL ORDER BY applied_at"
        try:
            self.cursor.execute(query)
            return [row[0] for row in self.cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"[CRITICAL] Failed to fetch applied migrations: {e}")
            raise RuntimeError(
                f"Cannot determine applied migrations: database query failed. {e}. "
                "Migration state is unknown. Check database connectivity and schema_version table."
            ) from e

    def get_pending_migrations(self) -> list[tuple[str, Path]]:
        """Get list of migration files that haven't been applied."""
        applied = set(self.get_applied_migrations())

        # Find all .sql and .py migration files (exclude __init__.py)
        all_files = [
            f
            for f in list(MIGRATIONS_DIR.glob("*.sql")) + list(MIGRATIONS_DIR.glob("*.py"))
            if not f.name.startswith("_")
        ]
        migration_files = sorted(all_files, key=lambda f: f.stem)

        pending = []
        for mig_file in migration_files:
            version = mig_file.stem  # e.g., "001_initial_schema"
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
            if mig_path.suffix == ".sql":
                # Handle SQL migrations
                with open(mig_path, encoding="utf-8") as f:
                    sql = f.read()

                statements = _split_sql_statements(sql)

                for statement in statements:
                    logger.debug(f"Executing SQL: {statement[:80]}...")
                    self.cursor.execute(statement)

                self.conn.commit()

            elif mig_path.suffix == ".py":
                # Handle Python migrations: import module and call up()
                import importlib.util

                spec = importlib.util.spec_from_file_location(version, mig_path)
                migration_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration_module)

                if not hasattr(migration_module, "up"):
                    raise AttributeError(f"Migration {version} has no up() function")

                # Set environment variables for Python migrations that need to connect
                # to the database (they read these with os.getenv())
                old_env = {}
                env_vars = {
                    "DB_HOST": DB_HOST,
                    "DB_PORT": str(DB_PORT),
                    "DB_USER": DB_USER,
                    "DB_PASSWORD": DB_PASSWORD,
                    "DB_NAME": DB_NAME,
                    "DB_SSL": DB_SSL,
                }
                for key, value in env_vars.items():
                    old_env[key] = os.getenv(key)
                    os.environ[key] = value

                try:
                    logger.info(f"Running Python migration: {version}")
                    migration_module.up()
                    logger.debug(f"Completed Python migration: {version}")
                finally:
                    # Restore original environment
                    for key, value in old_env.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value

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
            raise RuntimeError(f"Operation failed: {e}") from e

    def show_status(self):
        """Display migration status."""
        applied = self.get_applied_migrations()
        pending = self.get_pending_migrations()

        print("\n" + "=" * 60)
        print("MIGRATION STATUS")
        print("=" * 60)

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

        print("=" * 60 + "\n")

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
    if "--credentials-from-stdin" in sys.argv:
        sys.argv.remove("--credentials-from-stdin")

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    runner = MigrationRunner()

    try:
        runner.connect()
        runner.ensure_schema_version_table()

        if command == "apply":
            if len(sys.argv) > 2 and sys.argv[2] == "--all":
                success = runner.apply_all_pending()
                sys.exit(0 if success else 1)
            elif len(sys.argv) > 2:
                version = sys.argv[2]
                # Look for both .sql and .py migrations
                migration_files = list(MIGRATIONS_DIR.glob(f"{version}.sql"))
                if not migration_files:
                    migration_files = list(MIGRATIONS_DIR.glob(f"{version}.py"))
                if not migration_files:
                    logger.error(f"Migration {version} not found (.sql or .py)")
                    sys.exit(1)
                success = runner.apply_migration(version, migration_files[0])
                sys.exit(0 if success else 1)
            else:
                print("Usage: apply <version> or apply --all")
                sys.exit(1)

        elif command == "status":
            runner.show_status()
            sys.exit(0)

        elif command == "rollback":
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


if __name__ == "__main__":
    main()
