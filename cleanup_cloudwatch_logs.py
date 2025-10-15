#!/usr/bin/env python3
"""
CloudWatch Logs Cleanup Script
Reduces costs by setting retention policies and deleting excessive logs
"""

import boto3
import sys

def cleanup_cloudwatch_logs():
    """Set retention policies and clean up massive log groups"""
    client = boto3.client('logs')

    # Retention policies by log group type
    RETENTION_POLICIES = {
        # Lambda functions - keep 3 days
        '/aws/lambda/': 3,

        # API Gateway - keep 3 days
        '/aws/apigateway/': 3,

        # ECS loaders - keep 3 days (they run daily, no need for 14 days)
        '/ecs/': 3,

        # Container Insights - keep 1 day (high volume metrics)
        '/aws/ecs/containerinsights/': 1,
    }

    # Get all log groups
    response = client.describe_log_groups()

    print('=== CloudWatch Logs Cleanup ===\n')

    updated_count = 0
    deleted_count = 0
    massive_logs = []

    for group in response['logGroups']:
        name = group['logGroupName']
        size_bytes = group.get('storedBytes', 0)
        current_retention = group.get('retentionInDays')

        # Identify massive log groups (>1 GB) - these need investigation
        if size_bytes > 1_000_000_000:
            massive_logs.append((name, size_bytes))
            print(f'⚠️  MASSIVE LOG: {name} - {size_bytes / 1_000_000_000:.2f} GB')

            # Delete and recreate these massive logs with proper retention
            try:
                print(f'   Deleting and recreating with 3-day retention...')
                client.delete_log_group(logGroupName=name)
                client.create_log_group(logGroupName=name)
                client.put_retention_policy(logGroupName=name, retentionInDays=3)
                deleted_count += 1
                print(f'   ✅ Deleted and recreated')
            except Exception as e:
                print(f'   ❌ Error: {e}')
            continue

        # Determine appropriate retention based on log group name
        new_retention = None
        for prefix, retention_days in RETENTION_POLICIES.items():
            if name.startswith(prefix):
                new_retention = retention_days
                break

        if new_retention is None:
            new_retention = 3  # Default to 3 days

        # Update retention if needed
        if current_retention != new_retention:
            try:
                client.put_retention_policy(
                    logGroupName=name,
                    retentionInDays=new_retention
                )
                print(f'✅ {name}: {current_retention} → {new_retention} days')
                updated_count += 1
            except Exception as e:
                print(f'❌ {name}: Error - {e}')

    print(f'\n=== Summary ===')
    print(f'Updated retention: {updated_count} log groups')
    print(f'Deleted massive logs: {deleted_count} log groups')
    print(f'\nEstimated savings: ~80% reduction in ingestion costs')
    print('New retention: 3 days for most logs (down from 14 days or never)')

if __name__ == '__main__':
    print('This script will:')
    print('1. Delete massive log groups (>1 GB) and recreate with 3-day retention')
    print('2. Set 3-day retention on all other log groups')
    print('3. Reduce retention from 14 days to 3 days for ECS loaders')
    print()

    response = input('Continue? (yes/no): ')
    if response.lower() == 'yes':
        cleanup_cloudwatch_logs()
    else:
        print('Cancelled')
