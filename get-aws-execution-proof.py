#!/usr/bin/env python3
"""
AWS Execution Proof Capture
Get real CloudWatch logs and RDS data showing actual Batch 5 loader execution
"""

import boto3
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Load environment
env_file = Path('.env.local')
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key] = val

AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
DB_USER = os.environ.get('DB_USER', 'stocks')
DB_PASSWORD = os.environ.get('DB_PASSWORD')

# Initialize AWS clients
logs_client = boto3.client(
    'logs',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

rds_client = boto3.client(
    'rds',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

ec2_client = boto3.client(
    'ec2',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

import psycopg2

def get_rds_endpoint():
    """Get RDS database endpoint"""
    try:
        response = rds_client.describe_db_instances(
            DBInstanceIdentifier='stocks'
        )
        if response['DBInstances']:
            endpoint = response['DBInstances'][0]['Endpoint']['Address']
            status = response['DBInstances'][0]['DBInstanceStatus']
            return endpoint, status
    except Exception as e:
        print(f"Error getting RDS endpoint: {e}")
    return None, None

def get_cloudwatch_logs(log_group, limit=100):
    """Get recent CloudWatch logs for a loader"""
    try:
        # Get latest log stream
        streams = logs_client.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )

        if not streams['logStreams']:
            return []

        stream_name = streams['logStreams'][0]['logStreamName']

        # Get events
        events = logs_client.get_log_events(
            logGroupName=log_group,
            logStreamName=stream_name,
            startFromHead=False,
            limit=limit
        )

        return events.get('events', [])

    except logs_client.exceptions.ResourceNotFoundException:
        return []
    except Exception as e:
        print(f"Error getting logs from {log_group}: {e}")
        return []

def query_rds_data(query):
    """Query RDS database"""
    try:
        endpoint, _ = get_rds_endpoint()
        if not endpoint:
            return None

        conn = psycopg2.connect(
            host=endpoint,
            database='stocks',
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()
        return result
    except Exception as e:
        print(f"Error querying RDS: {e}")
        return None

def main():
    print("\n" + "="*70)
    print("AWS EXECUTION PROOF - REAL LOGS & DATA")
    print("="*70 + "\n")

    # Step 1: Check RDS Status
    print("[1] RDS Database Status")
    print("-" * 70)
    endpoint, status = get_rds_endpoint()
    if endpoint:
        print(f"[OK] RDS Database: {endpoint}")
        print(f"[OK] Status: {status}")
    else:
        print("[WARN] RDS not accessible yet (may still be provisioning)")

    # Step 2: Get CloudWatch Logs
    print("\n[2] CloudWatch Logs - Batch 5 Loaders")
    print("-" * 70)

    batch5_loaders = [
        'loadquarterlyincomestatement',
        'loadannualincomestatement',
        'loadquarterlybalancesheet',
        'loadannualbalancesheet',
        'loadquarterlycashflow',
        'loadannualcashflow'
    ]

    for loader in batch5_loaders:
        log_group = f'/ecs/{loader}'
        logs = get_cloudwatch_logs(log_group, limit=50)

        if logs:
            print(f"\n[OK] {loader}:")
            # Show last 10 lines
            for event in logs[-10:]:
                msg = event.get('message', '').strip()
                if msg:
                    print(f"     {msg[:100]}")

            # Look for completion message
            for event in logs:
                msg = event.get('message', '')
                if '[OK] Completed' in msg or 'rows inserted' in msg:
                    print(f"     [SUCCESS] {msg}")
        else:
            print(f"\n[WAIT] {loader}: No logs yet (job may be running or waiting to start)")

    # Step 3: Query RDS Data
    print("\n[3] RDS Data Verification")
    print("-" * 70)

    if endpoint:
        query = """
        SELECT
          'quarterly_income_statement' as table_name,
          COUNT(*) as row_count,
          COUNT(DISTINCT symbol) as unique_symbols,
          MAX(date) as latest_date
        FROM quarterly_income_statement
        UNION ALL
        SELECT 'annual_income_statement', COUNT(*), COUNT(DISTINCT symbol), MAX(date) FROM annual_income_statement
        UNION ALL
        SELECT 'quarterly_balance_sheet', COUNT(*), COUNT(DISTINCT symbol), MAX(date) FROM quarterly_balance_sheet
        UNION ALL
        SELECT 'annual_balance_sheet', COUNT(*), COUNT(DISTINCT symbol), MAX(date) FROM annual_balance_sheet
        UNION ALL
        SELECT 'quarterly_cash_flow', COUNT(*), COUNT(DISTINCT symbol), MAX(date) FROM quarterly_cash_flow
        UNION ALL
        SELECT 'annual_cash_flow', COUNT(*), COUNT(DISTINCT symbol), MAX(date) FROM annual_cash_flow
        ORDER BY row_count DESC;
        """

        result = query_rds_data(query)
        if result:
            print("\nBatch 5 Table Status:")
            total_rows = 0
            for row in result:
                table, count, symbols, date = row
                print(f"  {table:30s}: {count:6d} rows, {symbols:4d} symbols (latest: {date})")
                total_rows += count
            print(f"  {'TOTAL':30s}: {total_rows:6d} rows")
        else:
            print("[INFO] RDS accessible but tables may be empty (data loading in progress)")

    print("\n" + "="*70)
    print("END EXECUTION PROOF")
    print("="*70 + "\n")

if __name__ == '__main__':
    main()
