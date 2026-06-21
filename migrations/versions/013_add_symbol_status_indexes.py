#!/usr/bin/env python3
"""
Migration 013: Add symbol/status indexes for frequent WHERE clauses.

Analysis of query patterns shows many lookups on:
- algo_trades: WHERE symbol AND status (open position lookups)
- algo_positions: WHERE symbol AND status (portfolio queries)
- alpaca_import_failures: WHERE symbol AND resolved (sync errors)
- pending_exits: WHERE symbol (exit lookups)
- signal_quality_scores: WHERE date AND symbol (signal validation)

These composite indexes speed up the most frequently executed queries
and reduce sequential scans on large tables.

CREATE INDEX CONCURRENTLY does not lock the table; it requires autocommit
so we open our own connection outside the runner's transaction context.
"""

import os


DESCRIPTION = "Add symbol/status indexes for frequent WHERE clauses in trading operations"

_INDEXES = [
    # algo_trades: (symbol, status) for fast lookup of open positions
    "CREATE INDEX IF NOT EXISTS idx_algo_trades_symbol_status ON algo_trades(symbol, status) WHERE status IN ('open', 'active')",

    # algo_positions: (symbol, status) for portfolio management queries
    "CREATE INDEX IF NOT EXISTS idx_algo_positions_symbol_status ON algo_positions(symbol, status) WHERE status IN ('open', 'active')",

    # alpaca_import_failures: (symbol, resolved) for sync error detection
    "CREATE INDEX IF NOT EXISTS idx_alpaca_import_failures_symbol_resolved ON alpaca_import_failures(symbol, resolved) WHERE resolved = FALSE",

    # pending_exits: symbol-only for quick exit lookups
    "CREATE INDEX IF NOT EXISTS idx_pending_exits_symbol ON pending_exits(symbol)",

    # signal_quality_scores: (date, symbol) for signal validation and scoring
    "CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_date_symbol ON signal_quality_scores(date DESC, symbol)",

    # market_health_daily: (symbol, date) for market breadth/regime queries
    "CREATE INDEX IF NOT EXISTS idx_market_health_daily_symbol_date ON market_health_daily(symbol, date DESC)",
]


def _connect_autocommit():
    """Open an autocommit connection using the same env vars as the migration runner.

    DB_HOST is required - no localhost fallback for safety.
    """
    import psycopg2

    db_host = os.getenv("DB_HOST")
    if not db_host:
        raise ValueError(
            "DB_HOST environment variable is required (no localhost fallback for safety)"
        )

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
        "DROP INDEX IF EXISTS idx_algo_trades_symbol_status",
        "DROP INDEX IF EXISTS idx_algo_positions_symbol_status",
        "DROP INDEX IF EXISTS idx_alpaca_import_failures_symbol_resolved",
        "DROP INDEX IF EXISTS idx_pending_exits_symbol",
        "DROP INDEX IF EXISTS idx_signal_quality_scores_date_symbol",
        "DROP INDEX IF EXISTS idx_market_health_daily_symbol_date",
    ]
    for sql in drops:
        cur.execute(sql)
    cur.close()
    conn.close()
