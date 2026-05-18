#!/usr/bin/env python3
"""
Trigger AWS ECS data loaders to populate the database.
Usage: python3 trigger_data_loaders.py --access-key YOUR_KEY --secret-key YOUR_SECRET
Or: aws configure (then just run the script)
"""

import boto3
import json
import time
import argparse
from botocore.exceptions import ClientError

# Configuration
AWS_REGION = "us-east-1"
PROJECT_NAME = "algo"
ENVIRONMENT = "dev"
CLUSTER_NAME = f"{PROJECT_NAME}-cluster"

# Tier 0: Foundation (must run first)
TIER_0_LOADERS = [
    f"{PROJECT_NAME}-loaders-stocksymbols-{ENVIRONMENT}",
]

# Tier 1: Prices
TIER_1_LOADERS = [
    f"{PROJECT_NAME}-loaders-loadpricedaily-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-loadetfpricedaily-{ENVIRONMENT}",
]

# Tier 1b: Price aggregates
TIER_1B_LOADERS = [
    f"{PROJECT_NAME}-loaders-load_price_aggregate-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-load_etf_price_aggregate-{ENVIRONMENT}",
]

# Tier 1c: Technical indicators
TIER_1C_LOADERS = [
    f"{PROJECT_NAME}-loaders-load_technical_indicators-{ENVIRONMENT}",
]

# Tier 2: Reference data
TIER_2_LOADERS = [
    f"{PROJECT_NAME}-loaders-load_income_statement-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-load_balance_sheet-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-load_cash_flow-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-loadearningshistory-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-loadearningsrevisions-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-loadearningsestimates-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-load_key_metrics-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-loadmarketindices-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-loadseasonality-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-loadecondata-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-loadaaiidata-{ENVIRONMENT}",
    f"{PROJECT_NAME}-loaders-loadfeargreed-{ENVIRONMENT}",
]

# Quick tier for testing (just symbols and prices)
QUICK_LOADERS = TIER_0_LOADERS + TIER_1_LOADERS

def configure_aws(access_key=None, secret_key=None):
    """Configure AWS credentials if provided."""
    if access_key and secret_key:
        boto3.setup_default_session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=AWS_REGION
        )

def get_vpc_config():
    """Get VPC configuration from ECS cluster."""
    ecs = boto3.client('ecs', region_name=AWS_REGION)
    ec2 = boto3.client('ec2', region_name=AWS_REGION)

    try:
        # Get cluster details
        cluster = ecs.describe_clusters(clusters=[CLUSTER_NAME])['clusters'][0]

        # Get VPC details from cluster
        # For now, use default configuration
        subnets = boto3.client('ec2', region_name=AWS_REGION).describe_subnets(
            Filters=[{'Name': 'tag:Name', 'Values': ['*private*']}]
        )['Subnets']

        subnet_ids = [s['SubnetId'] for s in subnets[:2]]

        # Get security groups
        sgs = ec2.describe_security_groups(
            Filters=[{'Name': 'group-name', 'Values': [f'*{PROJECT_NAME}*loader*']}]
        )['SecurityGroups']

        sg_ids = [sg['GroupId'] for sg in sgs] if sgs else []

        return {
            'awsvpcConfiguration': {
                'subnets': subnet_ids,
                'securityGroups': sg_ids,
                'assignPublicIp': 'DISABLED'
            }
        }
    except Exception as e:
        print(f"Warning: Could not get VPC config: {e}")
        return {'awsvpcConfiguration': {'subnets': [], 'securityGroups': []}}

def trigger_loader(task_name, vpc_config):
    """Trigger a single ECS loader task."""
    ecs = boto3.client('ecs', region_name=AWS_REGION)

    try:
        response = ecs.run_task(
            cluster=CLUSTER_NAME,
            taskDefinition=task_name,
            launchType='FARGATE',
            networkConfiguration=vpc_config,
            count=1
        )

        if response['tasks']:
            task_id = response['tasks'][0]['taskArn'].split('/')[-1]
            print(f"  ✓ {task_name} → {task_id}")
            return task_id
        else:
            print(f"  ✗ Failed to start {task_name}")
            return None
    except ClientError as e:
        print(f"  ✗ Error starting {task_name}: {e}")
        return None

def wait_for_task(task_id, task_name):
    """Wait for an ECS task to complete."""
    ecs = boto3.client('ecs', region_name=AWS_REGION)
    timeout = 3600  # 1 hour
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = ecs.describe_tasks(
                cluster=CLUSTER_NAME,
                tasks=[task_id]
            )

            if response['tasks']:
                task = response['tasks'][0]
                status = task['lastStatus']

                if status == 'STOPPED':
                    exit_code = task['containers'][0].get('exitCode', -1)
                    if exit_code == 0:
                        print(f"    ✓ {task_name} completed successfully")
                        return True
                    else:
                        print(f"    ✗ {task_name} failed (exit code: {exit_code})")
                        return False
        except Exception as e:
            print(f"    Error checking status: {e}")

        time.sleep(10)

    print(f"    ✗ {task_name} timeout after {timeout}s")
    return False

def main():
    parser = argparse.ArgumentParser(description='Trigger AWS ECS data loaders')
    parser.add_argument('--access-key', help='AWS Access Key ID')
    parser.add_argument('--secret-key', help='AWS Secret Access Key')
    parser.add_argument('--quick', action='store_true', help='Load only Tier 0-1 (symbols and prices)')
    parser.add_argument('--tier', type=int, help='Load specific tier (0-2)')
    parser.add_argument('--wait', action='store_true', help='Wait for loaders to complete')

    args = parser.parse_args()

    # Configure AWS
    configure_aws(args.access_key, args.secret_key)

    # Select loaders to run
    if args.tier == 0:
        loaders = TIER_0_LOADERS
    elif args.tier == 1:
        loaders = TIER_0_LOADERS + TIER_1_LOADERS + TIER_1B_LOADERS + TIER_1C_LOADERS
    elif args.tier == 2:
        loaders = TIER_0_LOADERS + TIER_1_LOADERS + TIER_1B_LOADERS + TIER_1C_LOADERS + TIER_2_LOADERS
    elif args.quick:
        loaders = QUICK_LOADERS
    else:
        # Default: Tiers 0-1 (quick load)
        loaders = QUICK_LOADERS

    print("=" * 70)
    print(f"TRIGGERING DATA LOADERS ({len(loaders)} tasks)")
    print("=" * 70)
    print()

    # Get VPC config
    vpc_config = get_vpc_config()

    # Trigger loaders
    tasks = {}
    for loader_name in loaders:
        print(f"Triggering: {loader_name}")
        task_id = trigger_loader(loader_name, vpc_config)
        if task_id:
            tasks[task_id] = loader_name
        time.sleep(0.5)  # Avoid throttling

    print()
    print(f"Started {len(tasks)} tasks")

    if args.wait:
        print()
        print("Waiting for loaders to complete...")
        print("=" * 70)

        completed = 0
        failed = 0

        for task_id, task_name in tasks.items():
            if wait_for_task(task_id, task_name):
                completed += 1
            else:
                failed += 1

        print()
        print(f"Results: {completed} completed, {failed} failed")

        if failed == 0:
            print()
            print("✓ All data loaders completed successfully!")
            print("✓ Database should now be populated")
            print("✓ Frontend should display data")
        else:
            print()
            print(f"✗ {failed} loaders failed - check CloudWatch logs")
    else:
        print()
        print("To wait for completion, run with --wait flag:")
        print(f"  python3 trigger_data_loaders.py --wait")
        print()
        print("To check progress, view CloudWatch logs:")
        print(f"  aws logs tail /aws/ecs/algo-loaders --follow")

if __name__ == '__main__':
    main()
