#!/usr/bin/env python3
"""
Migration 032: Add index on data_patrol_log(created_at DESC) to fix COUNT(*) timeouts.

ISSUE D-002 FIX: data_patrol_log lacks index on (created_at DESC), causing COUNT(*) queries
to timeout during pagination and log retrieval operations.

The /api/algo/data-patrol endpoint executes:
  1. SELECT COUNT(*) FROM data_patrol_log (full table scan - SLOW)
  2. SELECT ... FROM data_patrol_log ORDER BY created_at DESC LIMIT/OFFSET (no index - SLOW)

This migration adds a descending index on created_at to optimize both operations. The DESC
order matches the query pattern (ORDER BY created_at DESC).

Related:
  - Existing idx_data_patrol_log_severity compound index is (severity, created_at DESC)
    but only filters rows where severity IN ('error', 'critical'), so generic COUNT(*)
    queries still scan the entire table
  - This index unblocks patrol log queries regardless of severity
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

DESCRIPTION = "Add index on data_patrol_log(created_at DESC) to fix COUNT(*) query timeouts"

_INDEXES = [
    # Primary index: created_at DESC for COUNT(*) and ORDER BY queries
    # This unblocks /api/algo/data-patrol pagination and log retrieval
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_data_patrol_log_created_at ON data_patrol_log(created_at DESC)",
]

def _connect_autocommit():
    """Open an autocommit connection for CREATE INDEX CONCURRENTLY.

    DB_HOST is required - no localhost fallback for safety.
    """
    import psycopg2
    db_host = os.getenv('DB_HOST')
    if not db_host:
        raise ValueError("DB_HOST environment variable is required (no localhost fallback for safety)")

    ssl_map = {'true': 'require', 'false': 'disable', 'disable': 'disable',
               'prefer': 'prefer', 'require': 'require'}
    conn = psycopg2.connect(
        host=db_host,
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'algo'),
        sslmode=ssl_map.get(os.getenv('DB_SSL', 'require').lower(), 'require'),
    )
    conn.autocommit = True
    return conn

def up():
    """Add index on data_patrol_log.created_at (DESC)."""
    conn = _connect_autocommit()
    cur = conn.cursor()

    for sql in _INDEXES:
        try:
            print(f"  {sql[:80]}...")
            cur.execute(sql)
        except Exception as e:
            print(f"  Warning: Index creation failed (may already exist): {e}")

    cur.close()
    conn.close()

def down():
    """Remove index on data_patrol_log.created_at."""
    conn = _connect_autocommit()
    cur = conn.cursor()

    drops = [
        "DROP INDEX IF EXISTS idx_data_patrol_log_created_at",
    ]

    for sql in drops:
        cur.execute(sql)

    cur.close()
    conn.close()
