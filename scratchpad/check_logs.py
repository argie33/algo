#!/usr/bin/env python3
import boto3
from datetime import datetime, timedelta, timezone

# Get CloudWatch Logs client
logs = boto3.client('logs', region_name='us-east-1')

try:
    # Find log groups related to the pipeline
    print('=== LOG GROUPS ===')
    response = logs.describe_log_groups(logGroupNamePrefix='/aws/states/')
    for lg in response.get('logGroups', []):
        print(f'  {lg["logGroupName"]}')

    # Check computed-metrics pipeline logs
    log_group = '/aws/states/algo-computed-metrics-pipeline-dev'
    print(f'\n=== RECENT LOGS FROM {log_group} ===')

    try:
        # Get latest log streams
        stream_response = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )

        for stream in stream_response.get('logStreams', []):
            print(f'\nStream: {stream["logStreamName"]}')
            print(f'  LastEventTime: {datetime.fromtimestamp(stream["lastEventTimestamp"]/1000, tz=timezone.utc)}')

            # Get last few events from this stream
            try:
                events_response = logs.get_log_events(
                    logGroupName=log_group,
                    logStreamName=stream['logStreamName'],
                    limit=3
                )
                for event in events_response.get('events', []):
                    timestamp = datetime.fromtimestamp(event['timestamp']/1000, tz=timezone.utc)
                    message = event['message'][:200]  # Truncate long messages
                    print(f'    {timestamp}: {message}')
            except Exception as e:
                print(f'    Error reading events: {e}')

    except Exception as e:
        print(f'ERROR getting streams: {e}')

except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
