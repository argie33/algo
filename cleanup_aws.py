#!/usr/bin/env python3
"""
AWS Cleanup Script - Remove Orphaned Resources
Stock Analytics Platform
"""

import boto3
import sys
import time
from botocore.exceptions import ClientError

# Fix for Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REGION = "us-east-1"

cf_client = boto3.client('cloudformation', region_name=REGION)
ec2_client = boto3.client('ec2', region_name=REGION)
ecr_client = boto3.client('ecr', region_name=REGION)
sts_client = boto3.client('sts', region_name=REGION)

def get_account_id():
    try:
        return sts_client.get_caller_identity()['Account']
    except Exception as e:
        print(f"[ERROR] Could not get account ID: {e}")
        sys.exit(1)

def list_current_state():
    print("\n" + "="*60)
    print("[PHASE 1] Current AWS State")
    print("="*60)

    account_id = get_account_id()
    print(f"[OK] Connected to AWS Account: {account_id}")
    print(f"     Region: {REGION}\n")

    print("CloudFormation Stacks with 'stocks':")
    try:
        response = cf_client.list_stacks(
            StackStatusFilter=['CREATE_IN_PROGRESS', 'CREATE_COMPLETE', 'CREATE_FAILED',
                              'ROLLBACK_IN_PROGRESS', 'ROLLBACK_COMPLETE', 'DELETE_IN_PROGRESS',
                              'UPDATE_IN_PROGRESS', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_IN_PROGRESS',
                              'UPDATE_ROLLBACK_COMPLETE', 'REVIEW_IN_PROGRESS']
        )
        stocks_stacks = [s for s in response['StackSummaries'] if 'stocks' in s['StackName']]
        if stocks_stacks:
            for stack in stocks_stacks:
                print(f"  * {stack['StackName']:<40} {stack['StackStatus']}")
        else:
            print("  (None found)")
    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\nVPCs with CIDR 10.0.0.0/16:")
    try:
        response = ec2_client.describe_vpcs(
            Filters=[{'Name': 'cidr', 'Values': ['10.0.0.0/16']}]
        )
        if response['Vpcs']:
            for vpc in response['Vpcs']:
                print(f"  * {vpc['VpcId']:<20} {vpc['State']}")
        else:
            print("  (None found)")
    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\nS3 Buckets with 'stocks' or 'algo':")
    try:
        s3_client = boto3.client('s3')
        response = s3_client.list_buckets()
        stocks_buckets = [b['Name'] for b in response['Buckets'] if 'stocks' in b['Name'] or 'algo' in b['Name']]
        if stocks_buckets:
            for bucket in stocks_buckets:
                print(f"  * {bucket}")
        else:
            print("  (None found)")
    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\nECR Repositories with 'stocks':")
    try:
        response = ecr_client.describe_repositories()
        stocks_repos = [r['repositoryName'] for r in response['repositories'] if 'stocks' in r['repositoryName']]
        if stocks_repos:
            for repo in stocks_repos:
                print(f"  * {repo}")
        else:
            print("  (None found)")
    except Exception as e:
        print(f"  [ERROR] {e}")

def delete_stacks():
    print("\n" + "="*60)
    print("[PHASE 2] Delete CloudFormation Stacks")
    print("="*60 + "\n")

    stacks_to_delete = [
        'stocks-webapp-dev',
        'stocks-algo-dev',
        'stocks-loaders',
        'stocks-data',
        'stocks-core',
        'stocks-oidc'
    ]

    for stack_name in stacks_to_delete:
        try:
            response = cf_client.describe_stacks(StackName=stack_name)
            status = response['Stacks'][0]['StackStatus']
            print(f"Deleting: {stack_name} ({status})")
            cf_client.delete_stack(StackName=stack_name)

            print(f"  Waiting...", end=' ', flush=True)
            waiter = cf_client.get_waiter('stack_delete_complete')
            waiter.wait(StackName=stack_name, WaiterConfig={'Delay': 10, 'MaxAttempts': 60})
            print("[OK]")

        except ClientError as e:
            if 'does not exist' in str(e):
                print(f"Stack {stack_name} does not exist (skipping)")
            else:
                print(f"  [WARN] {str(e)[:60]}")
        except Exception as e:
            print(f"  [WARN] Timeout: {str(e)[:60]}")

def delete_ecr_repos():
    print("\n" + "="*60)
    print("[PHASE 3a] Delete ECR Repositories")
    print("="*60 + "\n")

    repos_to_try = ['stocks-app-registry', 'stocks-loaders-registry',
                    'stocks-webapp-registry', 'stocks-algo-registry']

    for repo_name in repos_to_try:
        try:
            ecr_client.delete_repository(repositoryName=repo_name, force=True)
            print(f"[OK] Deleted: {repo_name}")
        except ClientError as e:
            if 'RepositoryNotFoundException' in str(e):
                print(f"     {repo_name} not found (skipping)")
            else:
                print(f"     [WARN] {repo_name}: {str(e)[:50]}")

def delete_vpc_resources():
    print("\n" + "="*60)
    print("[PHASE 3b] Delete VPCs and Dependencies")
    print("="*60 + "\n")

    try:
        response = ec2_client.describe_vpcs(
            Filters=[{'Name': 'cidr', 'Values': ['10.0.0.0/16']}]
        )
        vpc_ids = [vpc['VpcId'] for vpc in response['Vpcs']]

        if not vpc_ids:
            print("No VPCs to delete")
            return

        for vpc_id in vpc_ids:
            print(f"\nVPC: {vpc_id}")

            print(f"  ENIs...", end=' ', flush=True)
            try:
                enis = ec2_client.describe_network_interfaces(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
                )
                for eni in enis['NetworkInterfaces']:
                    try:
                        ec2_client.delete_network_interface(NetworkInterfaceId=eni['NetworkInterfaceId'])
                    except:
                        pass
                print("[OK]")
            except Exception as e:
                print(f"[WARN]")

            print(f"  IGWs...", end=' ', flush=True)
            try:
                igws = ec2_client.describe_internet_gateways(
                    Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
                )
                for igw in igws['InternetGateways']:
                    ec2_client.detach_internet_gateway(InternetGatewayId=igw['InternetGatewayId'], VpcId=vpc_id)
                    ec2_client.delete_internet_gateway(InternetGatewayId=igw['InternetGatewayId'])
                print("[OK]")
            except Exception as e:
                print(f"[WARN]")

            print(f"  VPC Endpoints...", end=' ', flush=True)
            try:
                vpces = ec2_client.describe_vpc_endpoints(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
                )
                vpce_ids = [v['VpcEndpointId'] for v in vpces['VpcEndpoints']]
                if vpce_ids:
                    ec2_client.delete_vpc_endpoints(VpcEndpointIds=vpce_ids)
                print("[OK]")
            except Exception as e:
                print(f"[WARN]")

            print(f"  Security Groups...", end=' ', flush=True)
            try:
                sgs = ec2_client.describe_security_groups(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
                )
                for sg in sgs['SecurityGroups']:
                    if sg['GroupName'] != 'default':
                        try:
                            ec2_client.delete_security_group(GroupId=sg['GroupId'])
                        except:
                            pass
                print("[OK]")
            except Exception as e:
                print(f"[WARN]")

            print(f"  Route Tables...", end=' ', flush=True)
            try:
                rts = ec2_client.describe_route_tables(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
                )
                for rt in rts['RouteTables']:
                    if not any(assoc['Main'] for assoc in rt.get('Associations', [])):
                        try:
                            ec2_client.delete_route_table(RouteTableId=rt['RouteTableId'])
                        except:
                            pass
                print("[OK]")
            except Exception as e:
                print(f"[WARN]")

            print(f"  Subnets...", end=' ', flush=True)
            try:
                subnets = ec2_client.describe_subnets(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
                )
                for subnet in subnets['Subnets']:
                    try:
                        ec2_client.delete_subnet(SubnetId=subnet['SubnetId'])
                    except:
                        pass
                print("[OK]")
            except Exception as e:
                print(f"[WARN]")

            print(f"  VPC...", end=' ', flush=True)
            try:
                time.sleep(2)
                ec2_client.delete_vpc(VpcId=vpc_id)
                print("[OK]")
            except Exception as e:
                print(f"[WARN]")

    except Exception as e:
        print(f"[ERROR] {e}")

def verify_cleanup():
    print("\n" + "="*60)
    print("[PHASE 4] Verification")
    print("="*60 + "\n")

    issues = []

    try:
        response = cf_client.list_stacks(
            StackStatusFilter=['CREATE_COMPLETE', 'UPDATE_COMPLETE', 'ROLLBACK_COMPLETE',
                              'UPDATE_ROLLBACK_COMPLETE', 'REVIEW_IN_PROGRESS']
        )
        stocks_stacks = [s for s in response['StackSummaries'] if 'stocks' in s['StackName']]
        if stocks_stacks:
            print("[FAIL] Remaining CloudFormation stacks:")
            for stack in stocks_stacks:
                print(f"       {stack['StackName']:<40} {stack['StackStatus']}")
            issues.append("stacks")
        else:
            print("[OK] No remaining CloudFormation stacks")
    except Exception as e:
        print(f"[WARN] Could not verify stacks: {e}")

    try:
        response = ec2_client.describe_vpcs(
            Filters=[{'Name': 'cidr', 'Values': ['10.0.0.0/16']}]
        )
        if response['Vpcs']:
            print("\n[FAIL] Remaining VPCs with 10.0.0.0/16:")
            for vpc in response['Vpcs']:
                print(f"       {vpc['VpcId']}")
            issues.append("VPCs")
        else:
            print("[OK] No remaining VPCs with 10.0.0.0/16")
    except Exception as e:
        print(f"[WARN] Could not verify VPCs: {e}")

    print("\n" + "="*60)
    if issues:
        print(f"[INCOMPLETE] Cleanup needs manual intervention: {', '.join(issues)}")
    else:
        print("[SUCCESS] AWS account is clean and ready")
    print("="*60)

    return len(issues) == 0

def main():
    print("\n" + "="*70)
    print(" AWS CLEANUP - Stock Analytics Platform")
    print("="*70)

    try:
        list_current_state()
        delete_stacks()
        delete_ecr_repos()
        delete_vpc_resources()
        success = verify_cleanup()

        print("\n" + "="*70)
        print("NEXT STEPS:")
        print("="*70)
        print("1. [OK] Cleanup complete")
        print("2. [PAUSE] User will revoke AWS admin access")
        print("3. [CONTINUE] Terraform migration after access removed")
        print("="*70 + "\n")

        return 0 if success else 1

    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
