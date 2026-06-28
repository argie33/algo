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

    # Connect to database using environment variables
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "algo"),
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

        # Add missing columns
        cur.execute("""
            ALTER TABLE options_chains
            ADD COLUMN IF NOT EXISTS iv DECIMAL(8, 4),
            ADD COLUMN IF NOT EXISTS days_to_expiration DECIMAL(8, 2);
            """)

        # Create index on iv_history for signal lookups
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_iv_history_symbol_date
            ON iv_history(symbol, date DESC);
            """)

        # Create index on options_chains for signal lookups
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

    # Connect to database using environment variables
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "algo"),
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
