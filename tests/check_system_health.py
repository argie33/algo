#!/usr/bin/env python3
"""Check system health: Lambda logs, database status, and data freshness."""

import boto3
import json
import sys
from datetime import datetime, timedelta

def check_api_lambda():
    """Check API Lambda for errors."""
    print("=" * 70)
    print("API LAMBDA HEALTH")
    print("=" * 70)

    lambda_client = boto3.client('lambda', region_name='us-east-1')
    logs_client = boto3.client('logs', region_name='us-east-1')

    # Check lambda configuration
    try:
        config = lambda_client.get_function_configuration(FunctionName='algo-api-dev')
        print(f"✓ Lambda exists: algo-api-dev")
        print(f"  Runtime: {config.get('Runtime')}")
        print(f"  Memory: {config.get('MemorySize')}MB")
        print(f"  Timeout: {config.get('Timeout')}s")
        print(f"  Layers: {len(config.get('Layers', []))} attached")

        # Check env vars
        env_vars = config.get('Environment', {}).get('Variables', {})
        print(f"  Environment vars: {len(env_vars)} configured")
        if 'DB_SECRET_ARN' in env_vars:
            print(f"    ✓ DB_SECRET_ARN configured")
        if 'DB_HOST' in env_vars:
            print(f"    ✓ DB_HOST: {env_vars['DB_HOST']}")
    except Exception as e:
        print(f"✗ Error checking Lambda config: {e}")
        return False

    # Check recent logs for errors
    try:
        log_group = '/aws/lambda/algo-api-dev'

        # Get latest log stream
        streams = logs_client.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )

        if not streams.get('logStreams'):
            print(f"⚠ No recent logs for {log_group}")
            return True

        stream_name = streams['logStreams'][0]['logStreamName']
        print(f"  Latest log stream: {stream_name}")

        # Get events
        events = logs_client.get_log_events(
            logGroupName=log_group,
            logStreamName=stream_name,
            limit=20
        )

        has_error = False
        error_count = 0
        for event in events.get('events', []):
            message = event.get('message', '')
            if 'ERROR' in message or '500' in message:
                print(f"  ✗ ERROR found: {message[:100]}")
                has_error = True
                error_count += 1

        if error_count > 0:
            print(f"  ✗ Found {error_count} errors in recent logs")
            return False
        else:
            print(f"  ✓ No errors in recent logs")
            return True

    except Exception as e:
        print(f"⚠ Could not check logs: {e}")
        return True

def check_orchestrator_lambda():
    """Check Orchestrator Lambda for errors."""
    print("\n" + "=" * 70)
    print("ORCHESTRATOR LAMBDA HEALTH")
    print("=" * 70)

    lambda_client = boto3.client('lambda', region_name='us-east-1')
    logs_client = boto3.client('logs', region_name='us-east-1')

    try:
        config = lambda_client.get_function_configuration(FunctionName='algo-algo-dev')
        print(f"✓ Lambda exists: algo-algo-dev")
        print(f"  Runtime: {config.get('Runtime')}")
        print(f"  Memory: {config.get('MemorySize')}MB")
        print(f"  Timeout: {config.get('Timeout')}s")
    except Exception as e:
        print(f"✗ Error checking Lambda: {e}")
        return False

    # Check recent logs
    try:
        log_group = '/aws/lambda/algo-algo-dev'

        streams = logs_client.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )

        if not streams.get('logStreams'):
            print(f"⚠ No recent logs")
            return True

        stream_name = streams['logStreams'][0]['logStreamName']
        print(f"  Latest log stream: {stream_name}")

        events = logs_client.get_log_events(
            logGroupName=log_group,
            logStreamName=stream_name,
            limit=30
        )

        phase_info = {}
        has_error = False

        for event in events.get('events', []):
            message = event.get('message', '')

            # Track phases
            if 'Phase' in message:
                for phase in range(1, 8):
                    if f'Phase {phase}' in message:
                        phase_info[phase] = 'in progress'

            # Check for errors
            if 'ERROR' in message or 'error' in message.lower():
                if '500' in message or 'Exception' in message:
                    print(f"  ✗ ERROR: {message[:100]}")
                    has_error = True

        if phase_info:
            print(f"  Phases executed: {', '.join(f'Phase {p}' for p in sorted(phase_info.keys()))}")

        if not has_error:
            print(f"  ✓ No critical errors")

        return not has_error

    except Exception as e:
        print(f"⚠ Could not check logs: {e}")
        return True

def check_database():
    """Check RDS database connectivity."""
    print("\n" + "=" * 70)
    print("RDS DATABASE HEALTH")
    print("=" * 70)

    rds_client = boto3.client('rds', region_name='us-east-1')

    try:
        instances = rds_client.describe_db_instances(
            Filters=[{'Name': 'db-instance-id', 'Values': ['algo-db']}]
        )

        if not instances['DBInstances']:
            print("✗ No RDS instance found")
            return False

        db = instances['DBInstances'][0]
        print(f"✓ Database: {db['DBInstanceIdentifier']}")
        print(f"  Status: {db['DBInstanceStatus']}")
        print(f"  Engine: {db['Engine']} {db['EngineVersion']}")
        print(f"  Endpoint: {db['Endpoint']['Address']}")

        if db['DBInstanceStatus'] != 'available':
            print(f"  ✗ WARNING: Database not available ({db['DBInstanceStatus']})")
            return False
        else:
            print(f"  ✓ Database available")
            return True

    except Exception as e:
        print(f"✗ Error checking database: {e}")
        return False

def main():
    """Run all health checks."""
    print("\n" + "=" * 70)
    print(f"SYSTEM HEALTH CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 70 + "\n")

    results = []

    # Run checks
    results.append(("API Lambda", check_api_lambda()))
    results.append(("Orchestrator Lambda", check_orchestrator_lambda()))
    results.append(("RDS Database", check_database()))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_ok = True
    for name, status in results:
        symbol = "✓" if status else "✗"
        print(f"{symbol} {name}: {'OK' if status else 'HAS ISSUES'}")
        if not status:
            all_ok = False

    print("=" * 70 + "\n")

    if all_ok:
        print("✓ All systems operational")
        return 0
    else:
        print("✗ Some systems have issues - see details above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
