#!/usr/bin/env python3
"""
AWS Infrastructure Audit: Identify unused resources and cost drivers.
"""

import boto3
import json
from datetime import datetime, timedelta
import sys
import os

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def get_session():
    """Get AWS session with algo-developer profile"""
    return boto3.Session(profile_name='algo-developer', region_name='us-east-1')

def audit_lambdas(session):
    """Check Lambda functions and their usage"""
    client = session.client('lambda')
    cloudwatch = session.client('cloudwatch')

    print("\n" + "="*60)
    print("LAMBDA FUNCTIONS")
    print("="*60)

    try:
        response = client.list_functions()
        if not response['Functions']:
            print("[OK] No Lambda functions found")
            return

        for func in response['Functions']:
            name = func['FunctionName']
            runtime = func['Runtime']
            memory = func['MemorySize']
            timeout = func['Timeout']
            state = func.get('State', 'Unknown')

            # Get invocation metrics
            try:
                metrics = cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Invocations',
                    Dimensions=[{'Name': 'FunctionName', 'Value': name}],
                    StartTime=datetime.utcnow() - timedelta(days=7),
                    EndTime=datetime.utcnow(),
                    Period=86400,  # Daily
                    Statistics=['Sum']
                )
                invocations = sum(dp['Sum'] for dp in metrics.get('Datapoints'))
            except Exception as e:
                invocations = 'ERROR'

            print(f"\n[OK] {name}")
            print(f"  Runtime: {runtime} | Memory: {memory}MB | Timeout: {timeout}s")
            print(f"  State: {state}")
            print(f"  Invocations (7d): {invocations}")
    except Exception as e:
        print(f"[ERROR] {e}")

def audit_rds(session):
    """Check RDS databases"""
    client = session.client('rds')

    print("\n" + "="*60)
    print("RDS DATABASES")
    print("="*60)

    try:
        response = client.describe_db_instances()
        if not response['DBInstances']:
            print("[OK] No RDS instances found")
            return

        for db in response['DBInstances']:
            name = db['DBInstanceIdentifier']
            engine = db['Engine']
            instance_class = db['DBInstanceClass']
            status = db['DBInstanceStatus']
            allocated_storage = db['AllocatedStorage']
            multi_az = db['MultiAZ']

            print(f"\n[OK] {name}")
            print(f"  Engine: {engine} | Instance: {instance_class}")
            print(f"  Status: {status} | Storage: {allocated_storage}GB | Multi-AZ: {multi_az}")
    except Exception as e:
        print(f"[ERROR] {e}")

def audit_ecs(session):
    """Check ECS clusters and tasks"""
    client = session.client('ecs')

    print("\n" + "="*60)
    print("ECS CLUSTERS & TASKS")
    print("="*60)

    try:
        clusters = client.list_clusters().get('clusterArns')
        if not clusters:
            print("[OK] No ECS clusters found")
            return

        for cluster_arn in clusters:
            cluster_name = cluster_arn.split('/')[-1]
            print(f"\n[OK] Cluster: {cluster_name}")

            # Get services
            services = client.list_services(cluster=cluster_arn).get('serviceArns')
            if services:
                for service_arn in services:
                    service_name = service_arn.split('/')[-1]
                    service_detail = client.describe_services(
                        cluster=cluster_arn,
                        services=[service_arn]
                    )['services'][0]
                    status = service_detail['status']
                    running = service_detail.get('runningCount', 0)
                    desired = service_detail.get('desiredCount', 0)
                    print(f"  Service: {service_name} (Status: {status}, Running: {running}, Desired: {desired})")
            else:
                print("  No services in cluster")

            # Get tasks
            tasks = client.list_tasks(cluster=cluster_arn).get('taskArns')
            print(f"  Total tasks: {len(tasks)}")
    except Exception as e:
        print(f"[ERROR] {e}")

def audit_s3(session):
    """Check S3 buckets and storage"""
    client = session.client('s3')
    cloudwatch = session.client('cloudwatch')

    print("\n" + "="*60)
    print("S3 BUCKETS")
    print("="*60)

    try:
        response = client.list_buckets()
        if not response['Buckets']:
            print("[OK] No S3 buckets found")
            return

        for bucket in response['Buckets']:
            name = bucket['Name']
            created = bucket['CreationDate']

            # Check if bucket belongs to 'algo' environment (has -dev or algo in name)
            if 'algo' not in name and '-dev' not in name:
                continue

            # Get bucket size from CloudWatch
            try:
                metrics = cloudwatch.get_metric_statistics(
                    Namespace='AWS/S3',
                    MetricName='BucketSizeBytes',
                    Dimensions=[
                        {'Name': 'BucketName', 'Value': name},
                        {'Name': 'StorageType', 'Value': 'StandardStorage'}
                    ],
                    StartTime=datetime.utcnow() - timedelta(days=1),
                    EndTime=datetime.utcnow(),
                    Period=86400,
                    Statistics=['Average']
                )
                size_gb = 0
                if metrics['Datapoints']:
                    size_bytes = metrics['Datapoints'][0]['Average']
                    size_gb = size_bytes / (1024**3)
            except:
                size_gb = 'Unknown'

            print(f"\n[OK] {name}")
            print(f"  Created: {created}")
            print(f"  Size: {size_gb:.2f}GB" if isinstance(size_gb, float) else f"  Size: {size_gb}")
    except Exception as e:
        print(f"[ERROR] {e}")

def audit_events(session):
    """Check EventBridge rules and schedules"""
    client = session.client('events')

    print("\n" + "="*60)
    print("EVENTBRIDGE RULES & SCHEDULES")
    print("="*60)

    try:
        response = client.list_rules()
        if not response['Rules']:
            print("[OK] No EventBridge rules found")
            return

        for rule in response['Rules']:
            name = rule['Name']
            state = rule['State']
            schedule_expr = rule.get('ScheduleExpression', 'N/A')
            description = rule.get('Description', 'N/A')

            print(f"\n[OK] {name}")
            print(f"  State: {state}")
            if schedule_expr != 'N/A':
                print(f"  Schedule: {schedule_expr}")
    except Exception as e:
        print(f"[ERROR] {e}")

def audit_dynamodb(session):
    """Check DynamoDB tables"""
    client = session.client('dynamodb')

    print("\n" + "="*60)
    print("DYNAMODB TABLES")
    print("="*60)

    try:
        response = client.list_tables()
        if not response['TableNames']:
            print("[OK] No DynamoDB tables found")
            return

        for table_name in response['TableNames']:
            if 'algo' not in table_name and '-dev' not in table_name:
                continue

            details = client.describe_table(TableName=table_name)['Table']
            status = details['TableStatus']
            billing_mode = details.get('BillingModeSummary').get('BillingMode', 'PROVISIONED')
            item_count = details.get('ItemCount', 0)
            size_bytes = details.get('TableSizeBytes', 0)

            print(f"\n[OK] {table_name}")
            print(f"  Status: {status} | Billing: {billing_mode}")
            print(f"  Items: {item_count} | Size: {size_bytes / (1024**2):.2f}MB")
    except Exception as e:
        print(f"[ERROR] {e}")

def main():
    print("AWS Infrastructure Audit - Algo Trading System")
    print(f"Started: {datetime.now().isoformat()}")

    try:
        session = get_session()

        # Test connection
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        print(f"\nAccount: {identity['Account']}")
        print(f"ARN: {identity['Arn']}")

        # Run audits
        audit_lambdas(session)
        audit_rds(session)
        audit_ecs(session)
        audit_s3(session)
        audit_events(session)
        audit_dynamodb(session)

        print("\n" + "="*60)
        print("Audit Complete")
        print("="*60)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
