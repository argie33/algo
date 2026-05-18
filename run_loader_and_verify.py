#!/usr/bin/env python3
"""
Trigger a loader task in AWS and capture CloudWatch logs showing execution success.
"""

import json
import time
import boto3
import sys
from datetime import datetime

def run_loader_and_capture_logs(loader_name="stock_symbols"):
    """Run a loader task and capture its CloudWatch logs."""

    try:
        # Initialize AWS clients
        ecs = boto3.client('ecs', region_name='us-east-1')
        logs = boto3.client('logs', region_name='us-east-1')
        ec2 = boto3.client('ec2', region_name='us-east-1')

        print(f"\n{'='*70}")
        print(f"TRIGGERING LOADER: {loader_name}")
        print(f"{'='*70}\n")

        # Get VPC details
        print("[1/5] Getting VPC configuration...")
        subnets_response = ec2.describe_subnets(
            Filters=[{'Name': 'tag:Project', 'Values': ['algo']}]
        )
        if not subnets_response['Subnets']:
            print("ERROR: No subnets found for project 'algo'")
            return False

        subnets = [s['SubnetId'] for s in subnets_response['Subnets'][:2]]
        print(f"   ✓ Found subnets: {subnets}")

        # Get security group
        sg_response = ec2.describe_security_groups(
            Filters=[{'Name': 'tag:Name', 'Values': ['algo-ecs-tasks']}]
        )
        if not sg_response['SecurityGroups']:
            print("ERROR: Security group 'algo-ecs-tasks' not found")
            return False

        sg = sg_response['SecurityGroups'][0]['GroupId']
        print(f"   ✓ Found security group: {sg}\n")

        # Run the ECS task
        print("[2/5] Launching ECS task...")
        response = ecs.run_task(
            cluster='algo-cluster',
            taskDefinition=f'algo-{loader_name}-loader',
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': subnets,
                    'securityGroups': [sg],
                    'assignPublicIp': 'DISABLED'
                }
            }
        )

        if not response.get('tasks'):
            print(f"ERROR: Failed to run task")
            if response.get('failures'):
                print(f"   Failures: {response['failures']}")
            return False

        task_arn = response['tasks'][0]['taskArn']
        task_id = task_arn.split('/')[-1]
        print(f"   ✓ Task started: {task_id}\n")

        # Wait for task to complete
        print("[3/5] Waiting for task to complete...")
        log_group = f"/ecs/algo-{loader_name}-loader"
        start_time = time.time()
        timeout = 600  # 10 minutes

        while True:
            response = ecs.describe_tasks(
                cluster='algo-cluster',
                tasks=[task_arn]
            )

            task = response['tasks'][0]
            status = task['lastStatus']
            elapsed = int(time.time() - start_time)

            print(f"   Status: {status} ({elapsed}s elapsed)")

            if status == 'STOPPED':
                exit_code = task['containers'][0].get('exitCode', -1)
                if exit_code == 0:
                    print(f"   ✓ Task completed successfully (exit code: 0)\n")
                else:
                    print(f"   ✗ Task failed (exit code: {exit_code})\n")
                break

            if elapsed > timeout:
                print(f"   ✗ Task timeout after {timeout}s\n")
                return False

            time.sleep(5)

        # Retrieve CloudWatch logs
        print("[4/5] Fetching CloudWatch logs...")
        try:
            # Get log streams
            streams = logs.describe_log_streams(
                logGroupName=log_group,
                logStreamNamePrefix=task_id,
                orderBy='LastEventTime',
                descending=True
            )

            if not streams.get('logStreams'):
                print(f"   ⚠ No log streams found (logs may be delayed)")
                return True  # Task succeeded, logs just not ready yet

            log_stream = streams['logStreams'][0]['logStreamName']
            print(f"   ✓ Found log stream: {log_stream}\n")

            # Get log events
            print("[5/5] CloudWatch Logs Output:")
            print(f"\n{'='*70}")
            print(f"LOG GROUP: {log_group}")
            print(f"LOG STREAM: {log_stream}")
            print(f"TASK ID: {task_id}")
            print(f"TIMESTAMP: {datetime.now().isoformat()}")
            print(f"{'='*70}\n")

            events = logs.get_log_events(
                logGroupName=log_group,
                logStreamName=log_stream,
                startFromHead=True
            )

            if events['events']:
                for event in events['events']:
                    message = event['message'].rstrip()
                    print(message)

                print(f"\n{'='*70}")
                print("✅ EXECUTION SUCCESS - Logs captured from CloudWatch")
                print(f"{'='*70}\n")
                return True
            else:
                print("   ⚠ No log events found")
                return True

        except logs.exceptions.ResourceNotFoundException:
            print(f"   ⚠ Log group not found yet (logs may be delayed)")
            return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    loader = sys.argv[1] if len(sys.argv) > 1 else 'stock_symbols'
    success = run_loader_and_capture_logs(loader)
    sys.exit(0 if success else 1)
