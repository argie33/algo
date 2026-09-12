#!/usr/bin/env python3
"""
Migration 091: Fix options_chains and iv_history schema to match signal code expectations.

- iv_history: Add current_iv, iv_52w_high, iv_52w_low columns
- options_chains: Rename data_date to quote_date, add iv and days_to_expiration columns
"""

import os

import psycopg2


def up():
    """Upgrade: Add missing columns to support options signals."""
    # Map DB_SSL values to psycopg2 SSL modes
    ssl_map = {
        "true": "require",
        "false": "disable",
        "disable": "disable",
        "prefer": "prefer",
        "require": "require",
    }
    db_ssl = ssl_map.get(os.getenv("DB_SSL", "require").lower(), "require")

    db_host = os.getenv("DB_HOST")
    if not db_host:
        raise ValueError("DB_HOST environment variable is required (no localhost fallback for safety)")
    db_user = os.getenv("DB_USER")
    if not db_user:
        raise ValueError("DB_USER environment variable is required (no 'postgres' fallback for safety)")
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        raise ValueError("DB_PASSWORD environment variable is required (no blank fallback for safety)")
    db_name = os.getenv("DB_NAME")
    if not db_name:
        raise ValueError("DB_NAME environment variable is required (no 'algo' fallback for safety)")

    # Connect to database using environment variables
    conn = psycopg2.connect(
        host=db_host,
        port=int(os.getenv("DB_PORT", 5432)),
        user=db_user,
        password=db_password,
        database=db_name,
        sslmode=db_ssl,
    )

    with conn.cursor() as cur:
        # Fix iv_history: Add columns expected by signal_options.py
        cur.execute("""
            ALTER TABLE IF EXISTS iv_history
            ADD COLUMN IF NOT EXISTS current_iv DECIMAL(8, 4),
            ADD COLUMN IF NOT EXISTS iv_52w_high DECIMAL(8, 4),
            ADD COLUMN IF NOT EXISTS iv_52w_low DECIMAL(8, 4);
            """)

        # Fix options_chains: Rename data_date to quote_date and add missing columns
        # First check if data_date exists (backwards compatibility)
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'options_chains' AND column_name = 'data_date'
            """)
        if cur.fetchone():
            # Rename data_date to quote_date
            cur.execute("""
                ALTER TABLE options_chains
                RENAME COLUMN data_date TO quote_date;
                """)

        # Add missing columns. IF EXISTS guard added 2026-09-12 (goal session options audit):
        # options_chains has never had a CREATE TABLE anywhere in this repo's history (the
        # loader this migration shipped alongside, loaders/load_options_chains.py, only ever
        # INSERTed into it too - see migrations/versions/1284_add_delta_to_options_chains.sql,
        # which now actually creates the table). Without IF EXISTS here, this ALTER hard-fails
        # with "relation options_chains does not exist" on any genuinely fresh database, and
        # since migrations/run.py's apply_all_pending() runs in ascending numeric order and
        # stops at the first failure, that would block every migration after this one
        # (numbered 127 through 9999) from ever being applied on a cold start. This only went
        # unnoticed because every already-provisioned environment had the table created
        # out-of-band before this migration first ran there.
        cur.execute("""
            ALTER TABLE IF EXISTS options_chains
            ADD COLUMN IF NOT EXISTS iv DECIMAL(8, 4),
            ADD COLUMN IF NOT EXISTS days_to_expiration DECIMAL(8, 2);
            """)

        # Create index on iv_history for signal lookups. `CREATE INDEX ... ON <table>` still
        # hard-fails if the table itself doesn't exist yet even with IF NOT EXISTS (that only
        # guards the index name, not the table) - both iv_history and options_chains are
        # created later, by migrations 1283/1284, so guard with to_regclass same as the
        # ALTER TABLE fix above.
        cur.execute("SELECT to_regclass('iv_history')")
        if cur.fetchone()[0] is not None:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_iv_history_symbol_date
                ON iv_history(symbol, date DESC);
                """)

        # Create index on options_chains for signal lookups
        cur.execute("SELECT to_regclass('options_chains')")
        if cur.fetchone()[0] is not None:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_options_chains_symbol_quote_date
                ON options_chains(symbol, quote_date DESC);
                """)

    conn.commit()


def down():
    """Downgrade: Revert schema changes (destructive - only for dev)."""
    # Map DB_SSL values to psycopg2 SSL modes
    ssl_map = {
        "true": "require",
        "false": "disable",
        "disable": "disable",
        "prefer": "prefer",
        "require": "require",
    }
    db_ssl = ssl_map.get(os.getenv("DB_SSL", "require").lower(), "require")

    db_host = os.getenv("DB_HOST")
    if not db_host:
        raise ValueError("DB_HOST environment variable is required (no localhost fallback for safety)")
    db_user = os.getenv("DB_USER")
    if not db_user:
        raise ValueError("DB_USER environment variable is required (no 'postgres' fallback for safety)")
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        raise ValueError("DB_PASSWORD environment variable is required (no blank fallback for safety)")
    db_name = os.getenv("DB_NAME")
    if not db_name:
        raise ValueError("DB_NAME environment variable is required (no 'algo' fallback for safety)")

    # Connect to database using environment variables
    conn = psycopg2.connect(
        host=db_host,
        port=int(os.getenv("DB_PORT", 5432)),
        user=db_user,
        password=db_password,
        database=db_name,
        sslmode=db_ssl,
    )

    with conn.cursor() as cur:
        # Drop indexes
        cur.execute("DROP INDEX IF EXISTS idx_iv_history_symbol_date;")
        cur.execute("DROP INDEX IF EXISTS idx_options_chains_symbol_quote_date;")

        # Drop new columns from iv_history
        cur.execute("""
            ALTER TABLE iv_history
            DROP COLUMN IF EXISTS current_iv,
            DROP COLUMN IF EXISTS iv_52w_high,
            DROP COLUMN IF EXISTS iv_52w_low;
            """)

        # Drop new columns from options_chains and rename back
        cur.execute("""
            ALTER TABLE options_chains
            DROP COLUMN IF EXISTS iv,
            DROP COLUMN IF EXISTS days_to_expiration;
            """)
        cur.execute("""
            ALTER TABLE options_chains
            RENAME COLUMN quote_date TO data_date;
            """)

    conn.commit()
