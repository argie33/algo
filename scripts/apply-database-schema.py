#!/usr/bin/env python3
"""Apply database schema from schema.sql file to initialize the database."""

import sys
import os
import psycopg2
import psycopg2.extensions
from pathlib import Path


def get_db_connection():
    """Create database connection from environment variables."""
    required_vars = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [v for v in required_vars if not os.getenv(v)]

    if missing:
        print("[ERROR] Missing environment variables: {}".format(", ".join(missing)))
        sys.exit(1)

    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", 5432)),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )
        # Set to autocommit mode for DDL statements
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except psycopg2.Error as e:
        print("[ERROR] Database connection failed: {}".format(e))
        sys.exit(1)


def load_schema(schema_file):
    """Load schema SQL from file."""
    try:
        with open(schema_file, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        print("[ERROR] Schema file not found: {}".format(schema_file))
        sys.exit(1)


def apply_schema(conn, schema_sql):
    """Apply schema to database using psycopg2."""
    try:
        cur = conn.cursor()

        print("Executing schema SQL (this may take a minute)...")

        # Execute the entire schema as one batch - psycopg2 handles complex SQL
        try:
            cur.execute(schema_sql)
            print("[OK] Schema applied successfully!")
            return True
        except psycopg2.Error as e:
            # Try to give useful feedback
            error_str = str(e)
            if "already exists" in error_str.lower():
                print("[INFO] Some objects already exist - continuing...")
                return True
            else:
                print("[ERROR] {}".format(e))
                return False

    except Exception as e:
        print("[ERROR] Unexpected error: {}".format(e))
        return False
    finally:
        if cur:
            cur.close()


def main():
    print("=" * 70)
    print("DATABASE SCHEMA INITIALIZATION")
    print("=" * 70 + "\n")

    print("Connecting to database...")
    conn = get_db_connection()
    print("[OK] Connected\n")

    script_dir = Path(__file__).parent
    schema_file = script_dir.parent / "lambda" / "db-init" / "schema.sql"
    print("Loading schema from: {}".format(schema_file))
    schema_sql = load_schema(schema_file)
    print("[OK] Schema loaded ({} bytes)\n".format(len(schema_sql)))

    print("Applying schema...")
    success = apply_schema(conn, schema_sql)

    conn.close()

    if success:
        print("\nTo verify the schema was created, run:")
        print("  python scripts/diagnose-dashboard-data.py")

    print("=" * 70)


if __name__ == "__main__":
    main()
