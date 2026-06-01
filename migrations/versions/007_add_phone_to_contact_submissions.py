#!/usr/bin/env python3
"""
Migration 007: Add phone column to contact_submissions table.

The contact form accepts an optional phone number but the column was missing
from the initial schema, causing 500 errors on contact form submissions.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.database_context import DatabaseContext

DESCRIPTION = "Add phone column to contact_submissions table"


def up():
    with DatabaseContext('write') as cur:
        cur.execute("""
            ALTER TABLE contact_submissions
            ADD COLUMN IF NOT EXISTS phone VARCHAR(20)
        """)


def down():
    with DatabaseContext('write') as cur:
        cur.execute("""
            ALTER TABLE contact_submissions
            DROP COLUMN IF EXISTS phone
        """)
