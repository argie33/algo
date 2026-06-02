#!/usr/bin/env python3
"""
Migration 008: Add user_id to algo_notifications for row-level access control.

SECURITY FIX: algo_notifications previously had no user_id field, allowing any
authenticated user to read/modify/delete ANY notification. This migration adds
user_id to enable row-level security checks.

Existing notifications are marked with user_id=NULL (system-wide, no owner).
Going forward, all notifications will include the creating user's ID.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.database_context import DatabaseContext

DESCRIPTION = "Add user_id to algo_notifications table for row-level access control"


def up():
    with DatabaseContext('write') as cur:
        # Add user_id column (nullable for backward compatibility with existing notifications)
        cur.execute("""
            ALTER TABLE algo_notifications
            ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)
        """)

        # Create an index for faster user-specific notification queries
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_notifications_user_id
            ON algo_notifications(user_id) WHERE user_id IS NOT NULL
        """)

        # Create a composite index for common queries: user_id + created_at (for sorting)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_notifications_user_created
            ON algo_notifications(user_id, created_at DESC) WHERE user_id IS NOT NULL
        """)


def down():
    with DatabaseContext('write') as cur:
        # Drop indexes first
        cur.execute("""
            DROP INDEX IF EXISTS idx_algo_notifications_user_created
        """)

        cur.execute("""
            DROP INDEX IF EXISTS idx_algo_notifications_user_id
        """)

        # Drop column
        cur.execute("""
            ALTER TABLE algo_notifications
            DROP COLUMN IF EXISTS user_id
        """)
