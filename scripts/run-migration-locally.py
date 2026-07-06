#!/usr/bin/env python3
"""
Run AWS RDS database migrations from local machine or CloudShell.
This script has better error handling and will work from locations with network access to RDS.

Usage:
    python3 scripts/run-migration-locally.py
"""

import json
import sys
import os
import time
import boto3
import psycopg2
import psycopg2.errors
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


MIGRATIONS: List[Tuple[str, str]] = [
    ("algo_positions.is_open column", """
        ALTER TABLE algo_positions ADD COLUMN IF NOT EXISTS is_open BOOLEAN
            GENERATED ALWAYS AS (status IN ('open', 'partially_closed')) STORED
    """),
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
    ("quality_metrics.reason",
     "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS reason VARCHAR(500)"),
    ("stability_metrics.reason",
     "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS reason VARCHAR(500)"),
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


def main():
    """Apply AWS database fixes."""
    print("=" * 80)
    print("AWS RDS DATABASE FIX - LOCAL EXECUTION")
    print("=" * 80)

    print("\n1. Getting RDS credentials from AWS Secrets Manager...")
    creds = get_rds_credentials()
    print(f"   Host: {creds['host']}")

    print("\n2. Connecting to AWS RDS database...")
    max_retries = 3
    conn = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"   Attempt {attempt}/{max_retries}...")
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
            break
        except psycopg2.OperationalError as e:
            if attempt < max_retries:
                print(f"   Connection failed: {str(e)[:80]}...")
                print(f"   Retrying in 2 seconds...")
                time.sleep(2)
            else:
                print(f"   ERROR: Failed to connect after {max_retries} attempts")
                print(f"   Last error: {e}")
                sys.exit(1)
        except Exception as e:
            print(f"   ERROR: {type(e).__name__}: {e}")
            sys.exit(1)

    if not conn:
        print("   ERROR: Could not establish connection")
        sys.exit(1)

    # Apply migrations
    applied, skipped, failed = apply_migrations(conn, dry_run=False)

    # Verify critical tables exist
    print(f"\n4. Verifying schema...")
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM algo_signals")
        signals_count = cur.fetchone()[0]
        print(f"   OK      algo_signals ({signals_count} records)")

        cur.execute("SELECT COUNT(*) FROM market_sentiment")
        sentiment_count = cur.fetchone()[0]
        print(f"   OK      market_sentiment ({sentiment_count} records)")

        schema_ok = True
    except Exception as e:
        print(f"   FAIL    Schema verification: {str(e)[:80]}")
        schema_ok = False

    cur.close()
    conn.close()

    print(f"\n{'='*80}")
    print(f"COMPLETE: {applied} migrations applied, {skipped} skipped, {failed} failed")

    if schema_ok:
        print("SCHEMA VERIFICATION: All critical tables verified")
    else:
        print("SCHEMA VERIFICATION: Some tables missing")

    print("=" * 80)

    if failed == 0 and schema_ok:
        print("\n[SUCCESS] Database fix complete!")
        print("\nNext steps:")
        print("  1. Restart dashboard: pkill -9 python && python -m dashboard -w")
        print("  2. Orchestrator will run on schedule (9:30 AM, 1 PM, 3 PM, 5:30 PM ET)")
        print("  3. Check API endpoints return 200 (not 5xx)")
        return 0
    else:
        print("\n[FAILED] Migrations did not complete successfully")
        return 1


if __name__ == '__main__':
    sys.exit(main())
