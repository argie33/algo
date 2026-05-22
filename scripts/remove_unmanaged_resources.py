#!/usr/bin/env python3
"""
Remove unmanaged AWS resources.
Only S3 buckets and Lambda functions - ECS clusters handled separately.
"""

import subprocess
import json

def run_cmd(cmd, region="us-east-1"):
    """Execute AWS CLI command."""
    full_cmd = cmd.replace("{region}", region)
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def delete_s3_bucket(bucket_name):
    """Delete S3 bucket and all contents."""
    print(f"\n[S3] Deleting bucket: {bucket_name}")

    # List and delete all objects
    print(f"  - Emptying bucket...")
    code, out, err = run_cmd(
        f'aws s3 rm s3://{bucket_name} --recursive --region {{region}} 2>&1'
    )
    if code != 0:
        print(f"    Warning: {err}")

    # Delete the bucket
    code, out, err = run_cmd(
        f'aws s3api delete-bucket --bucket {bucket_name} --region {{region}} 2>&1'
    )
    if code == 0:
        print(f"  [OK] Bucket deleted")
    else:
        print(f"  [ERROR] {err}")

def delete_lambda(function_name):
    """Delete Lambda function."""
    print(f"\n[Lambda] Deleting function: {function_name}")
    code, out, err = run_cmd(
        f'aws lambda delete-function --function-name {function_name} --region {{region}} 2>&1'
    )
    if code == 0:
        print(f"  [OK] Function deleted")
    else:
        print(f"  [ERROR] {err}")

def delete_ecs_cluster(cluster_name):
    """Delete ECS cluster (empty only)."""
    print(f"\n[ECS] Deleting cluster: {cluster_name}")

    # List and delete services
    code, out, err = run_cmd(
        f'aws ecs list-services --cluster {cluster_name} --region {{region}} --output json'
    )
    if code == 0:
        services = json.loads(out).get('serviceArns', [])
        for service_arn in services:
            service_name = service_arn.split('/')[-1]
            print(f"  - Deleting service: {service_name}")
            run_cmd(
                f'aws ecs delete-service --cluster {cluster_name} --service {service_name} '
                f'--force --region {{region}} 2>&1'
            )

    # List and terminate container instances
    code, out, err = run_cmd(
        f'aws ecs list-container-instances --cluster {cluster_name} --region {{region}} --output json'
    )
    if code == 0:
        instances = json.loads(out).get('containerInstanceArns', [])
        if instances:
            instance_ids = [arn.split('/')[-1] for arn in instances]
            for instance_id in instance_ids:
                print(f"  - Terminating instance: {instance_id}")
                run_cmd(
                    f'aws ecs update-container-instance-state --cluster {cluster_name} '
                    f'--container-instance {instance_id} --status INACTIVE --region {{region}} 2>&1'
                )

    # Delete the cluster
    code, out, err = run_cmd(
        f'aws ecs delete-cluster --cluster {cluster_name} --region {{region}} 2>&1'
    )
    if code == 0:
        print(f"  [OK] Cluster deleted")
    else:
        print(f"  [WARNING] {err}")

def main():
    print("=" * 80)
    print("REMOVING UNMANAGED AWS RESOURCES")
    print("=" * 80)

    # Unmanaged S3 buckets
    s3_to_remove = [
        "algo-cf-templates-626216981288",
        "algo-terraform-state-dev",
        "stocks-core-algoartifactsbucket-itxgch0igggk",
        "stocks-core-cftemplatesbucket-byjdqhvlyp1o",
        "stocks-core-cftemplatesbucket-yesjt7jywetz",
        "stocks-core-codebucket-3ebfeu44yqrr",
        "stocks-logs-archive-626216981288",
        "terraform-state-626216981288-us-east-1",
    ]

    # Unmanaged Lambda
    lambda_to_remove = [
        "algo-db-init-dev",
    ]

    # ECS clusters (note: terraform-20260509/20260510 are temp AWS Batch clusters)
    ecs_to_remove = [
        "algo-cluster",
        "stocks-cluster",
    ]

    print("\n[PHASE 1] S3 Buckets")
    print("-" * 80)
    for bucket in s3_to_remove:
        delete_s3_bucket(bucket)

    print("\n\n[PHASE 2] Lambda Functions")
    print("-" * 80)
    for func in lambda_to_remove:
        delete_lambda(func)

    print("\n\n[PHASE 3] ECS Clusters")
    print("-" * 80)
    print("[NOTE] AWS Batch temporary clusters will auto-cleanup after job completion.")
    print("       Manually deleting named clusters only:")
    for cluster in ecs_to_remove:
        delete_ecs_cluster(cluster)

    print("\n" + "=" * 80)
    print("CLEANUP COMPLETE")
    print("=" * 80)
    print("\nNext: Implement Service Control Policies (SCPs) to prevent manual creation.")
    print("      See: scp_deny_unmanaged_resources.json")

if __name__ == "__main__":
    main()
