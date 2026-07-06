#!/usr/bin/env python3
"""
Local Database Migration Script - Apply missing tables and columns locally

Usage:
    python3 scripts/apply_local_migrations.py
"""

import psycopg2
import os
import sys

def get_db_connection():
    """Get connection to local database."""
    try:
        conn = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'stocks'),
            user=os.environ.get('DB_USER', 'stocks'),
            password=os.environ.get('DB_PASSWORD', ''),
            port=int(os.environ.get('DB_PORT', 5432))
        )
        return conn
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}")
        sys.exit(1)

# All migrations to apply, in order
MIGRATIONS = [
    # SCHEMA FIXES (CODE/DB MISMATCHES)
    ("algo_positions.is_open column", """
        ALTER TABLE algo_positions ADD COLUMN IF NOT EXISTS is_open BOOLEAN
            GENERATED ALWAYS AS (status IN ('open', 'partially_closed')) STORED
    """),

    # CRITICAL TABLES (MISSING IN LOCAL DB)
    ("algo_signals table", """
        CREATE TABLE IF NOT EXISTS algo_signals (
            id SERIAL PRIMARY KEY,
            signal_date DATE NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            source_table VARCHAR(50),
            source_timeframe VARCHAR(20),
            raw_signal VARCHAR(20),
            entry_price DECIMAL(12, 4),
            entry_stage VARCHAR(20),
            signal_active BOOLEAN DEFAULT TRUE,
            signal_quality_score INTEGER,
            risk_score DECIMAL(8, 2),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(signal_date, symbol, source_timeframe)
        );
        CREATE INDEX IF NOT EXISTS idx_algo_signals_symbol_date ON algo_signals(symbol, signal_date DESC);
        CREATE INDEX IF NOT EXISTS idx_algo_signals_entry_stage ON algo_signals(entry_stage) WHERE entry_stage IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_algo_signals_active ON algo_signals(signal_active);
    """),

    ("market_sentiment table", """
        DROP VIEW IF EXISTS market_sentiment CASCADE;
        DROP TABLE IF EXISTS market_sentiment CASCADE;
        CREATE TABLE market_sentiment (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL UNIQUE,
            fear_greed_index DECIMAL(8, 4),
            put_call_ratio DECIMAL(8, 4),
            vix DECIMAL(8, 4),
            sentiment_score DECIMAL(8, 4),
            bullish_pct DECIMAL(8, 2),
            bearish_pct DECIMAL(8, 2),
            neutral_pct DECIMAL(8, 2),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_market_sentiment_date ON market_sentiment(date DESC);
    """),

    ("orchestrator_execution_log table", """
        DROP TABLE IF EXISTS orchestrator_execution_log CASCADE;
        CREATE TABLE orchestrator_execution_log (
            id SERIAL PRIMARY KEY,
            run_id VARCHAR(50) NOT NULL UNIQUE,
            run_date DATE NOT NULL,
            started_at TIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            overall_status VARCHAR(20) NOT NULL,
            phase_results JSONB,
            summary TEXT,
            halt_reason TEXT,
            phases_completed INTEGER,
            phases_halted INTEGER,
            phases_errored INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_run_date ON orchestrator_execution_log(run_date DESC);
        CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_status ON orchestrator_execution_log(overall_status);
        CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_started ON orchestrator_execution_log(started_at DESC);
    """),

    # PENDING MIGRATIONS - data_unavailable on metric tables
    ("quality_metrics.data_unavailable",
     "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"),

    ("growth_metrics.data_unavailable",
     "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"),

    ("value_metrics.data_unavailable",
     "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"),

    ("positioning_metrics.data_unavailable",
     "ALTER TABLE positioning_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"),

    ("stability_metrics.data_unavailable",
     "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"),

    # reason columns
    ("quality_metrics.reason",
     "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS reason VARCHAR(500)"),

    ("stability_metrics.reason",
     "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS reason VARCHAR(500)"),

    ("value_metrics.market_cap_unavailable_reason",
     "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS market_cap_unavailable_reason VARCHAR(255)"),

    ("value_metrics.pe_ratio_unavailable_reason",
     "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS pe_ratio_unavailable_reason VARCHAR(255)"),

    ("value_metrics.pb_ratio_unavailable_reason",
     "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS pb_ratio_unavailable_reason VARCHAR(255)"),

    ("value_metrics.ps_ratio_unavailable_reason",
     "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS ps_ratio_unavailable_reason VARCHAR(255)"),

    ("value_metrics.peg_ratio_unavailable_reason",
     "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS peg_ratio_unavailable_reason VARCHAR(255)"),

    ("value_metrics.dividend_yield_unavailable_reason",
     "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS dividend_yield_unavailable_reason VARCHAR(255)"),

    ("value_metrics.fcf_yield_unavailable_reason",
     "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS fcf_yield_unavailable_reason VARCHAR(255)"),

    ("value_metrics.held_percent_insiders_unavailable_reason",
     "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS held_percent_insiders_unavailable_reason VARCHAR(255)"),

    ("value_metrics.held_percent_institutions_unavailable_reason",
     "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS held_percent_institutions_unavailable_reason VARCHAR(255)"),

    # Technical data
    ("technical_data_daily.atr_50",
     "ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS atr_50 DECIMAL(12, 4)"),

    # market_health_daily columns
    ("market_health_daily.put_call_ratio_data_unavailable",
     "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS put_call_ratio_data_unavailable BOOLEAN DEFAULT FALSE"),

    ("market_health_daily.put_call_ratio_unavailable_reason",
     "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS put_call_ratio_unavailable_reason VARCHAR(255)"),

    ("market_health_daily.yield_curve_data_unavailable",
     "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS yield_curve_data_unavailable BOOLEAN DEFAULT FALSE"),

    ("market_health_daily.yield_curve_unavailable_reason",
     "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS yield_curve_unavailable_reason VARCHAR(255)"),

    ("market_health_daily.fed_rate_data_unavailable",
     "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS fed_rate_data_unavailable BOOLEAN DEFAULT FALSE"),

    ("market_health_daily.fed_rate_unavailable_reason",
     "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS fed_rate_unavailable_reason VARCHAR(255)"),
]

def apply_migrations():
    """Apply all pending migrations."""
    conn = get_db_connection()
    cur = conn.cursor()

    applied = 0
    failed = 0

    print("=" * 80)
    print("LOCAL DATABASE MIGRATION")
    print("=" * 80)

    for desc, migration_sql in MIGRATIONS:
        try:
            cur.execute(migration_sql)
            conn.commit()
            print(f"[OK] {desc}")
            applied += 1
        except psycopg2.errors.DuplicateColumn:
            print(f"[SKIP] {desc} (already exists)")
        except Exception as e:
            print(f"[FAIL] {desc}: {type(e).__name__}: {e}")
            conn.rollback()
            failed += 1

    cur.close()
    conn.close()

    print("\n" + "=" * 80)
    print(f"SUMMARY: {applied} applied, {failed} failed")
    print("=" * 80)

    return failed == 0

if __name__ == '__main__':
    success = apply_migrations()
    sys.exit(0 if success else 1)
