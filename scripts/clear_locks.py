#!/usr/bin/env python3
"""Clear orchestrator and loader locks."""
from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table


with DatabaseContext('write') as cur:
    # Check for distributed locks (various lock mechanisms)
    try:
        cur.execute("SELECT * FROM orchestrator_locks")
        locks = cur.fetchall()
        print(f"Found {len(locks)} orchestrator_locks:")
        for lock in locks:
            print(f"  {lock}")
    except Exception as e:
        if "does not exist" in str(e) or "undefined table" in str(e):
            print("No orchestrator_locks table")
        else:
            raise

    try:
        cur.execute("SELECT * FROM distributed_locks")
        locks = cur.fetchall()
        print(f"Found {len(locks)} distributed_locks:")
        for lock in locks:
            print(f"  {lock}")
        if locks:
            cur.execute("DELETE FROM distributed_locks")
            print(f"Cleared {cur.rowcount} distributed locks")
    except Exception as e:
        if "does not exist" in str(e) or "undefined table" in str(e):
            print("No distributed_locks table")
        else:
            raise

    try:
        cur.execute("SELECT * FROM advisory_locks")
        locks = cur.fetchall()
        print(f"Found {len(locks)} advisory_locks:")
        for lock in locks:
            print(f"  {lock}")
        if locks:
            cur.execute("DELETE FROM advisory_locks")
            print(f"Cleared {cur.rowcount} advisory locks")
    except Exception as e:
        if "does not exist" in str(e) or "undefined table" in str(e):
            print("No advisory_locks table")
        else:
            raise

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
        except Exception as e:
            print(f"Could not clear {table}: {e}")
