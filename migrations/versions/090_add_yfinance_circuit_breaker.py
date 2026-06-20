#!/usr/bin/env python3
"""
Migration 090: Add yfinance IP circuit breaker table

Creates a table to track the shared IP ban state across all 6 ECS tasks.
When any task detects rate limiting (429/401), it sets a flag here with
exponential backoff. All other tasks check this flag before making requests.

Purpose: Prevents cascading IP bans by coordinating backoff across all tasks.
"""

from migrations.migration_helper import DatabaseContext


DESCRIPTION = "Add yfinance_ip_ban table for coordinating rate limiting across ECS tasks"


def up():
    """Create yfinance_ip_ban table with shared state tracking."""
    with DatabaseContext("write") as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS yfinance_ip_ban (
                state_key TEXT PRIMARY KEY,
                is_banned BOOLEAN DEFAULT FALSE,
                failure_count INTEGER DEFAULT 0,
                ban_until TIMESTAMP WITH TIME ZONE,
                last_error_time TIMESTAMP WITH TIME ZONE,
                last_success_time TIMESTAMP WITH TIME ZONE,
                reason TEXT DEFAULT '',
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_yfinance_ip_ban_updated
            ON yfinance_ip_ban(updated_at DESC);
        """)

        cur.execute("""
            INSERT INTO yfinance_ip_ban (state_key, is_banned, failure_count, reason)
            VALUES ('shared', FALSE, 0, 'Initial state')
            ON CONFLICT (state_key) DO NOTHING;
        """)

    return True


def down():
    """Drop yfinance_ip_ban table."""
    with DatabaseContext("write") as cur:
        cur.execute("DROP TABLE IF EXISTS yfinance_ip_ban CASCADE;")

    return True
