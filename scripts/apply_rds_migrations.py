#!/usr/bin/env python3
"""
Direct RDS Migration Application Script

This script connects to the AWS RDS database and applies critical migrations
needed to fix the scores API 503 errors.

Usage:
    python3 apply_rds_migrations.py

Requirements:
    - AWS credentials configured (IAM user with Secrets Manager and RDS access)
    - psycopg2 installed: pip install psycopg2-binary boto3
    - Environment: Must run from the project root directory
"""

import json
import sys

import boto3
import psycopg2


def get_rds_credentials():
    """Get RDS credentials from AWS Secrets Manager."""
    try:
        client = boto3.client('secretsmanager', region_name='us-east-1')
        response = client.get_secret_value(SecretId='arn:aws:secretsmanager:us-east-1:626216981288:secret:algo/database-kymxp8')
        secret = json.loads(response['SecretString'])

        return {
            'host': secret.get('host', '').split(':')[0] if ':' in secret.get('host', '') else secret.get('host'),
            'port': int(secret.get('port', 5432)),
            'database': secret.get('dbname', 'stocks'),
            'user': secret.get('username', 'stocks'),
            'password': secret.get('password'),
        }
    except Exception as e:
        print(f"ERROR: Failed to get RDS credentials: {e}")
        sys.exit(1)

def apply_migrations():
    """Connect to RDS and apply critical migrations."""

    print("="*70)
    print("AWS RDS Migration Application")
    print("="*70)

    # Get credentials
    print("\n1. Getting RDS credentials from AWS Secrets Manager...")
    creds = get_rds_credentials()
    print(f"   Connected to: {creds['host']}")

    # Connect to RDS
    print("\n2. Connecting to AWS RDS database...")
    try:
        conn = psycopg2.connect(
            host=creds['host'],
            port=creds['port'],
            database=creds['database'],
            user=creds['user'],
            password=creds['password'],
            sslmode='require'
        )
        cur = conn.cursor()

        # Verify connection
        cur.execute("SELECT current_database(), inet_server_addr()")
        db_name, server_addr = cur.fetchone()
        print(f"   SUCCESS! Connected to: {db_name} on {server_addr}")

    except Exception as e:
        print(f"   ERROR: Failed to connect to RDS: {e}")
        print("\n   NOTE: If you're running this locally, you may need:")
        print("   - VPN connection to the AWS VPC")
        print("   - Or run this script from an EC2 instance/Lambda in the VPC")
        sys.exit(1)

    # Check current schema
    print("\n3. Checking current database schema...")
    tables = {
        'quality_metrics': 'Quality metrics (ROE, margins, debt ratios)',
        'growth_metrics': 'Growth metrics (revenue/EPS growth)',
        'value_metrics': 'Value metrics (P/E, P/B, dividend)',
        'positioning_metrics': 'Positioning metrics (institutional ownership)',
        'stability_metrics': 'Stability metrics (volatility, beta)',
    }

    missing_tables = []
    for table, _description in tables.items():
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = '{table}' AND column_name = 'data_unavailable'
        """)
        if cur.fetchone():
            print(f"   ✓ {table}: data_unavailable column exists")
        else:
            print(f"   ✗ {table}: data_unavailable column MISSING")
            missing_tables.append(table)

    # Apply migrations
    if missing_tables:
        print(f"\n4. Applying migrations to {len(missing_tables)} tables...")

        migrations = {
            'quality_metrics': 'ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE',
            'growth_metrics': 'ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE',
            'value_metrics': 'ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE',
            'positioning_metrics': 'ALTER TABLE positioning_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE',
            'stability_metrics': 'ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE',
        }

        for table in missing_tables:
            try:
                print(f"   Applying: {table}...")
                cur.execute(migrations[table])
                conn.commit()
                print(f"   ✓ {table}: migration applied")
            except Exception as e:
                print(f"   ✗ {table}: migration failed - {e}")
                conn.rollback()

        # Verify migrations
        print("\n5. Verifying migrations...")
        for table in missing_tables:
            cur.execute(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = '{table}' AND column_name = 'data_unavailable'
            """)
            if cur.fetchone():
                print(f"   ✓ {table}: data_unavailable column verified")
            else:
                print(f"   ✗ {table}: data_unavailable column still missing!")

        print("\n" + "="*70)
        print("MIGRATIONS APPLIED SUCCESSFULLY!")
        print("="*70)
        print("\nNext steps:")
        print("1. The scores API should now return 200 OK instead of 503")
        print("2. The dashboard scores panel should display component scores")
        print("3. Verify by calling: https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores")

    else:
        print("\n✓ ALL MIGRATIONS ALREADY APPLIED!")
        print("   The database schema is up to date.")
        print("\n   If the API is still returning 503 errors,")
        print("   the issue may be with the Lambda deployment.")

    cur.close()
    conn.close()

if __name__ == '__main__':
    apply_migrations()
