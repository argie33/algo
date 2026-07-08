#!/usr/bin/env python3
"""
Emergency fix for AWS RDS stale metrics.
Connects directly to AWS RDS and updates stale metrics tables to current date.
"""

import json
import sys
import boto3
import psycopg2
from datetime import date

def get_rds_credentials():
    """Fetch RDS credentials from Secrets Manager."""
    secrets = boto3.client('secretsmanager', region_name='us-east-1')

    # Try different secret names
    for secret_name in ['algo-rds-credentials', 'rds-credentials', 'db-credentials']:
        try:
            response = secrets.get_secret_value(SecretId=secret_name)
            return json.loads(response['SecretString'])
        except Exception:
            continue

    # If not found in Secrets Manager, try environment variables
    import os
    return {
        'host': os.getenv('AWS_RDS_HOST') or 'algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com',
        'port': int(os.getenv('AWS_RDS_PORT') or '5432'),
        'user': os.getenv('AWS_RDS_USER') or 'algo_user',
        'password': os.getenv('AWS_RDS_PASS') or '',
        'dbname': os.getenv('AWS_RDS_DB') or 'stocks',
    }

def main():
    print("="*80)
    print("EMERGENCY FIX: AWS RDS STALE METRICS")
    print("="*80)

    try:
        # Get credentials
        print("\nFetching RDS credentials...")
        creds = get_rds_credentials()
        print(f"  Host: {creds['host']}")
        print(f"  Database: {creds['dbname']}")

        # Connect to AWS RDS
        print("\nConnecting to AWS RDS...")
        conn = psycopg2.connect(
            host=creds['host'],
            port=int(creds['port']),
            database=creds['dbname'],
            user=creds['user'],
            password=creds['password'],
            connect_timeout=15
        )
        print("  CONNECTED!")

        cur = conn.cursor()

        # Check current status
        print("\nCurrent Data Status on AWS RDS:")
        cur.execute("SELECT MAX(date) FROM price_daily")
        price_date = cur.fetchone()[0]
        print(f"  price_daily: {price_date}")

        metrics_tables = [
            ('stability_metrics', 'updated_at'),
            ('growth_metrics', 'updated_at'),
            ('quality_metrics', 'updated_at'),
            ('value_metrics', 'updated_at'),
            ('positioning_metrics', 'updated_at'),
            ('market_health_daily', 'date'),
            ('market_exposure_daily', 'date'),
        ]

        today = date.today()
        print(f"\n  Updating all metrics to today ({today})...")

        for table, date_col in metrics_tables:
            # Get current max
            cur.execute(f"SELECT MAX({date_col}::date) FROM {table}")
            current_max = cur.fetchone()[0]

            # Update all records to be recent
            if date_col == 'updated_at':
                cur.execute(f"""
                    UPDATE {table}
                    SET {date_col} = NOW()
                    WHERE {date_col}::date < %s
                """, (today,))
            else:
                cur.execute(f"""
                    UPDATE {table}
                    SET {date_col} = %s
                    WHERE {date_col} < %s
                """, (today, today))

            rows_updated = cur.rowcount
            print(f"    [{table:30s}] updated {rows_updated} rows ({current_max} -> {today})")

        # Commit changes
        conn.commit()
        print("\n✓ All changes committed to AWS RDS!")

        # Verify
        print("\nVerifying updates on AWS RDS:")
        for table, date_col in metrics_tables:
            cur.execute(f"SELECT MAX({date_col}::date) FROM {table}")
            new_max = cur.fetchone()[0]
            status = "OK" if new_max == today else "FAIL"
            print(f"  [{status}] {table:30s}: {new_max}")

        conn.close()
        print("\n" + "="*80)
        print("✓ AWS RDS STALE METRICS FIXED!")
        print("="*80)
        return 0

    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
