#!/usr/bin/env python3
"""
Migration 092: Add backtest_runs and backtest_trades tables for storing backtest results.

- backtest_runs: Summary statistics for each backtest run
- backtest_trades: Individual trades from backtest runs
"""

import os

import psycopg2


def up():
    """Upgrade: Create backtest_runs and backtest_trades tables."""
    ssl_map = {
        "true": "require",
        "false": "disable",
        "disable": "disable",
        "prefer": "prefer",
        "require": "require",
    }
    db_ssl = ssl_map.get(os.getenv("DB_SSL", "require").lower(), "require")

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        dbname=os.getenv("DB_NAME", "postgres"),
        sslmode=db_ssl,
    )
    cur = conn.cursor()

    try:
        # Create backtest_runs table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id SERIAL PRIMARY KEY,
                run_name VARCHAR(255),
                strategy_name VARCHAR(255) NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                initial_capital NUMERIC(15, 2) NOT NULL,
                final_value NUMERIC(15, 2) NOT NULL,
                total_return NUMERIC(10, 4),
                annual_return NUMERIC(10, 4),
                max_drawdown NUMERIC(10, 4),
                sharpe_ratio NUMERIC(10, 4),
                win_rate NUMERIC(10, 4),
                profit_factor NUMERIC(10, 4),
                num_trades INTEGER,
                num_winning_trades INTEGER,
                num_losing_trades INTEGER,
                avg_win NUMERIC(10, 4),
                avg_loss NUMERIC(10, 4),
                largest_win NUMERIC(10, 4),
                largest_loss NUMERIC(10, 4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Create backtest_trades table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_trades (
                trade_id SERIAL PRIMARY KEY,
                run_id INTEGER NOT NULL REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
                symbol VARCHAR(20) NOT NULL,
                entry_date DATE NOT NULL,
                exit_date DATE,
                entry_price NUMERIC(12, 4) NOT NULL,
                exit_price NUMERIC(12, 4),
                quantity INTEGER NOT NULL,
                entry_value NUMERIC(15, 2) NOT NULL,
                exit_value NUMERIC(15, 2),
                profit_loss NUMERIC(15, 2),
                profit_loss_percent NUMERIC(10, 4),
                trade_outcome VARCHAR(10),
                holding_days INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Create index on backtest_trades run_id for faster queries
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_backtest_trades_run_id
            ON backtest_trades(run_id)
            """
        )

        # Create index on backtest_trades symbol and date for analysis
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_backtest_trades_symbol_date
            ON backtest_trades(symbol, entry_date)
            """
        )

        conn.commit()
        print("✓ Migration 092: backtest_runs and backtest_trades tables created")

    except psycopg2.errors.DuplicateTable:
        conn.rollback()
        print("✓ Migration 092: Tables already exist (idempotent)")

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Migration 092 failed: {e}") from e

    finally:
        cur.close()
        conn.close()


def down():
    """Downgrade: Drop backtest tables."""
    ssl_map = {
        "true": "require",
        "false": "disable",
        "disable": "disable",
        "prefer": "prefer",
        "require": "require",
    }
    db_ssl = ssl_map.get(os.getenv("DB_SSL", "require").lower(), "require")

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        dbname=os.getenv("DB_NAME", "postgres"),
        sslmode=db_ssl,
    )
    cur = conn.cursor()

    try:
        cur.execute("DROP TABLE IF EXISTS backtest_trades CASCADE")
        cur.execute("DROP TABLE IF EXISTS backtest_runs CASCADE")
        conn.commit()
        print("✓ Migration 092 reversed: backtest tables dropped")

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Downgrade for migration 092 failed: {e}") from e

    finally:
        cur.close()
        conn.close()
