#!/usr/bin/env python3
"""
Database migration runner - works locally with .env.local and in AWS with Secrets Manager.
Tracks applied migrations in database to prevent re-running.

Usage:
    Local:  python3 migrations.py up
    AWS:    AWS_REGION=us-east-1 DB_SECRET_ARN=arn:... python3 migrations.py up
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


class MigrationRunner:
    def __init__(self):
        self.conn = None
        self.migrations_dir = Path(__file__).parent / "migrations"
        self.migrations_dir.mkdir(exist_ok=True)

    def get_connection(self):
        """Connect to database using env vars (local) or Secrets Manager (AWS)."""
        if self.conn and not self.conn.closed:
            return self.conn

        # Try AWS first
        db_secret_arn = os.getenv("DB_SECRET_ARN")
        if db_secret_arn:
            return self._connect_aws(db_secret_arn)

        # Fall back to local env vars
        return self._connect_local()

    def _connect_local(self):
        """Connect using local environment variables."""
        from dotenv import load_dotenv
        load_dotenv(".env.local")

        self.conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "stocks"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "stocks"),
        )
        return self.conn

    def _connect_aws(self, secret_arn):
        """Fetch credentials from AWS Secrets Manager and connect."""
        import boto3
        import json

        region = os.getenv("AWS_REGION", "us-east-1")
        client = boto3.client("secretsmanager", region_name=region)

        try:
            response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response["SecretString"])

            self.conn = psycopg2.connect(
                host=secret.get("host"),
                port=int(secret.get("port", 5432)),
                user=secret.get("username"),
                password=secret.get("password"),
                database=secret.get("dbname", "stocks"),
            )
            return self.conn
        except Exception as e:
            log.error(f"Failed to fetch secret {secret_arn}: {e}")
            raise

    def _ensure_migration_table(self):
        """Create migrations table if it doesn't exist."""
        conn = self.get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id SERIAL PRIMARY KEY,
                    version VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    applied_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            conn.commit()

    def _get_applied_migrations(self):
        """Get list of already-applied migrations."""
        conn = self.get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM schema_migrations ORDER BY version")
            return {row[0] for row in cur.fetchall()}

    def _get_pending_migrations(self):
        """Get list of .sql files that haven't been applied."""
        applied = self._get_applied_migrations()
        pending = []

        for sql_file in sorted(self.migrations_dir.glob("*.sql")):
            version = sql_file.stem  # e.g., "001_init" from "001_init.sql"
            if version not in applied:
                pending.append((version, sql_file))

        return pending

    def up(self):
        """Run all pending migrations."""
        self._ensure_migration_table()
        pending = self._get_pending_migrations()

        if not pending:
            log.info("No pending migrations.")
            return True

        log.info(f"Found {len(pending)} pending migration(s)")

        try:
            for version, sql_file in pending:
                self._run_migration(version, sql_file)
            log.info("✓ All migrations applied successfully")
            return True
        except Exception as e:
            log.error(f"Migration failed: {e}")
            return False

    def _run_migration(self, version, sql_file):
        """Run a single migration file."""
        log.info(f"  Applying {version}...")

        sql_content = sql_file.read_text()
        conn = self.get_connection()

        try:
            with conn.cursor() as cur:
                # Execute the migration SQL
                cur.execute(sql_content)

                # Record that it was applied
                cur.execute(
                    """
                    INSERT INTO schema_migrations (version, name)
                    VALUES (%s, %s)
                    """,
                    (version, sql_file.name),
                )

            conn.commit()
            log.info(f"  ✓ {version} applied")

        except Exception as e:
            conn.rollback()
            log.error(f"  ✗ {version} failed: {e}")
            raise

    def status(self):
        """Show migration status."""
        self._ensure_migration_table()
        applied = self._get_applied_migrations()
        pending = self._get_pending_migrations()

        log.info("Applied migrations:")
        for version in sorted(applied):
            log.info(f"  ✓ {version}")

        if pending:
            log.info(f"\nPending migrations ({len(pending)}):")
            for version, _ in pending:
                log.info(f"  ○ {version}")
        else:
            log.info("\nAll migrations applied!")

    def close(self):
        if self.conn:
            self.conn.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 migrations.py [up|status]")
        sys.exit(1)

    runner = MigrationRunner()
    try:
        command = sys.argv[1]
        if command == "up":
            success = runner.up()
            sys.exit(0 if success else 1)
        elif command == "status":
            runner.status()
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    finally:
        runner.close()


if __name__ == "__main__":
    main()
