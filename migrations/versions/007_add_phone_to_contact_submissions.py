#!/usr/bin/env python3
"""
Migration 007: Add phone column to contact_submissions table.

The contact form accepts an optional phone number but the column was missing
from the initial schema, causing 500 errors on contact form submissions.
"""

from utils.db.context import DatabaseContext


DESCRIPTION = "Add phone column to contact_submissions table"


def up():
    with DatabaseContext("write") as cur:
        cur.execute("""
            ALTER TABLE contact_submissions
            ADD COLUMN IF NOT EXISTS phone VARCHAR(20)
        """)


def down():
    with DatabaseContext("write") as cur:
        cur.execute("""
            ALTER TABLE contact_submissions
            DROP COLUMN IF EXISTS phone
        """)
