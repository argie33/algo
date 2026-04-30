#!/usr/bin/env python3
"""
AWS Deployment Manager for Batch 5 Loaders
Uses boto3 to deploy CloudFormation stacks and manage ECS tasks
"""

import boto3
import json
import os
import time
from pathlib import Path
from datetime import datetime

# Load environment variables
env_file = Path('.env.local')
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key] = val

# AWS Configuration
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
AWS_ACCOUNT_ID = '626216981288'
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')

# Initialize AWS clients
cf_client = boto3.client(
    'cloudformation',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

ecs_client = boto3.client(
    'ecs',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

logs_client = boto3.client(
    'logs',
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

def print_status(msg, status='INFO'):
    """Print formatted status message"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{status}] {msg}")

def check_cloudformation_stack(stack_name):
    """Check if CloudFormation stack exists and its status"""
    try:
        response = cf_client.describe_stacks(StackName=stack_name)
        if response['Stacks']:
            stack = response['Stacks'][0]
            return {
                'exists': True,
                'status': stack['StackStatus'],
                'creation_time': stack.get('CreationTime'),
                'outputs': {o['OutputKey']: o['OutputValue'] for o in stack.get('Outputs', [])}
            }
    except cf_client.exceptions.ClientError as e:
        if 'does not exist' in str(e):
            return {'exists': False}
    return None

def deploy_cloudformation_stack(stack_name, template_file, parameters=None):
    """Deploy a CloudFormation stack"""
    print_status(f"Deploying stack: {stack_name}", "INFO")

    # Check if stack already exists
    existing = check_cloudformation_stack(stack_name)
    if existing and existing.get('exists'):
        print_status(f"Stack {stack_name} already exists with status: {existing['status']}", "WARN")
        if existing['status'] != 'CREATE_COMPLETE':
            print_status(f"Stack {stack_name} needs attention: {existing['status']}", "ERROR")
        return existing['status'] == 'CREATE_COMPLETE'

    # Read template
    try:
        with open(template_file) as f:
            template_body = f.read()
    except FileNotFoundError:
        print_status(f"Template file not found: {template_file}", "ERROR")
        return False

    # Prepare parameters
    cf_parameters = []
    if parameters:
        for key, value in parameters.items():
            cf_parameters.append({'ParameterKey': key, 'ParameterValue': value})

    try:
        # Create or update stack
        response = cf_client.create_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Parameters=cf_parameters,
            Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']
        )
        print_status(f"Stack creation initiated: {stack_name}", "OK")

        # Wait for stack creation
        print_status(f"Waiting for stack {stack_name} to complete...", "INFO")
        waiter = cf_client.get_waiter('stack_create_complete')
        waiter.wait(StackName=stack_name)
        print_status(f"Stack {stack_name} created successfully", "OK")
        return True

    except cf_client.exceptions.ClientError as e:
        if 'already exists' in str(e):
            print_status(f"Stack {stack_name} already exists", "WARN")
            return True
        else:
            print_status(f"CloudFormation error: {e}", "ERROR")
            return False

def check_ecs_task_status(cluster, task_def):
    """Check ECS task definition and latest tasks"""
    try:
        # Check task definition
        task_def_response = ecs_client.describe_task_definition(
            taskDefinition=task_def
        )
        print_status(f"Task definition {task_def} exists", "OK")

        # List recent tasks
        tasks_response = ecs_client.list_tasks(
            cluster=cluster,
            family=task_def,
            maxResults=5
        )

        if tasks_response['taskArns']:
            print_status(f"Found {len(tasks_response['taskArns'])} recent tasks for {task_def}", "INFO")
            # Get task details
            task_details = ecs_client.describe_tasks(
                cluster=cluster,
                tasks=tasks_response['taskArns']
            )
            for task in task_details['tasks']:
                status = task['lastStatus']
                launched_at = task.get('createdAt', 'unknown')
                print_status(f"  - Task {task['taskArn'].split('/')[-1][:12]}... status: {status}", "INFO")
                return status
        else:
            print_status(f"No tasks found for {task_def}", "WARN")
            return None

    except Exception as e:
        print_status(f"Error checking ECS task: {e}", "ERROR")
        return None

def get_cloudwatch_logs(log_group, task_name, limit_lines=50):
    """Get recent CloudWatch logs for a loader"""
    try:
        # Try to get logs
        response = logs_client.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )

        if not response['logStreams']:
            print_status(f"No logs found in {log_group}", "WARN")
            return []

        log_stream = response['logStreams'][0]['logStreamName']

        # Get log events
        events_response = logs_client.get_log_events(
            logGroupName=log_group,
            logStreamName=log_stream,
            startFromHead=False,
            limit=limit_lines
        )

        events = events_response.get('events', [])
        return events

    except logs_client.exceptions.ResourceNotFoundException:
        print_status(f"Log group not found: {log_group}", "WARN")
        return []
    except Exception as e:
        print_status(f"Error getting logs: {e}", "ERROR")
        return []

def run_ecs_task(cluster, task_def, network_config):
    """Run an ECS task for a loader"""
    try:
        response = ecs_client.run_task(
            cluster=cluster,
            taskDefinition=task_def,
            launchType='FARGATE',
            networkConfiguration=network_config
        )

        if response['tasks']:
            task_arn = response['tasks'][0]['taskArn']
            print_status(f"Started task: {task_def}", "OK")
            print_status(f"Task ARN: {task_arn}", "INFO")
            return task_arn
        else:
            print_status(f"Failed to start task: {response}", "ERROR")
            return None

    except Exception as e:
        print_status(f"Error running task: {e}", "ERROR")
        return None

def main():
    print("\n" + "="*70)
    print("AWS BATCH 5 DEPLOYMENT MANAGER")
    print("="*70 + "\n")

    # Step 1: Check existing stacks
    print_status("Checking existing CloudFormation stacks...", "INFO")

    stacks_to_check = [
        'stocks-core',
        'stocks-app',
        'stocks-app-ecs-tasks'
    ]

    stack_status = {}
    for stack in stacks_to_check:
        status = check_cloudformation_stack(stack)
        if status:
            stack_status[stack] = status
            print_status(f"Stack {stack}: {status.get('status', 'UNKNOWN')}",
                        "OK" if status.get('exists') else "WARN")
        else:
            print_status(f"Stack {stack}: NOT FOUND", "WARN")

    print("\n" + "="*70)
    print("DEPLOYMENT STATUS SUMMARY")
    print("="*70 + "\n")

    # Check if all stacks exist
    all_exist = all(stack_status.get(s, {}).get('exists', False) for s in stacks_to_check)

    if all_exist:
        print_status("All CloudFormation stacks exist! Infrastructure is deployed.", "OK")
        print("\nStack Details:")
        for stack_name, status in stack_status.items():
            print(f"\n{stack_name}:")
            print(f"  Status: {status['status']}")
            print(f"  Created: {status.get('creation_time', 'unknown')}")
            if status.get('outputs'):
                print(f"  Outputs:")
                for key, val in status['outputs'].items():
                    print(f"    - {key}: {val}")
    else:
        print_status("Some stacks are missing. Deploy them first.", "WARN")
        print("\nTo deploy, run:")
        print("  aws cloudformation deploy \\")
        print("    --template-file template-core.yml \\")
        print("    --stack-name stocks-core \\")
        print("    --region us-east-1")

    # Step 2: Check ECS tasks if stacks exist
    if all_exist:
        print("\n" + "="*70)
        print("ECS TASK STATUS")
        print("="*70 + "\n")

        batch5_loaders = [
            'loadquarterlyincomestatement',
            'loadannualincomestatement',
            'loadquarterlybalancesheet',
            'loadannualbalancesheet',
            'loadquarterlycashflow',
            'loadannualcashflow'
        ]

        for loader in batch5_loaders:
            status = check_ecs_task_status('stock-analytics-cluster', loader)

            # Get recent logs
            log_group = f"/ecs/{loader}"
            logs = get_cloudwatch_logs(log_group, loader, limit_lines=10)

            if logs:
                print_status(f"Recent logs for {loader}:", "INFO")
                for event in logs[-5:]:  # Show last 5 lines
                    msg = event.get('message', '')
                    if msg:
                        print(f"  {msg[:100]}")

if __name__ == '__main__':
    main()
