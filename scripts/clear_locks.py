#!/usr/bin/env python3
"""Clear orchestrator and loader locks."""
import psycopg2.errors

from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table


def main() -> None:
    """Clear all distributed locks from database."""
    with DatabaseContext('write') as cur:
        # Check for distributed locks (various lock mechanisms)
        try:
            cur.execute("SELECT * FROM orchestrator_locks")
            locks = cur.fetchall()
            print(f"Found {len(locks)} orchestrator_locks:")
            for lock in locks:
                print(f"  {lock}")
        except psycopg2.errors.UndefinedTable:
            print("No orchestrator_locks table")

        try:
            cur.execute("SELECT * FROM distributed_locks")
            locks = cur.fetchall()
            print(f"Found {len(locks)} distributed_locks:")
            for lock in locks:
                print(f"  {lock}")
            if locks:
                cur.execute("DELETE FROM distributed_locks")
                print(f"Cleared {cur.rowcount} distributed locks")
        except psycopg2.errors.UndefinedTable:
            print("No distributed_locks table")

        try:
            cur.execute("SELECT * FROM advisory_locks")
            locks = cur.fetchall()
            print(f"Found {len(locks)} advisory_locks:")
            for lock in locks:
                print(f"  {lock}")
            if locks:
                cur.execute("DELETE FROM advisory_locks")
                print(f"Cleared {cur.rowcount} advisory locks")
        except psycopg2.errors.UndefinedTable:
            print("No advisory_locks table")

        # Try to list all tables that might contain locks
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name LIKE '%lock%'
        """)
        lock_tables = cur.fetchall()
        print(f"\nLock-related tables: {lock_tables}")

        for table_tuple in lock_tables:
            table = table_tuple[0]
            try:
                table_safe = assert_safe_table(table)
                cur.execute(f"DELETE FROM {table_safe} WHERE 1=1")
                print(f"Cleared {cur.rowcount} rows from {table}")
            except (ValueError, psycopg2.errors.Error) as e:
                print(f"Could not clear {table}: {e}")


if __name__ == "__main__":
    main()
