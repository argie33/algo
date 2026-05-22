#!/usr/bin/env python3
"""
Audit unmanaged AWS resources and identify candidates for removal.
Compares Terraform state against actual AWS resources.
"""

import json
import subprocess
import sys
from collections import defaultdict

def run_cmd(cmd):
    """Execute AWS CLI command and return JSON."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None
    try:
        return json.loads(result.stdout)
    except:
        return None

def get_terraform_resources():
    """Get all resources from Terraform state."""
    result = subprocess.run(
        "terraform state list",
        shell=True,
        capture_output=True,
        text=True,
        cwd="terraform"
    )
    if result.returncode != 0:
        print(f"Terraform error: {result.stderr}")
        return []
    return [line.strip() for line in result.stdout.split('\n') if line.strip()]

def get_managed_s3_buckets(tf_resources):
    """Extract S3 bucket names from Terraform state."""
    buckets = set()
    for res in tf_resources:
        if 'aws_s3_bucket' in res and 's3_bucket.' in res:
            # Get bucket name from state
            result = subprocess.run(
                f"terraform state show {res}",
                shell=True,
                capture_output=True,
                text=True,
                cwd="terraform"
            )
            if 'bucket' in result.stdout:
                for line in result.stdout.split('\n'):
                    if 'bucket' in line and '=' in line:
                        bucket_name = line.split('=')[1].strip().strip('"')
                        if bucket_name:
                            buckets.add(bucket_name)
    return buckets

def get_actual_s3_buckets():
    """Get all S3 buckets from AWS."""
    data = run_cmd('aws s3api list-buckets --region us-east-1 --output json')
    if not data:
        return set()
    return {b['Name'] for b in data.get('Buckets', [])}

def get_actual_lambda_functions():
    """Get all Lambda functions from AWS."""
    data = run_cmd('aws lambda list-functions --region us-east-1 --output json')
    if not data:
        return set()
    return {f['FunctionName'] for f in data.get('Functions', [])}

def get_managed_lambda(tf_resources):
    """Extract Lambda function names from Terraform."""
    funcs = set()
    for res in tf_resources:
        if 'aws_lambda_function' in res:
            result = subprocess.run(
                f"terraform state show {res}",
                shell=True,
                capture_output=True,
                text=True,
                cwd="terraform"
            )
            for line in result.stdout.split('\n'):
                if 'function_name' in line and '=' in line:
                    func_name = line.split('=')[1].strip().strip('"')
                    if func_name:
                        funcs.add(func_name)
    return funcs

def get_actual_ecs_clusters():
    """Get all ECS clusters."""
    data = run_cmd('aws ecs list-clusters --region us-east-1 --output json')
    if not data:
        return set()
    return {arn.split('/')[-1] for arn in data.get('clusterArns', [])}

def get_actual_rds_instances():
    """Get all RDS instances."""
    data = run_cmd('aws rds describe-db-instances --region us-east-1 --output json')
    if not data:
        return set()
    return {db['DBInstanceIdentifier'] for db in data.get('DBInstances', [])}

def main():
    print("=" * 80)
    print("AWS RESOURCE AUDIT - UNMANAGED RESOURCES")
    print("=" * 80)

    tf_resources = get_terraform_resources()
    print(f"\n[INFO] Terraform manages {len(tf_resources)} resources\n")

    # S3 Audit
    print("S3 BUCKETS")
    print("-" * 80)
    managed_s3 = get_managed_s3_buckets(tf_resources)
    actual_s3 = get_actual_s3_buckets()
    unmanaged_s3 = actual_s3 - managed_s3

    print(f"Managed by Terraform:   {len(managed_s3)}")
    for b in sorted(managed_s3):
        print(f"  [MANAGED] {b}")

    print(f"\nActual in AWS:           {len(actual_s3)}")
    for b in sorted(actual_s3):
        print(f"  {b}")

    if unmanaged_s3:
        print(f"\n[WARNING] UNMANAGED (NOT IN TERRAFORM): {len(unmanaged_s3)}")
        for b in sorted(unmanaged_s3):
            print(f"  [REMOVE] {b}")
    else:
        print(f"\n[OK] All S3 buckets managed by Terraform")

    # Lambda Audit
    print("\n\nLAMBDA FUNCTIONS")
    print("-" * 80)
    managed_lambda = get_managed_lambda(tf_resources)
    actual_lambda = get_actual_lambda_functions()
    unmanaged_lambda = actual_lambda - managed_lambda

    print(f"Managed by Terraform:   {len(managed_lambda)}")
    for f in sorted(managed_lambda):
        print(f"  [MANAGED] {f}")

    print(f"\nActual in AWS:           {len(actual_lambda)}")
    for f in sorted(actual_lambda):
        print(f"  {f}")

    if unmanaged_lambda:
        print(f"\n[WARNING] UNMANAGED (NOT IN TERRAFORM): {len(unmanaged_lambda)}")
        for f in sorted(unmanaged_lambda):
            print(f"  [REMOVE] {f}")
    else:
        print(f"\n[OK] All Lambda functions managed by Terraform")

    # ECS Audit
    print("\n\nECS CLUSTERS")
    print("-" * 80)
    actual_ecs = get_actual_ecs_clusters()
    print(f"Actual in AWS: {len(actual_ecs)}")
    for cluster in sorted(actual_ecs):
        is_managed = any('aws_ecs_cluster' in res and cluster in res for res in tf_resources)
        status = "[MANAGED]" if is_managed else "[REMOVE]"
        print(f"  {status} {cluster}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    total_unmanaged = len(unmanaged_s3) + len(unmanaged_lambda)
    print(f"Total unmanaged resources: {total_unmanaged}")

    if total_unmanaged > 0:
        print("\n[ACTION REQUIRED] Remove the resources marked with [REMOVE]")
        print("Then implement Service Control Policies (SCPs) to prevent manual creation.")
    else:
        print("\n[OK] All resources are managed by Terraform!")

if __name__ == "__main__":
    main()
