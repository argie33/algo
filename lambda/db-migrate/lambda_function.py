#!/usr/bin/env python3
"""
Lambda function to apply AWS RDS database migrations.

Runs on deployment to apply all pending migrations to the AWS RDS database.
Uses boto3 to connect to RDS via Secrets Manager (no hardcoded credentials).

Deployment: zip this file + boto3 + psycopg2, upload to Lambda
"""

import json

import boto3
import psycopg2

# All migrations needed, in order
MIGRATIONS = [
    # CRITICAL TABLES
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

    # PENDING MIGRATIONS
    ("quality_metrics.data_unavailable", "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"),
    ("growth_metrics.data_unavailable", "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"),
    ("value_metrics.data_unavailable", "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"),
    ("positioning_metrics.data_unavailable", "ALTER TABLE positioning_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"),
    ("stability_metrics.data_unavailable", "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"),
    ("quality_metrics.reason", "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS reason VARCHAR(500)"),
    ("stability_metrics.reason", "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS reason VARCHAR(500)"),
    ("value_metrics.market_cap_unavailable_reason", "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS market_cap_unavailable_reason VARCHAR(255)"),
    ("value_metrics.pe_ratio_unavailable_reason", "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS pe_ratio_unavailable_reason VARCHAR(255)"),
    ("value_metrics.pb_ratio_unavailable_reason", "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS pb_ratio_unavailable_reason VARCHAR(255)"),
    ("value_metrics.ps_ratio_unavailable_reason", "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS ps_ratio_unavailable_reason VARCHAR(255)"),
    ("value_metrics.peg_ratio_unavailable_reason", "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS peg_ratio_unavailable_reason VARCHAR(255)"),
    ("value_metrics.dividend_yield_unavailable_reason", "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS dividend_yield_unavailable_reason VARCHAR(255)"),
    ("value_metrics.fcf_yield_unavailable_reason", "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS fcf_yield_unavailable_reason VARCHAR(255)"),
    ("value_metrics.held_percent_insiders_unavailable_reason", "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS held_percent_insiders_unavailable_reason VARCHAR(255)"),
    ("value_metrics.held_percent_institutions_unavailable_reason", "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS held_percent_institutions_unavailable_reason VARCHAR(255)"),
    ("technical_data_daily.atr_50", "ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS atr_50 DECIMAL(12, 4)"),
    ("market_health_daily.put_call_ratio_data_unavailable", "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS put_call_ratio_data_unavailable BOOLEAN DEFAULT FALSE"),
    ("market_health_daily.put_call_ratio_unavailable_reason", "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS put_call_ratio_unavailable_reason VARCHAR(255)"),
    ("market_health_daily.yield_curve_data_unavailable", "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS yield_curve_data_unavailable BOOLEAN DEFAULT FALSE"),
    ("market_health_daily.yield_curve_unavailable_reason", "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS yield_curve_unavailable_reason VARCHAR(255)"),
    ("market_health_daily.fed_rate_data_unavailable", "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS fed_rate_data_unavailable BOOLEAN DEFAULT FALSE"),
    ("market_health_daily.fed_rate_unavailable_reason", "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS fed_rate_unavailable_reason VARCHAR(255)"),
    ("algo_performance_metrics.avg_win_r", "ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS avg_win_r NUMERIC(8, 4)"),
    ("algo_performance_metrics.avg_loss_r", "ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS avg_loss_r NUMERIC(8, 4)"),
    ("algo_performance_metrics.expectancy", "ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS expectancy NUMERIC(8, 4)"),
]


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
        raise


def lambda_handler(event, context):
    """Lambda entry point - apply all migrations."""
    print("=" * 80)
    print("AWS RDS DATABASE MIGRATION (Lambda)")
    print("=" * 80)

    try:
        print("\n1. Getting RDS credentials from Secrets Manager...")
        creds = get_rds_credentials()
        print(f"   Host: {creds['host']}")

        print("\n2. Connecting to AWS RDS...")
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

        print(f"\n3. Applying {len(MIGRATIONS)} migrations...")
        applied = 0
        skipped = 0
        failed = 0

        for desc, migration_sql in MIGRATIONS:
            try:
                cur.execute(migration_sql)
                conn.commit()
                print(f"   OK      {desc}")
                applied += 1
            except psycopg2.errors.DuplicateTable:
                print(f"   SKIP    {desc} (already exists)")
                skipped += 1
            except Exception as e:
                print(f"   FAIL    {desc}: {str(e)[:80]}")
                conn.rollback()
                failed += 1

        # Verify schema
        print("\n4. Verifying schema...")
        critical_tables = {
            'algo_signals': ['signal_date', 'symbol'],
            'orchestrator_execution_log': ['run_id', 'overall_status'],
        }

        all_good = True
        for table, cols in critical_tables.items():
            try:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = %s AND table_schema = 'public'
                """, (table,))
                existing = {row[0] for row in cur.fetchall()}
                missing = set(cols) - existing
                if missing:
                    print(f"   FAIL    {table}: missing {missing}")
                    all_good = False
                else:
                    print(f"   OK      {table}")
            except Exception as e:
                print(f"   FAIL    {table}: {str(e)[:80]}")
                all_good = False

        cur.close()
        conn.close()

        result = {
            'statusCode': 200 if (failed == 0 and all_good) else 500,
            'applied': applied,
            'skipped': skipped,
            'failed': failed,
            'schema_verified': all_good,
        }

        print(f"\n{'='*80}")
        print(f"COMPLETE: {applied} applied, {skipped} skipped, {failed} failed")
        if all_good:
            print("SCHEMA: All critical tables verified OK")
        else:
            print("SCHEMA: Verification FAILED")
        print("="*80)

        return result

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'error': str(e),
        }


if __name__ == '__main__':
    # For local testing
    result = lambda_handler({}, None)
    print(json.dumps(result, indent=2))
