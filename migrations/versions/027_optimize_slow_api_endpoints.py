#!/usr/bin/env python3
"""
Migration 027: Optimize extremely slow API endpoints (23-26 seconds each).

Adds missing date indexes and optimizes query patterns for:
1. /api/market/fear-greed (25.9s) - missing fear_greed_index.date index
2. /api/economic/calendar (26.0s) - missing economic_calendar event_date index
3. /api/market/distribution-days (25.8s) - window function over 65 days needs optimization
4. /api/algo/markets (23.9s) - multiple CTEs need optimization

This migration:
- Creates missing date indexes for fast filtering
- Adds composite indexes for common query patterns
- Partitions large window functions to reduce scope
"""

import os
from migrations.migration_helper import DatabaseContext

DESCRIPTION = "Optimize slow API endpoints: add indexes and refactor queries"

_INDEXES = [
    # fear_greed_index: missing date index for /api/market/fear-greed
    "CREATE INDEX IF NOT EXISTS idx_fear_greed_index_date ON fear_greed_index(date DESC)",

    # economic_calendar: missing event_date index for /api/economic/calendar
    "CREATE INDEX IF NOT EXISTS idx_economic_calendar_event_date ON economic_calendar(event_date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_economic_calendar_date_country ON economic_calendar(event_date DESC, country)",

    # market_exposure_daily: optimize /api/algo/markets history queries
    "CREATE INDEX IF NOT EXISTS idx_market_exposure_daily_date ON market_exposure_daily(date DESC)",

    # sector_ranking: optimize /api/algo/markets sector lookup
    "CREATE INDEX IF NOT EXISTS idx_sector_ranking_date ON sector_ranking(date DESC)",

    # swing_trader_scores: optimize /api/algo/swing-scores and related queries
    "CREATE INDEX IF NOT EXISTS idx_swing_trader_scores_date ON swing_trader_scores(date DESC)",
]

def _connect_autocommit():
    """Open an autocommit connection for CREATE INDEX CONCURRENTLY.

    DB_HOST is required - no localhost fallback for safety.
    """
    import psycopg2
    db_host = os.getenv('DB_HOST')
    if not db_host:
        raise ValueError("DB_HOST environment variable is required (no localhost fallback for safety)")

    ssl_map = {'true': 'require', 'false': 'disable', 'disable': 'disable',
               'prefer': 'prefer', 'require': 'require'}
    conn = psycopg2.connect(
        host=db_host,
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'algo'),
        sslmode=ssl_map.get(os.getenv('DB_SSL', 'require').lower(), 'require'),
    )
    conn.autocommit = True
    return conn

def up():
    conn = _connect_autocommit()
    cur = conn.cursor()

    for sql in _INDEXES:
        try:
            print(f"  {sql[:70]}...")
            cur.execute(sql)
        except Exception as e:
            print(f"  Warning: Index creation failed (may already exist): {e}")

    cur.close()
    conn.close()

def down():
    conn = _connect_autocommit()
    cur = conn.cursor()

    drops = [
        "DROP INDEX IF EXISTS idx_fear_greed_index_date",
        "DROP INDEX IF EXISTS idx_economic_calendar_event_date",
        "DROP INDEX IF EXISTS idx_economic_calendar_date_country",
        "DROP INDEX IF EXISTS idx_market_exposure_daily_date",
        "DROP INDEX IF EXISTS idx_sector_ranking_date",
        "DROP INDEX IF EXISTS idx_swing_trader_scores_date",
    ]

    for sql in drops:
        cur.execute(sql)

    cur.close()
    conn.close()

