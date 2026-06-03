#!/usr/bin/env python3
import boto3

logs = boto3.client('logs', region_name='us-east-1')

# Get latest log stream
response = logs.describe_log_streams(
    logGroupName='/aws/lambda/algo-algo-dev',
    orderBy='LastEventTime',
    descending=True,
    limit=1
)

stream = response['logStreams'][0]['logStreamName']
print(f"Latest stream: {stream}\n")

# Get ALL events
response = logs.get_log_events(
    logGroupName='/aws/lambda/algo-algo-dev',
    logStreamName=stream,
    limit=1000
)

# Extract Phase 1 messages (from latest run)
phase1_info = []
for event in response['events']:
    msg = event['message'].strip()
    if any(x in msg for x in ['Phase 1', 'data_freshness', 'direct scan', 'STALE', 'Market health', 'SPY price']):
        phase1_info.append(msg)

# Show last 50 Phase 1 messages
for line in phase1_info[-50:]:
    print(line)
