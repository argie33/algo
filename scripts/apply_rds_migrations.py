#!/usr/bin/env python3
"""
Direct RDS Migration Application Script

Connects to the AWS RDS database and applies pending migrations.

Usage:
    python3 scripts/apply_rds_migrations.py

Requirements:
    - AWS credentials configured (IAM user with Secrets Manager access)
    - psycopg2 installed: pip install psycopg2-binary boto3
    - Must run from a machine with VPC access (bastion, EC2, or Lambda in same VPC)
      OR with an SSM port-forward tunnel active:
        aws ssm start-session --target <bastion-instance-id> \
          --document-name AWS-StartPortForwardingSessionToRemoteHost \
          --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5432"]}'
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

        if 'host' not in secret:
            raise ValueError('[CRITICAL] RDS host missing from Secrets Manager')
        if 'password' not in secret:
            raise ValueError('[CRITICAL] RDS password missing from Secrets Manager')

        host = secret['host']
        return {
            'host': host.split(':')[0] if ':' in host else host,
            'port': int(secret.get('port', 5432)),
            'database': secret.get('dbname', 'stocks'),
            'user': secret.get('username', 'stocks'),
            'password': secret['password'],
        }
    except ValueError:
        raise
    except Exception as e:
        print(f"ERROR: Failed to get RDS credentials: {e}")
        sys.exit(1)


# All migrations to apply, in order.
# Each entry: (description, check_query, check_args, migration_sql)
MIGRATIONS = [
    # Migration 102: data_unavailable on metric tables
    (
        "quality_metrics.data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='quality_metrics' AND column_name='data_unavailable'",
        (),
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
    ),
    (
        "growth_metrics.data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='growth_metrics' AND column_name='data_unavailable'",
        (),
        "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
    ),
    (
        "value_metrics.data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='value_metrics' AND column_name='data_unavailable'",
        (),
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
    ),
    (
        "positioning_metrics.data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='positioning_metrics' AND column_name='data_unavailable'",
        (),
        "ALTER TABLE positioning_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
    ),
    (
        "stability_metrics.data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='stability_metrics' AND column_name='data_unavailable'",
        (),
        "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
    ),
    # Migration 104: reason and _unavailable_reason columns on metric tables
    (
        "quality_metrics.reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='quality_metrics' AND column_name='reason'",
        (),
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS reason VARCHAR(500)",
    ),
    (
        "stability_metrics.reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='stability_metrics' AND column_name='reason'",
        (),
        "ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS reason VARCHAR(500)",
    ),
    (
        "value_metrics.market_cap_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='value_metrics' AND column_name='market_cap_unavailable_reason'",
        (),
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS market_cap_unavailable_reason VARCHAR(255)",
    ),
    (
        "value_metrics.pe_ratio_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='value_metrics' AND column_name='pe_ratio_unavailable_reason'",
        (),
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS pe_ratio_unavailable_reason VARCHAR(255)",
    ),
    (
        "value_metrics.pb_ratio_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='value_metrics' AND column_name='pb_ratio_unavailable_reason'",
        (),
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS pb_ratio_unavailable_reason VARCHAR(255)",
    ),
    (
        "value_metrics.ps_ratio_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='value_metrics' AND column_name='ps_ratio_unavailable_reason'",
        (),
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS ps_ratio_unavailable_reason VARCHAR(255)",
    ),
    (
        "value_metrics.peg_ratio_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='value_metrics' AND column_name='peg_ratio_unavailable_reason'",
        (),
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS peg_ratio_unavailable_reason VARCHAR(255)",
    ),
    (
        "value_metrics.dividend_yield_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='value_metrics' AND column_name='dividend_yield_unavailable_reason'",
        (),
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS dividend_yield_unavailable_reason VARCHAR(255)",
    ),
    (
        "value_metrics.fcf_yield_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='value_metrics' AND column_name='fcf_yield_unavailable_reason'",
        (),
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS fcf_yield_unavailable_reason VARCHAR(255)",
    ),
    (
        "value_metrics.held_percent_insiders_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='value_metrics' AND column_name='held_percent_insiders_unavailable_reason'",
        (),
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS held_percent_insiders_unavailable_reason VARCHAR(255)",
    ),
    (
        "value_metrics.held_percent_institutions_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='value_metrics' AND column_name='held_percent_institutions_unavailable_reason'",
        (),
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS held_percent_institutions_unavailable_reason VARCHAR(255)",
    ),
    # Migration 103: data_unavailable columns on market_health_daily
    (
        "market_health_daily.put_call_ratio_data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='market_health_daily' AND column_name='put_call_ratio_data_unavailable'",
        (),
        "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS put_call_ratio_data_unavailable BOOLEAN DEFAULT FALSE",
    ),
    (
        "market_health_daily.put_call_ratio_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='market_health_daily' AND column_name='put_call_ratio_unavailable_reason'",
        (),
        "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS put_call_ratio_unavailable_reason VARCHAR(255)",
    ),
    (
        "market_health_daily.yield_curve_data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='market_health_daily' AND column_name='yield_curve_data_unavailable'",
        (),
        "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS yield_curve_data_unavailable BOOLEAN DEFAULT FALSE",
    ),
    (
        "market_health_daily.yield_curve_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='market_health_daily' AND column_name='yield_curve_unavailable_reason'",
        (),
        "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS yield_curve_unavailable_reason VARCHAR(255)",
    ),
    (
        "market_health_daily.fed_rate_data_unavailable",
        "SELECT 1 FROM information_schema.columns WHERE table_name='market_health_daily' AND column_name='fed_rate_data_unavailable'",
        (),
        "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS fed_rate_data_unavailable BOOLEAN DEFAULT FALSE",
    ),
    (
        "market_health_daily.fed_rate_unavailable_reason",
        "SELECT 1 FROM information_schema.columns WHERE table_name='market_health_daily' AND column_name='fed_rate_unavailable_reason'",
        (),
        "ALTER TABLE market_health_daily ADD COLUMN IF NOT EXISTS fed_rate_unavailable_reason VARCHAR(255)",
    ),
]


def apply_migrations():
    """Connect to RDS and apply pending migrations."""

    print("=" * 70)
    print("AWS RDS Migration Application")
    print("=" * 70)

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
        print("\n   NOTE: RDS is in a private VPC. Connect via:")
        print("   - SSM port-forward tunnel from bastion/EC2 in the VPC")
        print("   - Or run this from inside the VPC (EC2, Lambda, etc.)")
        sys.exit(1)

    print(f"\n3. Checking and applying {len(MIGRATIONS)} migrations...")
    applied = 0
    skipped = 0
    failed = 0

    for desc, check_sql, check_args, migration_sql in MIGRATIONS:
        cur.execute(check_sql, check_args)
        exists = cur.fetchone()
        if exists:
            print(f"   SKIP {desc} (already exists)")
            skipped += 1
            continue

        try:
            cur.execute(migration_sql)
            conn.commit()
            print(f"   OK   {desc}")
            applied += 1
        except Exception as e:
            print(f"   FAIL {desc}: {e}")
            conn.rollback()
            failed += 1

    print(f"\n{'='*70}")
    print(f"COMPLETE: {applied} applied, {skipped} skipped, {failed} failed")
    print("=" * 70)

    cur.close()
    conn.close()

    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    apply_migrations()
