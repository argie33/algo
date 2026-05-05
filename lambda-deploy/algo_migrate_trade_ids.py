#!/usr/bin/env python3
"""
Migration: Backfill trade_ids VARCHAR to trade_ids_arr TEXT[].

This script safely migrates existing comma-delimited trade_ids to PostgreSQL
ARRAY type. It includes verification and rollback capability.

USAGE:
  python3 algo_migrate_trade_ids.py --check       # Show what would migrate
  python3 algo_migrate_trade_ids.py --migrate     # Backfill arrays
  python3 algo_migrate_trade_ids.py --verify      # Verify migration
  python3 algo_migrate_trade_ids.py --cleanup     # Drop old trade_ids column
"""

import os
import psycopg2
import argparse
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


def check_migration_status(conn):
    """Show how many records need migration."""
    cur = conn.cursor()
    try:
        # Count records with old format
        cur.execute("""
            SELECT COUNT(*) as need_migration,
                   COUNT(CASE WHEN trade_ids_arr IS NOT NULL THEN 1 END) as already_migrated,
                   COUNT(*) as total
            FROM algo_positions
            WHERE trade_ids IS NOT NULL
        """)
        need_migration, already_migrated, total = cur.fetchone()

        print(f"\nMigration Status:")
        print(f"  Total positions with trade_ids: {total}")
        print(f"  Already migrated: {already_migrated}")
        print(f"  Need migration: {need_migration}")

        if need_migration > 0:
            cur.execute("""
                SELECT position_id, symbol, trade_ids, trade_ids_arr
                FROM algo_positions
                WHERE trade_ids IS NOT NULL AND trade_ids_arr IS NULL
                LIMIT 5
            """)
            print(f"\n  Sample records to migrate:")
            for pos_id, sym, old_val, new_val in cur.fetchall():
                print(f"    {pos_id:20} {sym:6} '{old_val}' -> {new_val}")

        return need_migration > 0

    finally:
        cur.close()


def perform_migration(conn):
    """Backfill trade_ids_arr from trade_ids."""
    cur = conn.cursor()
    try:
        print(f"\nStarting migration...")

        # Backfill: split comma-delimited trade_ids into array
        cur.execute("""
            UPDATE algo_positions
            SET trade_ids_arr = string_to_array(
                TRIM(BOTH ',' FROM trade_ids), ','
            )
            WHERE trade_ids IS NOT NULL AND trade_ids_arr IS NULL
        """)
        migrated = cur.rowcount
        conn.commit()

        print(f"  ✓ Migrated {migrated} records")

        # Verify conversion
        cur.execute("""
            SELECT COUNT(*)
            FROM algo_positions
            WHERE trade_ids IS NOT NULL AND (trade_ids_arr IS NULL OR array_length(trade_ids_arr, 1) = 0)
        """)
        still_empty = cur.fetchone()[0]

        if still_empty > 0:
            print(f"  ⚠ Warning: {still_empty} records still have NULL arrays")
            return False

        print(f"  ✓ All arrays populated successfully")
        return True

    except Exception as e:
        conn.rollback()
        print(f"  ✗ Migration failed: {e}")
        return False
    finally:
        cur.close()


def verify_migration(conn):
    """Verify migration correctness."""
    cur = conn.cursor()
    try:
        print(f"\nVerifying migration...")

        # Check for any nulls after migration
        cur.execute("""
            SELECT COUNT(*) FROM algo_positions
            WHERE trade_ids IS NOT NULL AND trade_ids_arr IS NULL
        """)
        null_count = cur.fetchone()[0]

        if null_count > 0:
            print(f"  ✗ {null_count} records have NULL arrays")
            return False

        print(f"  ✓ All records have arrays")

        # Spot check: verify array contents match original
        cur.execute("""
            SELECT position_id, symbol, trade_ids, array_to_string(trade_ids_arr, ',')
            FROM algo_positions
            WHERE trade_ids IS NOT NULL AND trade_ids_arr IS NOT NULL
            LIMIT 10
        """)

        all_match = True
        for pos_id, sym, old_val, new_val in cur.fetchall():
            # Normalize for comparison (trim commas)
            old_norm = old_val.strip(',')
            if old_norm != new_val:
                print(f"  ✗ Mismatch in {pos_id}: '{old_norm}' vs '{new_val}'")
                all_match = False

        if all_match:
            print(f"  ✓ Spot check passed (10 records verified)")
        return all_match

    finally:
        cur.close()


def cleanup_migration(conn):
    """Drop old trade_ids column (only after verification)."""
    cur = conn.cursor()
    try:
        print(f"\nCleaning up old column...")

        # Final safety check
        cur.execute("""
            SELECT COUNT(*) FROM algo_positions
            WHERE trade_ids IS NOT NULL AND trade_ids_arr IS NULL
        """)
        unmigratedcount = cur.fetchone()[0]

        if unmigratedcount > 0:
            print(f"  ✗ Cannot cleanup: {unmigratedcount} records not yet migrated")
            return False

        print(f"  • Dropping trade_ids column...")
        cur.execute("ALTER TABLE algo_positions DROP COLUMN trade_ids")
        conn.commit()

        print(f"  ✓ Old column dropped successfully")
        return True

    except Exception as e:
        conn.rollback()
        print(f"  ✗ Cleanup failed: {e}")
        return False
    finally:
        cur.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Migrate trade_ids to ARRAY type')
    parser.add_argument('--check', action='store_true', help='Check migration status')
    parser.add_argument('--migrate', action='store_true', help='Perform backfill migration')
    parser.add_argument('--verify', action='store_true', help='Verify migration')
    parser.add_argument('--cleanup', action='store_true', help='Drop old column')
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)

    try:
        if args.check:
            check_migration_status(conn)
        elif args.migrate:
            if check_migration_status(conn):
                perform_migration(conn)
        elif args.verify:
            verify_migration(conn)
        elif args.cleanup:
            cleanup_migration(conn)
        else:
            # Default: show status
            check_migration_status(conn)
    finally:
        conn.close()
