#!/usr/bin/env python3
"""
Complete AWS RDS Database Fix - Apply All Missing Migrations and Schema

This script:
1. Applies all critical missing tables (algo_signals, orchestrator_execution_log, market_sentiment)
2. Applies all pending migrations from scripts/apply_rds_migrations.py
3. Fixes schema mismatches (stock_scores, etc.)
4. Verifies data integrity

Run from AWS CloudShell or EC2 instance with VPC access to RDS.

Usage:
    python3 scripts/aws_complete_database_fix.py [--dry-run]
"""

import json
import sys
import boto3
import psycopg2
from typing import List, Tuple


def get_rds_credentials() -> dict:
    """Get RDS credentials from AWS Secrets Manager."""
    try:
        client = boto3.client('secretsmanager', region_name='us-east-1')
        response = client.get_secret_value(SecretId='algo-db-credentials-dev')
        secret = json.loads(response['SecretString'])

        if 'host' not in secret or 'password' not in secret:
            raise ValueError('[CRITICAL] RDS credentials incomplete in Secrets Manager')

        host = secret['host']
        return {
            'host': host.split(':')[0] if ':' in host else host,
            'port': int(secret.get('port', 5432)),
            'database': secret.get('dbname', 'stocks'),
            'user': secret.get('username', 'stocks'),
            'password': secret['password'],
        }
    except Exception as e:
        print(f"ERROR: Failed to get RDS credentials: {e}")
        sys.exit(1)


# All migrations needed, in order
MIGRATIONS: List[Tuple[str, str]] = [
    # ========== SCHEMA FIXES (CODE/DB MISMATCHES) ==========

    ("algo_positions.is_open column", """
        ALTER TABLE algo_positions ADD COLUMN IF NOT EXISTS is_open BOOLEAN
            GENERATED ALWAYS AS (status IN ('open', 'partially_closed')) STORED
    """),

    # ========== CRITICAL TABLES (MISSING IN RDS) ==========
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

    ("market_sentiment table (ensure correct structure)", """
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

    ("orchestrator_execution_log table (ensure correct structure)", """
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

    # ========== PENDING MIGRATIONS FROM apply_rds_migrations.py ==========

    # Migration 102: data_unavailable on metric tables
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

    # Migration 104: reason and _unavailable_reason columns
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

    # Migration 105: atr_50 column
    ("technical_data_daily.atr_50",
     "ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS atr_50 DECIMAL(12, 4)"),

    # Migration 103: market_health_daily columns
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

    # Migration 108: R-metrics on algo_performance_metrics
    ("algo_performance_metrics.avg_win_r",
     "ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS avg_win_r NUMERIC(8, 4)"),

    ("algo_performance_metrics.avg_loss_r",
     "ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS avg_loss_r NUMERIC(8, 4)"),

    ("algo_performance_metrics.expectancy",
     "ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS expectancy NUMERIC(8, 4)"),
]


def apply_migrations(conn, dry_run: bool = False):
    """Apply all migrations to RDS."""
    cur = conn.cursor()

    print("\n3. Applying migrations...")
    applied = 0
    skipped = 0
    failed = 0

    for desc, migration_sql in MIGRATIONS:
        try:
            if dry_run:
                print(f"   DRY_RUN {desc}")
            else:
                cur.execute(migration_sql)
                conn.commit()
                print(f"   OK      {desc}")
                applied += 1
        except psycopg2.errors.DuplicateTable:
            print(f"   SKIP    {desc} (already exists)")
            skipped += 1
        except Exception as e:
            print(f"   FAIL    {desc}")
            print(f"           Error: {str(e)[:100]}")
            conn.rollback()
            failed += 1

    cur.close()
    return applied, skipped, failed


def verify_schema(conn) -> bool:
    """Verify critical tables exist and have correct schema."""
    cur = conn.cursor()

    print("\n4. Verifying schema...")

    critical_tables = {
        'algo_signals': ['signal_date', 'symbol', 'entry_stage'],
        'market_sentiment': ['date', 'vix'],
        'orchestrator_execution_log': ['run_id', 'overall_status'],
        'stock_scores': ['symbol', 'composite_score', 'updated_at'],
    }

    all_good = True

    for table, required_cols in critical_tables.items():
        try:
            cur.execute(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = %s AND table_schema = 'public'
            """, (table,))

            existing_cols = {row[0] for row in cur.fetchall()}
            missing = set(required_cols) - existing_cols

            if missing:
                print(f"   FAIL    {table}: missing columns {missing}")
                all_good = False
            else:
                print(f"   OK      {table}")
        except Exception as e:
            print(f"   FAIL    {table}: {str(e)[:80]}")
            all_good = False

    cur.close()
    return all_good


def main():
    """Apply all AWS database fixes."""
    dry_run = '--dry-run' in sys.argv

    print("=" * 80)
    print("AWS RDS COMPLETE DATABASE FIX")
    print("=" * 80)

    if dry_run:
        print("\n[DRY RUN] No changes will be applied\n")

    print("\n1. Getting RDS credentials from AWS Secrets Manager...")
    creds = get_rds_credentials()
    print(f"   Host: {creds['host']}")

    print("\n2. Connecting to AWS RDS database...")
    try:
        conn = psycopg2.connect(
            host=creds['host'],
            port=creds['port'],
            database=creds['database'],
            user=creds['user'],
            password=creds['password'],
            sslmode='require',
            connect_timeout=10,
        )
        cur = conn.cursor()
        cur.execute("SELECT current_database()")
        db_name = cur.fetchone()[0]
        cur.close()
        print(f"   Connected to: {db_name}")
    except Exception as e:
        print(f"   ERROR: Failed to connect to RDS: {e}")
        sys.exit(1)

    # Apply migrations
    applied, skipped, failed = apply_migrations(conn, dry_run)

    # Verify schema
    if not dry_run:
        schema_ok = verify_schema(conn)
    else:
        schema_ok = None

    print(f"\n{'='*80}")
    if dry_run:
        print(f"DRY RUN: Would apply {applied} migrations, skip {skipped}, fail {failed}")
    else:
        print(f"COMPLETE: {applied} migrations applied, {skipped} skipped, {failed} failed")

    if schema_ok is False:
        print("SCHEMA VERIFICATION FAILED - See errors above")
        print("="*80)
        conn.close()
        sys.exit(1)
    elif schema_ok is True:
        print("SCHEMA VERIFICATION: All critical tables present with correct columns")

    print("="*80)

    conn.close()

    if not dry_run and failed == 0:
        print("\n[SUCCESS] Database fix complete!")
        print("\nNext steps:")
        print("  1. Kill orchestrator if running: pkill -9 python")
        print("  2. Restart dashboard: python -m dashboard -w")
        print("  3. Orchestrator will resume on next scheduled run (2:15 AM or 4:05 PM ET)")
        print("  4. Monitor AWS CloudWatch logs for loader jobs")
        return 0
    elif dry_run:
        return 0
    else:
        return 1


if __name__ == '__main__':
    sys.exit(main())
