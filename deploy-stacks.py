#!/usr/bin/env python3
"""
CloudFormation Stack Deployment Script
Deploys all 3 stacks in the correct order with proper parameters
"""

import boto3
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

# Configuration
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
DB_USER = os.environ.get('DB_USER', 'stocks')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'bed0elAn')
FRED_API_KEY = os.environ.get('FRED_API_KEY', '')

print(f"AWS Region: {AWS_REGION}")
print(f"DB User: {DB_USER}")
print(f"FRED API Key: {'*' * 10 if FRED_API_KEY else 'NOT SET'}")
print()

# Initialize CloudFormation client
cf = boto3.client(
    'cloudformation',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

def print_header(title):
    print("\n" + "="*70)
    print(title)
    print("="*70 + "\n")

def deploy_stack(template_file, stack_name, parameters=None, wait=True):
    """Deploy a CloudFormation stack"""
    print(f"Deploying stack: {stack_name}")
    print(f"Template: {template_file}")

    # Read template
    try:
        with open(template_file) as f:
            template_body = f.read()
    except FileNotFoundError:
        print(f"ERROR: Template file not found: {template_file}")
        return False

    # Build parameters list
    cf_params = []
    if parameters:
        for key, value in parameters.items():
            cf_params.append({
                'ParameterKey': key,
                'ParameterValue': str(value)
            })

    try:
        # Check if stack already exists
        try:
            existing = cf.describe_stacks(StackName=stack_name)
            print(f"  Stack {stack_name} already exists")
            status = existing['Stacks'][0]['StackStatus']
            print(f"  Current status: {status}")
            if status in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']:
                print(f"  Stack is ready, skipping deployment")
                return True
        except cf.exceptions.ClientError:
            pass

        # Create stack
        response = cf.create_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Parameters=cf_params,
            Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']
        )

        stack_id = response['StackId']
        print(f"  Stack creation initiated: {stack_id}")

        if wait:
            print(f"  Waiting for stack to complete...")
            waiter = cf.get_waiter('stack_create_complete')
            waiter.wait(StackName=stack_name)
            print(f"  [OK] Stack {stack_name} created successfully")
            return True
        else:
            print(f"  Stack creation in progress (not waiting)")
            return True

    except cf.exceptions.ClientError as e:
        error_msg = str(e)
        if 'already exists' in error_msg:
            print(f"  Stack {stack_name} already exists")
            return True
        elif 'CREATE_COMPLETE' in error_msg:
            print(f"  Stack {stack_name} already created")
            return True
        else:
            print(f"  ERROR: {error_msg}")
            return False
    except Exception as e:
        print(f"  ERROR: Unexpected error - {e}")
        return False

def main():
    print_header("AWS CloudFormation Stack Deployment")
    print("This will deploy 3 stacks in order:")
    print("  1. stocks-core (VPC, subnets, security groups)")
    print("  2. stocks-app (RDS database)")
    print("  3. stocks-app-ecs-tasks (ECS task definitions)")
    print()

    # Step 1: Deploy Core Stack
    print_header("STEP 1: Deploy Core Infrastructure")
    core_success = deploy_stack(
        'template-core.yml',
        'stocks-core',
        parameters={
            'VpcCidr': '10.0.0.0/16',
            'PublicSubnetCidr1': '10.0.1.0/24',
            'PublicSubnetCidr2': '10.0.2.0/24',
            'PrivateSubnetCidr1': '10.0.101.0/24',
            'PrivateSubnetCidr2': '10.0.102.0/24',
        },
        wait=True
    )

    if not core_success:
        print("ERROR: Core stack deployment failed")
        return False

    # Step 2: Deploy App Stack
    print_header("STEP 2: Deploy Application Stack (RDS)")
    app_success = deploy_stack(
        'template-app-stocks.yml',
        'stocks-app',
        parameters={
            'RDSUsername': DB_USER,
            'RDSPassword': DB_PASSWORD,
            'FREDApiKey': FRED_API_KEY or 'placeholder',
        },
        wait=True
    )

    if not app_success:
        print("ERROR: App stack deployment failed")
        return False

    # Step 3: Deploy ECS Tasks Stack
    print_header("STEP 3: Deploy ECS Task Definitions")
    ecs_success = deploy_stack(
        'template-app-ecs-tasks.yml',
        'stocks-app-ecs-tasks',
        parameters={
            'QuarterlyIncomeImageTag': 'latest',
            'AnnualIncomeImageTag': 'latest',
            'QuarterlyBalanceImageTag': 'latest',
            'AnnualBalanceImageTag': 'latest',
            'QuarterlyCashflowImageTag': 'latest',
            'AnnualCashflowImageTag': 'latest',
            'RDSUsername': DB_USER,
            'RDSPassword': DB_PASSWORD,
        },
        wait=True
    )

    if not ecs_success:
        print("ERROR: ECS stack deployment failed")
        return False

    # Summary
    print_header("DEPLOYMENT SUMMARY")
    print("[OK] All stacks deployed successfully!")
    print()
    print("Next steps:")
    print("  1. Configure RDS security group for ECS access")
    print("  2. Rebuild and push Docker images to ECR")
    print("  3. Run Batch 5 loaders: python3 aws-deploy.py run-loader")
    print()

    return True

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
