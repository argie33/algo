#!/usr/bin/env python3
"""Check AWS CloudFormation and deployment status."""

import os
import sys

# Credentials should come from:
# 1. ~/.aws/credentials file (stored locally)
# 2. AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars
# 3. IAM role if running in AWS
# DO NOT hardcode credentials here!

try:
    import boto3
except ImportError:
    print("Installing boto3...")
    os.system('python3 -m pip install boto3 -q')
    import boto3

print("=" * 80)
print("AWS ACCOUNT STATUS CHECK")
print("=" * 80)
print()

try:
    # Create clients
    cf = boto3.client('cloudformation', region_name='us-east-1')
    ecs = boto3.client('ecs', region_name='us-east-1')
    rds = boto3.client('rds', region_name='us-east-1')

    # 1. Check CloudFormation stacks
    print("1. CLOUDFORMATION STACKS")
    print("-" * 80)

    try:
        response = cf.describe_stacks(StackName='stocks-app-stack')
        stack = response['Stacks'][0]
        print(f"  stocks-app-stack:")
        print(f"    Status: {stack['StackStatus']}")
        print(f"    Created: {stack['CreationTime']}")
        if 'StackStatusReason' in stack:
            print(f"    Reason: {stack['StackStatusReason']}")
    except cf.exceptions.ClientError as e:
        if 'does not exist' in str(e):
            print("  stocks-app-stack: DOES NOT EXIST")
        else:
            print(f"  stocks-app-stack: ERROR - {str(e)[:100]}")

    # List all active stacks
    print()
    print("  All active CloudFormation stacks:")
    try:
        response = cf.list_stacks(
            StackStatusFilter=['CREATE_COMPLETE', 'UPDATE_COMPLETE']
        )
        stacks = response.get('StackSummaries', [])
        if stacks:
            for stack in stacks[:10]:
                print(f"    - {stack['StackName']}: {stack['StackStatus']}")
        else:
            print("    NONE")
    except Exception as e:
        print(f"    ERROR: {str(e)[:100]}")

    # 2. Check CloudFormation exports
    print()
    print("2. CLOUDFORMATION EXPORTS")
    print("-" * 80)

    try:
        response = cf.list_exports()
        exports = response.get('Exports', [])

        # Look for our critical export
        cluster_export = [e for e in exports if e['Name'] == 'StocksApp-ClusterArn']
        if cluster_export:
            print(f"  StocksApp-ClusterArn: FOUND")
            print(f"    Value: {cluster_export[0]['Value']}")
        else:
            print(f"  StocksApp-ClusterArn: NOT FOUND [CRITICAL BLOCKER]")

        # Show sample exports
        if exports:
            print(f"\n  Total exports in region: {len(exports)}")
            print("  Sample exports:")
            for exp in exports[:5]:
                print(f"    - {exp['Name']}")
        else:
            print("  NO EXPORTS DEFINED")
    except Exception as e:
        print(f"  ERROR: {str(e)[:100]}")

    # 3. Check ECS cluster
    print()
    print("3. ECS CLUSTER")
    print("-" * 80)

    try:
        clusters = ecs.list_clusters()
        cluster_arns = clusters.get('clusterArns', [])
        if cluster_arns:
            print(f"  ECS Clusters: {len(cluster_arns)} found")
            for arn in cluster_arns:
                print(f"    - {arn}")
                # Get cluster details
                cluster_name = arn.split('/')[-1]
                try:
                    details = ecs.describe_clusters(clusters=[cluster_name])
                    if details['clusters']:
                        cluster = details['clusters'][0]
                        print(f"      Status: {cluster['status']}")
                        print(f"      Active services: {cluster['activeServicesCount']}")
                        print(f"      Registered tasks: {cluster['registeredContainerInstancesCount']}")
                except:
                    pass
        else:
            print("  ECS Clusters: NONE [CRITICAL]")
    except Exception as e:
        print(f"  ERROR: {str(e)[:100]}")

    # 4. Check RDS database
    print()
    print("4. RDS DATABASE")
    print("-" * 80)

    try:
        response = rds.describe_db_instances()
        dbs = response.get('DBInstances', [])

        if dbs:
            print(f"  RDS Databases: {len(dbs)} found")
            for db in dbs:
                print(f"    - {db['DBInstanceIdentifier']}")
                print(f"      Engine: {db['Engine']} {db['EngineVersion']}")
                print(f"      Status: {db['DBInstanceStatus']}")
                if 'Endpoint' in db and 'Address' in db['Endpoint']:
                    print(f"      Endpoint: {db['Endpoint']['Address']}")
        else:
            print("  RDS Databases: NONE")
    except Exception as e:
        print(f"  ERROR: {str(e)[:100]}")

    # 5. Summary
    print()
    print("=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    # Check what's missing
    issues = []

    try:
        response = cf.describe_stacks(StackName='stocks-app-stack')
        stack = response['Stacks'][0]
        if stack['StackStatus'] not in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']:
            issues.append(f"stocks-app-stack is in {stack['StackStatus']} state")
    except:
        issues.append("stocks-app-stack does not exist")

    try:
        response = cf.list_exports()
        exports = response.get('Exports', [])
        if not any(e['Name'] == 'StocksApp-ClusterArn' for e in exports):
            issues.append("StocksApp-ClusterArn export is missing (CRITICAL)")
    except:
        issues.append("Cannot read exports")

    try:
        clusters = ecs.list_clusters()
        if not clusters.get('clusterArns'):
            issues.append("No ECS cluster exists")
    except:
        issues.append("Cannot read ECS clusters")

    if issues:
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"  [ ] {issue}")
    else:
        print("ALL CHECKS PASSED - AWS infrastructure is ready!")

    print()
    print("NEXT STEPS:")
    if any('StocksApp-ClusterArn' in issue for issue in issues):
        print("  1. Deploy template-app-stocks.yml to create cluster and exports")
        print("  2. Then deploy template-app-ecs-tasks.yml")
        print("  3. Then loaders can run in ECS")
    else:
        print("  Infrastructure is ready - check GitHub Actions workflow")

except Exception as e:
    print(f"CRITICAL ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
