#!/usr/bin/env python3
"""
Migration 010: Fix user_dashboard_settings for Cognito authentication.

The original schema used user_id INTEGER FK -> users(id), but the app uses
Cognito subs (UUID strings) as user identities, not rows in the users table.
Additionally, the settings route was using pgp_sym_encrypt which requires the
pgcrypto extension (not installed).

This migration drops and recreates user_dashboard_settings with:
- user_id VARCHAR(255) PRIMARY KEY (Cognito sub, no FK)
- preferences JSONB DEFAULT '{}' (plain JSON, no encryption needed for UI prefs)
- theme default changed to 'dark' (matches app default)

Safe to run: the old table was non-functional (settings always returned 503),
so there are no valid rows to preserve.
"""

from migrations.migration_helper import DatabaseContext

DESCRIPTION = "Fix user_dashboard_settings: VARCHAR user_id, remove pgcrypto dependency"

def up():
    with DatabaseContext('write') as cur:
        cur.execute("""
            DROP TABLE IF EXISTS user_dashboard_settings CASCADE
        """)
        cur.execute("""
            CREATE TABLE user_dashboard_settings (
                user_id VARCHAR(255) PRIMARY KEY,
                theme VARCHAR(20) DEFAULT 'dark',
                notifications BOOLEAN DEFAULT TRUE,
                preferences JSONB DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

def down():
    with DatabaseContext('write') as cur:
        cur.execute("DROP TABLE IF EXISTS user_dashboard_settings CASCADE")
        cur.execute("""
            CREATE TABLE user_dashboard_settings (
                user_id INTEGER PRIMARY KEY,
                theme VARCHAR(20) DEFAULT 'light',
                notifications BOOLEAN DEFAULT TRUE,
                preferences JSONB,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

