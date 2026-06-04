#!/usr/bin/env python3
"""
Check recent loader logs and execution times to verify data collection performance.
"""

import boto3
from datetime import datetime, timedelta

def check_loader_logs():
    logs_client = boto3.client('logs', region_name='us-east-1')
    sfn_client = boto3.client('stepfunctions', region_name='us-east-1')

    # Check ECS log groups for recent executions
    log_groups = [
        '/ecs/algo-stock_prices_daily-loader',
        '/ecs/algo-technical_data_daily-loader',
        '/ecs/algo-buy_sell_daily-loader',
        '/ecs/algo-signal_quality_scores-loader',
        '/ecs/algo-algo_metrics_daily-loader',
        '/ecs/algo-swing_trader_scores-loader',
        '/ecs/algo-company_profile-loader',
        '/ecs/algo-stability_metrics-loader',
    ]

    start_time = int((datetime.utcnow() - timedelta(hours=72)).timestamp() * 1000)

    print("=" * 80)
    print("LOADER EXECUTION LOGS (Last 72 hours)")
    print("=" * 80)

    for log_group in log_groups:
        print(f"\n{log_group}")
        try:
            # Get all events
            response = logs_client.filter_log_events(
                logGroupName=log_group,
                startTime=start_time,
                limit=50
            )

            events = response.get('events', [])
            if not events:
                print("  (No events in last 72 hours)")
                continue

            # Look for summary lines or timing info
            for event in events[-10:]:  # Last 10 events
                msg = event['message'].strip()
                # Look for interesting lines
                if any(x in msg.lower() for x in ['completed', 'error', 'timeout', 'seconds', 'duration', 'failed', 'success']):
                    ts = datetime.fromtimestamp(event['timestamp']/1000).strftime('%Y-%m-%d %H:%M:%S')
                    if len(msg) > 100:
                        msg = msg[:100] + '...'
                    print(f"  [{ts}] {msg}")

        except Exception as e:
            print(f"  Error: {str(e)[:80]}")

    # Check Step Functions EOD pipeline
    print("\n" + "=" * 80)
    print("STEP FUNCTIONS EOD PIPELINE EXECUTIONS")
    print("=" * 80)

    sm_arn = 'arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev'

    try:
        execs = sfn_client.list_executions(
            stateMachineArn=sm_arn,
            maxResults=5
        )

        for exe in execs.get('executions', [])[:3]:
            exe_arn = exe['executionArn']
            status = exe['status']
            start = exe['startDate'].strftime('%Y-%m-%d %H:%M:%S')

            print(f"\n  [{start}] Status: {status}")

            # Get execution details
            try:
                exec_details = sfn_client.describe_execution(executionArn=exe_arn)

                if 'stopDate' in exec_details:
                    duration = (exec_details['stopDate'] - exec_details['startDate']).total_seconds()
                    print(f"    Duration: {duration:.0f} seconds ({duration/60:.1f} minutes)")

                # Get history to find task execution times
                history = sfn_client.get_execution_history(executionArn=exe_arn, maxResults=100)

                task_durations = {}
                task_starts = {}

                for event in history.get('events', []):
                    evt_type = event['type']

                    if evt_type == 'TaskStateEntered':
                        detail = event.get('stateEnteredEventDetails', {})
                        task_name = detail.get('name')
                        if task_name:
                            task_starts[task_name] = event['timestamp']

                    elif evt_type == 'TaskSucceeded' or evt_type == 'TaskFailed':
                        detail = event.get('executionSucceededEventDetails', {}) or event.get('executionFailedEventDetails', {})
                        # Try to find matching task name from state name
                        for key in task_starts:
                            if key in str(event):
                                duration = (event['timestamp'] - task_starts[key]) / 1000
                                task_durations[key] = duration

                if task_durations:
                    print("    Task Execution Times:")
                    for task, duration in sorted(task_durations.items(), key=lambda x: x[1], reverse=True)[:10]:
                        print(f"      {task}: {duration:.0f}s ({duration/60:.1f}m)")

            except Exception as e:
                print(f"    Error getting details: {str(e)[:60]}")

    except Exception as e:
        print(f"Error: {str(e)[:80]}")

if __name__ == '__main__':
    check_loader_logs()
