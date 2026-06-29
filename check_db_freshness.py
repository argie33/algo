#!/usr/bin/env python3
"""Check portfolio snapshot freshness in database."""
import json
import sys
import boto3

# Get DB credentials via boto3
try:
    secrets_client = boto3.client("secretsmanager", region_name="us-east-1")
    response = secrets_client.get_secret_value(SecretId="algo-dev-db")
    db_creds = json.loads(response["SecretString"])
except Exception as e:
    print(f"ERROR getting secrets: {e}")
    sys.exit(1)

# Import psycopg2 safely
try:
    import psycopg2
    from datetime import datetime, timezone
except ImportError as e:
    print(f"ERROR: Missing required module: {e}")
    sys.exit(1)

try:
    conn = psycopg2.connect(
        host="algo-dev-db.chhwlvcliqfb.us-east-1.rds.amazonaws.com",
        port=5432,
        database="algodb",
        user=db_creds["username"],
        password=db_creds["password"]
    )
    cur = conn.cursor()

    # Check portfolio snapshot age
    cur.execute("""
        SELECT now() at time zone 'UTC' as current_time,
               MAX(created_at) as latest_snapshot,
               EXTRACT(EPOCH FROM (now() at time zone 'UTC' - MAX(created_at))) as age_seconds,
               COUNT(*) as row_count
        FROM algo_portfolio_snapshots
    """)
    row = cur.fetchone()

    print("=== Database Portfolio Snapshot Status ===")
    print(f"Current DB Time: {row[0]}")
    print(f"Latest Snapshot Created: {row[1]}")
    print(f"Age (seconds): {row[2]}")
    print(f"Total Rows: {row[3]}")

    if row[2]:
        age_hours = row[2] / 3600
        age_days = age_hours / 24
        print(f"Age (human): {age_days:.1f} days ({age_hours:.1f} hours)")

    if row[2] and row[2] > 360:
        print(f"\n⚠️  DATA IS STALE: {row[2]:.0f}s > 360s max")
    else:
        print(f"\n✅ DATA IS FRESH: {row[2]:.0f}s < 360s max")

    conn.close()
except Exception as e:
    print(f"ERROR: Database query failed: {e}")
    sys.exit(1)
