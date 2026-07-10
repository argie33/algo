#!/usr/bin/env python3
"""Fix Lambda VPC configuration to allow database access."""

import json
import subprocess
import sys

def run_aws(cmd):
    """Run AWS CLI command and return JSON output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        return None
    return json.loads(result.stdout) if result.stdout.strip() else None

def main():
    print("=" * 50)
    print("FIXING LAMBDA VPC CONFIGURATION")
    print("=" * 50)
    print()

    AWS_REGION = "us-east-1"
    LAMBDA_FUNCTION = "algo-api-dev"

    # [1] Get RDS database details
    print("[1] Getting RDS database details...")
    rds_output = run_aws(
        f'aws rds describe-db-instances --db-instance-identifier algo-db --region {AWS_REGION} --output json'
    )
    if not rds_output or not rds_output.get('DBInstances'):
        print("ERROR: Could not find algo-db RDS instance")
        return 1

    db = rds_output['DBInstances'][0]
    db_vpc_id = db['DBSubnetGroup']['VpcId']
    db_subnets = [s['SubnetIdentifier'] for s in db['DBSubnetGroup']['Subnets']]
    db_sg = db['VpcSecurityGroups'][0]['VpcSecurityGroupId']

    print(f"   Database VPC ID: {db_vpc_id}")
    print(f"   Database Security Group: {db_sg}")
    print(f"   Database Subnets: {', '.join(db_subnets)}")
    print()

    # [2] Get Lambda current configuration
    print("[2] Getting Lambda current configuration...")
    lambda_output = run_aws(
        f'aws lambda get-function --function-name {LAMBDA_FUNCTION} --region {AWS_REGION} --output json'
    )
    if not lambda_output:
        print("ERROR: Could not get Lambda configuration")
        return 1

    current_vpc = lambda_output['Configuration'].get('VpcConfig', {})
    print(f"   Current VPC Config: {current_vpc}")
    print()

    # [3] Create/Get Lambda security group
    print("[3] Creating/getting Lambda security group...")
    sg_output = run_aws(
        f'aws ec2 describe-security-groups --filters Name=group-name,Values=algo-lambda-sg --region {AWS_REGION} --output json'
    )

    if sg_output and sg_output.get('SecurityGroups'):
        lambda_sg_id = sg_output['SecurityGroups'][0]['GroupId']
        print(f"   Using existing Lambda SG: {lambda_sg_id}")
    else:
        sg_create = run_aws(
            f'aws ec2 create-security-group --group-name algo-lambda-sg '
            f'--description "Security group for algo Lambda to access RDS" '
            f'--vpc-id {db_vpc_id} --region {AWS_REGION} --output json'
        )
        if not sg_create:
            print("ERROR: Could not create security group")
            return 1
        lambda_sg_id = sg_create['GroupId']
        print(f"   Created Lambda SG: {lambda_sg_id}")
    print()

    # [4] Allow RDS inbound from Lambda
    print("[4] Updating RDS security group to allow inbound from Lambda...")
    auth_result = subprocess.run(
        f'aws ec2 authorize-security-group-ingress --group-id {db_sg} '
        f'--protocol tcp --port 5432 --source-group {lambda_sg_id} '
        f'--region {AWS_REGION}',
        shell=True, capture_output=True, text=True
    )
    if auth_result.returncode == 0:
        print("   ✓ Rule added")
    else:
        print("   (Rule may already exist)")
    print()

    # [5] Update Lambda VPC configuration
    print("[5] Updating Lambda VPC configuration...")
    vpc_config = f"SubnetIds={','.join(db_subnets)},SecurityGroupIds={lambda_sg_id}"
    update_result = subprocess.run(
        f'aws lambda update-function-configuration --function-name {LAMBDA_FUNCTION} '
        f'--vpc-config {vpc_config} --region {AWS_REGION} --output json',
        shell=True, capture_output=True, text=True
    )
    if update_result.returncode == 0:
        updated_vpc = json.loads(update_result.stdout).get('VpcConfig', {})
        print(f"   Updated VPC Config: {updated_vpc}")
    else:
        print(f"   ERROR: {update_result.stderr}")
        return 1

    print()
    print("=" * 50)
    print("LAMBDA VPC CONFIGURATION FIXED")
    print("=" * 50)
    print()
    print("Next steps:")
    print("1. Wait 60 seconds for Lambda to update")
    print("2. Re-deploy Lambda code: gh workflow run deploy-api-lambda.yml")
    print("3. Test circuit-breakers: curl https://<api-url>/api/algo/circuit-breakers -H 'Authorization: Bearer <token>'")
    print()

    return 0

if __name__ == '__main__':
    sys.exit(main())
