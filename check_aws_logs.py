#!/usr/bin/env python3
"""Check AWS CloudWatch logs for stock_prices_daily failures."""

import boto3
import sys
from datetime import datetime, timedelta

logs = boto3.client('logs', region_name='us-east-1')

# Get logs from last 24 hours
now_ms = int(datetime.utcnow().timestamp() * 1000)
since_ms = now_ms - (24 * 60 * 60 * 1000)

print("=== stock_prices_daily ECS Task Logs (last 24h) ===")
print()

try:
    response = logs.filter_log_events(
        logGroupName='/ecs/algo-stock_prices_daily-loader',
        startTime=since_ms,
        endTime=now_ms,
        limit=200
    )

    if response.get('events'):
        print(f"Found {len(response['events'])} log events\n")
        print("=== ERROR/WARNING Messages ===\n")

        # Filter for errors and warnings
        error_patterns = ['ERROR', 'WARNING', 'CRITICAL', 'Traceback', 'Exception', 'FAIL', 'exit', 'failed']
        error_count = 0

        for event in response['events']:
            msg = event.get('message', '').strip()
            if any(pattern in msg for pattern in error_patterns):
                error_count += 1
                # Safely print with ASCII encoding
                safe_msg = ''.join(c if ord(c) < 128 else '?' for c in msg)
                print(safe_msg)

        if error_count == 0:
            print("No ERROR or WARNING messages found in logs")
            print("\n=== Last 20 log lines ===\n")
            for event in response['events'][-20:]:
                msg = event.get('message', '').strip()
                if msg:
                    safe_msg = ''.join(c if ord(c) < 128 else '?' for c in msg)
                    print(safe_msg)
        else:
            print(f"\n=== Found {error_count} error/warning messages ===" )
    else:
        print("No log events found for the last 24 hours")

except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    sys.exit(1)
