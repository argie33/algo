#!/usr/bin/env python3
"""Analyze loader execution status from database and AWS logs."""

import os
import json
import sys
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Fix encoding on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    """Get database connection using environment variables."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME', 'algo_trading'),
            sslmode=os.getenv('DB_SSL', 'disable')
        )
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None


def get_loader_status_from_db() -> Dict:
    """Query loader status from data_loader_status table."""
    conn = get_db_connection()
    if not conn:
        return {}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    loader_name,
                    status,
                    rows_processed,
                    rows_written,
                    error_message,
                    created_at,
                    updated_at
                FROM data_loader_status
                ORDER BY created_at DESC
                LIMIT 100
            """)
            rows = cur.fetchall()

        loader_status = {}
        for row in rows:
            loader_name = row['loader_name']
            if loader_name not in loader_status:
                loader_status[loader_name] = row

        return loader_status
    except Exception as e:
        print(f"❌ Query failed: {e}")
        return {}
    finally:
        conn.close()


def get_aws_logs(log_group: str, hours: int = 24) -> Dict[str, List[str]]:
    """Fetch CloudWatch logs for loaders."""
    try:
        client = boto3.client('logs', region_name='us-east-1')

        # Get log streams
        response = client.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True
        )

        logs_by_stream = {}
        start_time = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)

        for stream in response.get('logStreams', [])[:50]:  # Limit to 50 recent streams
            stream_name = stream['logStreamName']
            try:
                log_response = client.get_log_events(
                    logGroupName=log_group,
                    logStreamName=stream_name,
                    startTime=start_time,
                    limit=100
                )
                logs_by_stream[stream_name] = [
                    event['message'] for event in log_response.get('events', [])
                ]
            except Exception as e:
                print(f"⚠️  Could not fetch logs for {stream_name}: {e}")

        return logs_by_stream
    except Exception as e:
        print(f"❌ AWS CloudWatch access failed: {e}")
        print("   Make sure you have AWS credentials configured: aws configure")
        return {}


def analyze_loader_issues() -> None:
    """Analyze and report loader issues."""
    print("=" * 80)
    print("LOADER STATUS ANALYSIS")
    print("=" * 80)

    # Get database status
    print("\n📊 DATABASE LOADER STATUS:")
    print("-" * 80)

    loader_status = get_loader_status_from_db()

    if not loader_status:
        print("❌ No loader status data found in database")
        print("   Loaders may not have run yet or table is empty")
    else:
        issues = []
        successful = []

        for loader_name, status_row in sorted(loader_status.items()):
            status = status_row['status']
            rows_written = status_row.get('rows_written', 0)
            rows_processed = status_row.get('rows_processed', 0)
            error = status_row.get('error_message')
            created_at = status_row.get('created_at')

            if status == 'success':
                if rows_written == 0:
                    issues.append({
                        'loader': loader_name,
                        'issue': f'✅ Success but 0 rows written (processed: {rows_processed})',
                        'created_at': created_at
                    })
                else:
                    successful.append({
                        'loader': loader_name,
                        'rows': rows_written,
                        'created_at': created_at
                    })
            elif status == 'failed':
                issues.append({
                    'loader': loader_name,
                    'issue': f'❌ Failed: {error or "Unknown error"}',
                    'created_at': created_at
                })
            elif status == 'running':
                issues.append({
                    'loader': loader_name,
                    'issue': '⏳ Still running',
                    'created_at': created_at
                })
            else:
                issues.append({
                    'loader': loader_name,
                    'issue': f'❓ Unknown status: {status}',
                    'created_at': created_at
                })

        print(f"\n✅ SUCCESSFUL ({len(successful)}):")
        for item in successful:
            print(f"  • {item['loader']}: {item['rows']} rows")

        if issues:
            print(f"\n⚠️  ISSUES & ANOMALIES ({len(issues)}):")
            for item in issues:
                print(f"  • {item['loader']}: {item['issue']}")

    # Try AWS logs
    print("\n\n📋 AWS CLOUDWATCH LOGS:")
    print("-" * 80)

    logs = get_aws_logs('/ecs/algo-cluster', hours=24)

    if logs:
        print(f"Found {len(logs)} log streams")

        # Parse for errors
        errors_by_loader = {}
        for stream_name, messages in logs.items():
            for msg in messages:
                if 'error' in msg.lower() or 'exception' in msg.lower():
                    loader = stream_name.split('/')[0] if '/' in stream_name else stream_name
                    if loader not in errors_by_loader:
                        errors_by_loader[loader] = []
                    errors_by_loader[loader].append(msg)

        if errors_by_loader:
            print("\n🔴 ERRORS FOUND:")
            for loader, errors in sorted(errors_by_loader.items()):
                print(f"\n  {loader}:")
                for error in errors[:3]:  # Show first 3 errors
                    print(f"    • {error[:100]}...")
        else:
            print("✅ No errors found in logs")
    else:
        print("⚠️  Could not access AWS logs")
        print("   Please run: aws configure")
        print("   Then set up credentials from Terraform outputs or PowerShell environment")

    print("\n" + "=" * 80)


if __name__ == '__main__':
    analyze_loader_issues()
