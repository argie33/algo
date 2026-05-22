#!/usr/bin/env python3
"""
Identify ACTUAL manually created resources (not auto-generated like ENIs, log groups, etc.)
Focus on resources with CloudFormation stack tags or untagged primary resources.
"""

import subprocess
import json

def run_cmd(cmd, region="us-east-1"):
    """Execute AWS CLI command."""
    full_cmd = cmd.replace("{region}", region)
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

region = "us-east-1"
print("=" * 100)
print("IDENTIFYING ACTUAL UNMANAGED RESOURCES (CloudFormation + Manual)")
print("=" * 100)

# 1. Find orphaned VPCs (not the main algo VPC)
print("\n1. VPCs")
print("-" * 100)
code, out, err = run_cmd("aws ec2 describe-vpcs --region {region} --output json")
vpcs = json.loads(out).get('Vpcs', [])
main_vpc = "vpc-04519b1cc434f7947"  # The Terraform-managed one
for vpc in vpcs:
    if vpc['VpcId'] != main_vpc:
        tags = {t['Key']: t['Value'] for t in vpc.get('Tags', [])}
        cf_stack = tags.get('aws:cloudformation:stack-name')
        print(f"  [ORPHANED] {vpc['VpcId']} - {tags.get('Name', 'N/A')} (CF: {cf_stack})")

# 2. Find CloudFormation stacks
print("\n2. CloudFormation Stacks")
print("-" * 100)
code, out, err = run_cmd("aws cloudformation list-stacks --region {region} --output json")
stacks = json.loads(out).get('StackSummaries', [])
for stack in stacks:
    if stack['StackStatus'] != 'DELETE_COMPLETE':
        print(f"  [CF-STACK] {stack['StackName']} - Status: {stack['StackStatus']}")

# 3. Unassociated Elastic IPs
print("\n3. Unassociated Elastic IPs")
print("-" * 100)
code, out, err = run_cmd("aws ec2 describe-addresses --region {region} --output json")
eips = json.loads(out).get('Addresses', [])
for eip in eips:
    if 'AssociationId' not in eip:
        tags = {t['Key']: t['Value'] for t in eip.get('Tags', [])}
        print(f"  [ORPHANED-EIP] {eip['PublicIp']} - Domain: {eip['Domain']}")

# 4. DynamoDB Tables (check if in Terraform)
print("\n4. DynamoDB Tables")
print("-" * 100)
code, out, err = run_cmd("aws dynamodb list-tables --region {region} --output json")
tables = json.loads(out).get('TableNames', [])
managed_tables = [
    "algo-terraform-locks-dev",  # This IS managed (Terraform bootstrap)
    "algo-watermarks-dev",  # Check if this is in Terraform
    "algo-feature_flags-dev",  # Check this too
]
for table in tables:
    if table not in managed_tables:
        print(f"  [CHECK] DynamoDB: {table}")
    else:
        print(f"  [MANAGED] DynamoDB: {table}")

# 5. EventBridge Rules (non-terraform)
print("\n5. EventBridge Rules")
print("-" * 100)
code, out, err = run_cmd("aws events list-rules --region {region} --output json")
rules = json.loads(out).get('Rules', [])
managed_rules = [
    'detect-unmanaged-aws-resources',
    'daily-weight-optimization',
    'eod-bulk-refresh',
    'morning-data-preparation',
]
for rule in rules:
    if not rule['Name'].startswith('aws.'):
        if rule['Name'] not in managed_rules:
            print(f"  [UNMANAGED] EventBridge Rule: {rule['Name']}")
        else:
            print(f"  [MANAGED] EventBridge Rule: {rule['Name']}")

# 6. Check Lambda functions for orphaned ones
print("\n6. Lambda Functions")
print("-" * 100)
code, out, err = run_cmd("aws lambda list-functions --region {region} --output json")
funcs = json.loads(out).get('Functions', [])
managed_funcs = [
    'algo-algo-dev',
    'algo-api-dev',
    'algo-data-freshness-monitor-dev',
    'algo-execution-monitor-dev',
    'algo-rds-rotation-dev',
]
for func in funcs:
    if func['FunctionName'] not in managed_funcs:
        tags = func.get('Tags', {})
        print(f"  [CHECK] Lambda: {func['FunctionName']} (Tags: {tags})")
    else:
        print(f"  [MANAGED] Lambda: {func['FunctionName']}")

# 7. Step Functions (State Machines)
print("\n7. Step Functions")
print("-" * 100)
code, out, err = run_cmd("aws stepfunctions list-state-machines --region {region} --output json")
sms = json.loads(out).get('stateMachines', [])
for sm in sms:
    print(f"  [CHECK] State Machine: {sm['name']}")

# 8. SNS Topics (non-terraform)
print("\n8. SNS Topics")
print("-" * 100)
code, out, err = run_cmd("aws sns list-topics --region {region} --output json")
topics = json.loads(out).get('Topics', [])
managed_topics = ['algo-algo-alerts-dev']
for topic in topics:
    topic_name = topic['TopicArn'].split(':')[-1]
    if topic_name not in managed_topics:
        print(f"  [CHECK] SNS Topic: {topic_name}")
    else:
        print(f"  [MANAGED] SNS Topic: {topic_name}")

# Summary
print("\n" + "=" * 100)
print("ACTION ITEMS")
print("=" * 100)
print("""
1. CloudFormation Stacks: Delete old "stocks-*" stacks if not in use
   Command: aws cloudformation delete-stack --stack-name <stack-name>

2. Orphaned VPCs: Either add to Terraform or delete
   - If old "stocks-vpc" not needed: Delete the VPC and associated resources

3. Unassociated EIPs: Delete if not in use
   Command: aws ec2 release-address --public-ip <ip>

4. DynamoDB Tables: Add to Terraform or tag as external
   - algo-watermarks-dev: Check if this should be in Terraform state

5. EventBridge Rules: Add to Terraform or delete

6. Lambda Functions: Verify all are accounted for in Terraform

Once cleaned up, run: python3 scripts/audit_unmanaged_resources.py
""")
