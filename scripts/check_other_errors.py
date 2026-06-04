#!/usr/bin/env python3
"""
Check what "other errors" are happening in specific loaders.
"""

import boto3
from datetime import datetime, timedelta

logs = boto3.client('logs', region_name='us-east-1')
start_time = int((datetime.utcnow() - timedelta(hours=96)).timestamp() * 1000)

loaders_to_check = {
    '/ecs/algo-technical_data_daily-loader': 'technical_data_daily',
    '/ecs/algo-market_health_daily-loader': 'market_health_daily',
    '/ecs/algo-fred_economic_data-loader': 'fred_economic_data',
    '/ecs/algo-buy_sell_daily-loader': 'buy_sell_daily',
}

for log_group, loader_name in loaders_to_check.items():
    print(f"\n=== {loader_name} - Sample errors ===")

    response = logs.filter_log_events(
        logGroupName=log_group,
        startTime=start_time,
        limit=100
    )

    # Find errors that aren't timeout/rate limit/connection related
    shown = 0
    for event in response.get('events', []):
        msg = event['message']
        msg_lower = msg.lower()

        # Skip known error types
        if any(x in msg_lower for x in ['timed-out', 'timeout', 'rate', 'too many', 'connection', 'statement timeout']):
            continue

        if 'error' in msg_lower or 'failed' in msg_lower or 'exception' in msg_lower:
            ts = datetime.fromtimestamp(event['timestamp'] / 1000).strftime('%Y-%m-%d %H:%M')
            print(f'[{ts}] {msg[:120]}')
            shown += 1
            if shown >= 3:
                break

    if shown == 0:
        print('(No "other" errors found)')
