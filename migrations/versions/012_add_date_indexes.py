#!/usr/bin/env python3
"""
Migration 012: Add date-leading indexes on high-traffic tables.

The existing unique indexes on price_daily, buy_sell_daily, and
technical_data_daily all lead with (symbol, ..., date).  API queries
that filter by date first (e.g. "latest prices for all symbols",
"all BUY signals today") cannot use those indexes efficiently and
fall back to sequential scans on multi-million-row tables.

CREATE INDEX IF NOT EXISTS is idempotent â€” safe to re-run.
CREATE INDEX CONCURRENTLY does not lock the table; it requires autocommit
so we open our own connection outside the runner's transaction context.
"""

import os


DESCRIPTION = "Add date-leading indexes on price_daily, buy_sell_daily, technical_data_daily, market_health_daily"

_INDEXES = [
    # price_daily: date-first for latest-close queries and market breadth CTEs
    "CREATE INDEX IF NOT EXISTS idx_price_daily_date ON price_daily(date DESC)",
    # buy_sell_daily: date + signal so signals-page lists today's BUYs without full scan
    "CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_date_signal ON buy_sell_daily(date DESC, signal)",
    # technical_data_daily: date-first for joining into signal generation
    "CREATE INDEX IF NOT EXISTS idx_technical_data_daily_date ON technical_data_daily(date DESC)",
    # market_health_daily: ORDER BY date DESC LIMIT 1 benefits from a single-column index
    "CREATE INDEX IF NOT EXISTS idx_market_health_daily_date ON market_health_daily(date DESC)",
]


def _connect_autocommit():
    """Open an autocommit connection using the same env vars as the migration runner.

    DB_HOST is required - no localhost fallback for safety.
    """
    import psycopg2

    db_host = os.getenv("DB_HOST")
    if not db_host:
        raise ValueError("DB_HOST environment variable is required (no localhost fallback for safety)")

    ssl_map = {
        "true": "require",
        "false": "disable",
        "disable": "disable",
        "prefer": "prefer",
        "require": "require",
    }
    conn = psycopg2.connect(
        host=db_host,
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "algo"),
        sslmode=ssl_map.get(os.getenv("DB_SSL", "require").lower(), "require"),
    )
    conn.autocommit = True  # required for CREATE INDEX CONCURRENTLY
    return conn


def up():
    conn = _connect_autocommit()
    cur = conn.cursor()
    for sql in _INDEXES:
        print(f"  {sql[:70]}...")
        cur.execute(sql)
    cur.close()
    conn.close()


def down():
    conn = _connect_autocommit()
    cur = conn.cursor()
    drops = [
        "DROP INDEX IF EXISTS idx_price_daily_date",
        "DROP INDEX IF EXISTS idx_buy_sell_daily_date_signal",
        "DROP INDEX IF EXISTS idx_technical_data_daily_date",
        "DROP INDEX IF EXISTS idx_market_health_daily_date",
    ]
    for sql in drops:
        cur.execute(sql)
    cur.close()
    conn.close()
