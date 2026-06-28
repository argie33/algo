#!/usr/bin/env python3
"""
Migration 033: Add NOT NULL constraint to company_profile.sector

ISSUE D-003 FIX: The positions/sectors queries JOIN on company_profile.sector
but allow NULL values, causing missing sectors in results. This migration:

1. Updates 3 rows with NULL sector to 'Industrials' (most common sector)
2. Adds NOT NULL constraint to company_profile.sector column
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Add NOT NULL constraint to company_profile.sector"


def up():
    with DatabaseContext("write") as cur:
        # First, check if there are any NULL values
        cur.execute("SELECT COUNT(*) FROM company_profile WHERE sector IS NULL")
        row = cur.fetchone()
        if row is None or row[0] is None:
            raise RuntimeError("NULL count query failed")
        null_count = row[0]

        if null_count > 0:
            # Update NULL sectors to 'Industrials' (most common sector)
            cur.execute("""
                UPDATE company_profile
                SET sector = 'Industrials'
                WHERE sector IS NULL
            """)

        # Add NOT NULL constraint
        cur.execute("""
            ALTER TABLE company_profile
            ALTER COLUMN sector SET NOT NULL
        """)


def down():
    with DatabaseContext("write") as cur:
        # Remove NOT NULL constraint
        cur.execute("""
            ALTER TABLE company_profile
            ALTER COLUMN sector DROP NOT NULL
        """)
