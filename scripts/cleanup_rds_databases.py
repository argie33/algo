#!/usr/bin/env python3
"""
Cleanup script to identify and remove extra databases from RDS.
This should only run if explicitly authorized to delete databases.

⚠️ DEPRECATED: Emergency workaround script — bypasses RDS Proxy connection pooling
This script connects directly to AWS RDS and performs database cleanup operations.

CRITICAL NOTE: This script exists because the primary database connection layer
(RDS Proxy) was failing. The root cause should be fixed in the connection layer
instead of using this workaround.

DO NOT use this script except as a last resort during infrastructure failures.
Database cleanup should normally be done through:
1. Lambda handlers (which use RDS Proxy)
2. AWS RDS console (for admin operations)
3. Terraform automation (for infrastructure changes)

This script bypasses audit trails and IAM permission checks.

Usage:
    python3 scripts/cleanup_rds_databases.py --list        # List all databases
    python3 scripts/cleanup_rds_databases.py --drop=DB     # Drop specific database
    python3 scripts/cleanup_rds_databases.py --clean       # Drop all extra databases (requires confirmation)
"""

import argparse
import getpass
import os
import sys

import psycopg2


class RDSCleaner:
    """Helper class to manage RDS database cleanup."""

    EXPECTED_DB = "stocks"
    PROTECTED_DBS = {"postgres", "template0", "template1", "stocks"}

    def __init__(self, host: str, port: int, user: str, password: str, db: str):
        """Initialize connection to RDS."""
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.db = db
        self.conn = None

    def connect(self) -> bool:
        """Connect to RDS master database."""
        try:
            print(f"[*] Connecting to {self.host}:{self.port}...")
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.db,
                connect_timeout=10
            )
            print("[OK] Connected successfully!")
            return True
        except psycopg2.OperationalError as e:
            print(f"[ERROR] Connection failed: {e}")
            return False
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            return False

    def list_databases(self) -> list[tuple[str, str, float]]:
        """List all non-template databases."""
        if not self.conn:
            return []

        try:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT datname, pg_get_userbyid(datdba), pg_database_size(datname)
                FROM pg_database
                WHERE datistemplate = false
                ORDER BY datname;
            """)
            databases = cur.fetchall()
            cur.close()
            return databases
        except Exception as e:
            print(f"[ERROR] Could not list databases: {e}")
            return []

    def get_extra_databases(self, databases: list[tuple]) -> list[str]:
        """Identify databases that should not exist."""
        extra = []
        for db_name, _, _ in databases:
            if db_name not in self.PROTECTED_DBS:
                extra.append(db_name)
        return extra

    def drop_database(self, db_name: str, force: bool = False) -> bool:
        """Drop a database."""
        if db_name in self.PROTECTED_DBS:
            print(f"[WARN] Cannot drop protected database: {db_name}")
            return False

        if not self.conn:
            print("[ERROR] Not connected to database")
            return False

        try:
            # Terminate all connections to the database
            cur = self.conn.cursor()
            cur.execute("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid();
            """, (db_name,))
            print(f"[*] Terminated existing connections to {db_name}")

            # Drop the database
            cur.execute(f"DROP DATABASE IF EXISTS {psycopg2.sql.Identifier(db_name).as_string(cur)};")
            self.conn.commit()
            print(f"[OK] Dropped database: {db_name}")
            cur.close()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to drop {db_name}: {e}")
            self.conn.rollback()
            return False

    def close(self):
        """Close RDS connection."""
        if self.conn:
            self.conn.close()


def main():
    parser = argparse.ArgumentParser(description="Clean up extra RDS databases")
    parser.add_argument("--host", default="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com",
                       help="RDS endpoint")
    parser.add_argument("--port", type=int, default=5432, help="RDS port")
    parser.add_argument("--user", default="stocks", help="Master username")
    parser.add_argument("--password", help="Master password (will prompt if not provided)")
    parser.add_argument("--db", default="stocks", help="Master database name")
    parser.add_argument("--list", action="store_true", help="List all databases")
    parser.add_argument("--drop", help="Drop specific database")
    parser.add_argument("--clean", action="store_true", help="Drop all extra databases (requires confirmation)")

    args = parser.parse_args()

    # Get password if not provided
    password = args.password
    if not password:
        password = os.getenv("DB_PASSWORD")
    if not password:
        password = getpass.getpass("Enter RDS master password: ")

    if not password:
        print("[ERROR] No password provided")
        sys.exit(1)

    # Connect
    cleaner = RDSCleaner(args.host, args.port, args.user, password, args.db)
    if not cleaner.connect():
        sys.exit(1)

    try:
        # List databases
        print("\n[*] Scanning databases...\n")
        databases = cleaner.list_databases()

        print(f"Found {len(databases)} databases:\n")
        for db_name, owner, size in databases:
            status = "[EXPECTED]" if db_name == "stocks" else "[EXTRA]"
            size_mb = size / (1024 * 1024) if size else 0
            print(f"  {status} {db_name:20s} (owner: {owner:10s}, size: {size_mb:8.2f} MB)")

        # Identify extra databases
        extra_dbs = cleaner.get_extra_databases(databases)
        print(f"\n{'='*60}")

        if args.list or (not args.drop and not args.clean):
            if extra_dbs:
                print(f"[WARNING] Found {len(extra_dbs)} extra database(s): {extra_dbs}")
                print("\nTo remove them, run:")
                for db in extra_dbs:
                    print(f"  python3 scripts/cleanup_rds_databases.py --drop={db}")
            else:
                print("[OK] No extra databases found.")

        # Drop specific database
        if args.drop:
            db_to_drop = args.drop
            print(f"\n[*] Preparing to drop database: {db_to_drop}")
            confirm = input("Are you sure? Type 'yes' to confirm: ").strip().lower()
            if confirm == "yes":
                cleaner.drop_database(db_to_drop)
            else:
                print("[CANCEL] Drop cancelled")

        # Clean all extra databases
        if args.clean:
            if not extra_dbs:
                print("[OK] No extra databases to clean")
            else:
                print(f"\n[WARNING] About to drop {len(extra_dbs)} database(s):")
                for db in extra_dbs:
                    print(f"  - {db}")
                confirm = input("\nType 'yes' to confirm deletion of ALL extra databases: ").strip().lower()
                if confirm == "yes":
                    dropped = 0
                    for db in extra_dbs:
                        if cleaner.drop_database(db):
                            dropped += 1
                    print(f"\n[OK] Dropped {dropped}/{len(extra_dbs)} extra database(s)")
                else:
                    print("[CANCEL] Clean cancelled")

    finally:
        cleaner.close()


if __name__ == "__main__":
    main()
