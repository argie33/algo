#!/usr/bin/env python3
"""Migration: Add avg_r column to algo_performance_daily.

HIGH-SEVERITY ISSUE FIX: Ensures avg_r (average R-multiple) is pre-computed in the database
rather than recalculated on every dashboard refresh. This column was added to schema.sql
(line 1864) but needs an explicit migration to ensure existing databases are updated.

The loader (load_algo_performance_daily.py) computes and stores avg_r, but if the column
doesn't exist, the dashboard falls back to expensive per-request recalculation.
"""

from migrations.migration_helper import DatabaseContext

DESCRIPTION = "Add avg_r column to algo_performance_daily"

def up():
    """Add avg_r column if it doesn't exist."""
    with DatabaseContext("write") as cur:
        cur.execute("""
            ALTER TABLE algo_performance_daily
            ADD COLUMN IF NOT EXISTS avg_r NUMERIC(6, 3)
        """)

def down():
    """Remove avg_r column (not recommended in production)."""
    with DatabaseContext("write") as cur:
        cur.execute("""
            ALTER TABLE algo_performance_daily
            DROP COLUMN IF EXISTS avg_r
        """)
