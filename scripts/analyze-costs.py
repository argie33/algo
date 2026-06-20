#!/usr/bin/env python3
"""
Analyze infrastructure costs and identify optimization opportunities.
"""

import boto3
from datetime import datetime, timedelta

def analyze_costs():
    # Cost Explorer client
    ce_client = boto3.client('ce', region_name='us-east-1')

    print("\n" + "="*60)
    print("COST ANALYSIS (Last 7 Days)")
    print("="*60)

    # Get cost data grouped by service
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'End': datetime.now().strftime('%Y-%m-%d'),
            },
            Granularity='DAILY',
            Filter={
                'Tags': {
                    'Key': 'Environment',
                    'Values': ['dev']
                }
            },
            Metrics=['UnblendedCost'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ]
        )

        total_cost = 0.0
        costs_by_service = {}

        for result in response['ResultsByTime']:
            for group in result['Groups']:
                service = group['Keys'][0]
                cost = float(group['Metrics']['UnblendedCost']['Amount'])

                if service not in costs_by_service:
                    costs_by_service[service] = 0.0
                costs_by_service[service] += cost
                total_cost += cost

        # Print sorted by cost
        print("\nCosts by Service (Last 7 Days):")
        print("-" * 60)

        for service, cost in sorted(costs_by_service.items(), key=lambda x: x[1], reverse=True):
            pct = (float(cost) / total_cost * 100) if total_cost > 0 else 0
            print(f"{service:30} ${float(cost):8.2f}  ({pct:5.1f}%)")

        print("-" * 60)
        print(f"{'TOTAL':30} ${total_cost:8.2f}")

    except Exception as e:
        print(f"[ERROR] {e}")

def check_resources():
    """Check for common cost issues"""
    print("\n" + "="*60)
    print("RESOURCE AUDIT - COST OPTIMIZATION")
    print("="*60)

    ec2 = boto3.client('ec2', region_name='us-east-1')

    # Check for unused/stopped instances
    print("\n[Checking] EC2 Instances...")
    try:
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
            ]
        )

        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                state = instance['State']['Name']
                instance_type = instance['InstanceType']

                # Check if it's a bastion (based on tags)
                tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}
                name = tags.get('Name', 'No Name')

                print(f"  Instance: {instance_id} ({name})")
                print(f"    Type: {instance_type} | State: {state}")

                if state == 'stopped':
                    print(f"    [WARNING] Instance is STOPPED - Consider terminating if unused")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # Check EBS volumes
    print("\n[Checking] EBS Volumes...")
    try:
        response = ec2.describe_volumes(
            Filters=[
                {'Name': 'status', 'Values': ['available']}  # Unattached volumes
            ]
        )

        if response['Volumes']:
            print(f"  Found {len(response['Volumes'])} unattached volume(s):")
            for vol in response['Volumes']:
                vol_id = vol['VolumeId']
                size = vol['Size']
                print(f"    {vol_id}: {size}GB (UNATTACHED - Delete if unused)")
        else:
            print("  [OK] No unattached EBS volumes")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # Check elastic IPs
    print("\n[Checking] Elastic IPs...")
    try:
        response = ec2.describe_addresses()

        unused_eips = []
        for addr in response['Addresses']:
            if 'InstanceId' not in addr or not addr['InstanceId']:
                unused_eips.append(addr['PublicIp'])

        if unused_eips:
            print(f"  [WARNING] Found {len(unused_eips)} unassociated Elastic IP(s):")
            for eip in unused_eips:
                print(f"    {eip} - Costs $0.005/hour when unassociated")
        else:
            print("  [OK] No unassociated Elastic IPs")
    except Exception as e:
        print(f"  [ERROR] {e}")

def main():
    print("AWS Cost Analysis Tool")
    print(f"Started: {datetime.now().isoformat()}")

    try:
        # Test connection
        sts = boto3.client('sts', region_name='us-east-1')
        identity = sts.get_caller_identity()
        print(f"Account: {identity['Account']}")

        # Run analyses
        analyze_costs()
        check_resources()

        print("\n" + "="*60)
        print("Analysis Complete")
        print("="*60)
        print("\nRecommendations:")
        print("1. Check RDS for unused databases or over-provisioned instances")
        print("2. Review S3 buckets for old/unused data (enable lifecycle policies)")
        print("3. Check Lambda functions for excessive memory allocation")
        print("4. Verify no production resources in dev account")

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    main()
