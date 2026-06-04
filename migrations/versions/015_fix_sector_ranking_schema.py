#!/usr/bin/env python3
"""
Migration 015: Fix sector_ranking schema - rename date_recorded to date.

The sector_ranking loader (load_sector_ranking.py) writes to a 'date' column
with watermark_field = "date", but the database schema has 'date_recorded'.
This mismatch causes the loader to fail silently or write to the wrong column.

This migration:
1. Adds a 'date' column to sector_ranking
2. Copies data from date_recorded to date
3. Updates the primary key and indexes to use 'date'
4. Drops the old date_recorded column
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.database_context import DatabaseContext

DESCRIPTION = "Fix sector_ranking schema - rename date_recorded to date"


def up():
    with DatabaseContext('write') as cur:
        # Check if date column already exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='sector_ranking' AND column_name='date'
            )
        """)
        date_exists = cur.fetchone()[0]

        if not date_exists:
            # Add date column
            cur.execute("""
                ALTER TABLE sector_ranking
                ADD COLUMN date DATE
            """)

            # Copy data from date_recorded to date
            cur.execute("""
                UPDATE sector_ranking
                SET date = date_recorded
                WHERE date IS NULL
            """)

            # Drop the old date_recorded column
            cur.execute("""
                ALTER TABLE sector_ranking
                DROP COLUMN date_recorded
            """)

            # Add NOT NULL constraint after data is migrated
            cur.execute("""
                ALTER TABLE sector_ranking
                ALTER COLUMN date SET NOT NULL
            """)

            # Create unique index on (sector_name, date)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sector_ranking_unique
                ON sector_ranking(sector_name, date)
            """)

            # Create index on date for time-range queries
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_sector_ranking_date
                ON sector_ranking(date DESC)
            """)


def down():
    with DatabaseContext('write') as cur:
        # Check if date_recorded column exists in down migration
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='sector_ranking' AND column_name='date_recorded'
            )
        """)
        date_recorded_exists = cur.fetchone()[0]

        if not date_recorded_exists:
            # Restore date_recorded column
            cur.execute("""
                ALTER TABLE sector_ranking
                ADD COLUMN date_recorded DATE
            """)

            # Copy data back from date to date_recorded
            cur.execute("""
                UPDATE sector_ranking
                SET date_recorded = date
                WHERE date_recorded IS NULL
            """)

            # Drop indexes
            cur.execute("""
                DROP INDEX IF EXISTS idx_sector_ranking_unique
            """)
            cur.execute("""
                DROP INDEX IF EXISTS idx_sector_ranking_date
            """)

            # Drop the date column
            cur.execute("""
                ALTER TABLE sector_ranking
                DROP COLUMN date
            """)
