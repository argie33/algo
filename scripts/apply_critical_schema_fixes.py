#!/usr/bin/env python3
"""
Apply critical missing schema migrations to RDS.

These tables are BLOCKING the entire system:
- algo_signals: Required for dashboard signals display
- orchestrator_execution_log: Required for orchestrator to run
- market_sentiment: Required for market data endpoints

Run from AWS CloudShell to connect to RDS.
"""

import json
import sys
import boto3
import psycopg2


def get_rds_credentials():
    """Get RDS credentials from AWS Secrets Manager."""
    try:
        client = boto3.client('secretsmanager', region_name='us-east-1')
        response = client.get_secret_value(SecretId='algo-db-credentials-dev')
        secret = json.loads(response['SecretString'])

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


CRITICAL_MIGRATIONS = [
    # Migration 052: algo_signals table
    (
        "algo_signals table",
        """
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(signal_date, symbol, source_timeframe)
        );

        CREATE INDEX IF NOT EXISTS idx_algo_signals_symbol_date ON algo_signals(symbol, signal_date DESC);
        CREATE INDEX IF NOT EXISTS idx_algo_signals_entry_stage ON algo_signals(entry_stage) WHERE entry_stage IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_algo_signals_active ON algo_signals(signal_active);
        """
    ),
    # Migration 066: orchestrator_execution_log
    (
        "orchestrator_execution_log table",
        """
        CREATE TABLE IF NOT EXISTS orchestrator_execution_log (
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_run_date ON orchestrator_execution_log(run_date DESC);
        CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_status ON orchestrator_execution_log(overall_status);
        CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_started ON orchestrator_execution_log(started_at DESC);
        """
    ),
    # market_sentiment table
    (
        "market_sentiment table",
        """
        CREATE TABLE IF NOT EXISTS market_sentiment (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL UNIQUE,
            fear_greed_index DECIMAL(8, 4),
            put_call_ratio DECIMAL(8, 4),
            vix DECIMAL(8, 4),
            sentiment_score DECIMAL(8, 4),
            bullish_pct DECIMAL(8, 2),
            bearish_pct DECIMAL(8, 2),
            neutral_pct DECIMAL(8, 2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    ),
]


def apply_migrations():
    """Apply critical schema migrations to RDS."""
    print("=" * 80)
    print("CRITICAL SCHEMA MIGRATION - UNBLOCK SYSTEM DATA FLOWS")
    print("=" * 80)

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
        print(f"   Connected to: {db_name}")
    except Exception as e:
        print(f"   ERROR: Failed to connect to RDS: {e}")
        sys.exit(1)

    print(f"\n3. Applying {len(CRITICAL_MIGRATIONS)} critical migrations...")
    applied = 0
    failed = 0

    for desc, migration_sql in CRITICAL_MIGRATIONS:
        try:
            cur.execute(migration_sql)
            conn.commit()
            print(f"   OK   {desc}")
            applied += 1
        except Exception as e:
            print(f"   FAIL {desc}: {e}")
            conn.rollback()
            failed += 1

    print(f"\n{'=' * 80}")
    print(f"COMPLETE: {applied} migrations applied, {failed} failed")
    print(f"{'=' * 80}")

    if applied == len(CRITICAL_MIGRATIONS):
        print("\n[SUCCESS] All critical tables created!")
        print("\nNext steps:")
        print("  1. Stop orchestrator if running: pkill -9 python")
        print("  2. Restart dashboard: python -m dashboard -w")
        print("  3. Check dashboard for signals and data")

    cur.close()
    conn.close()

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(apply_migrations())
