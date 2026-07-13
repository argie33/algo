#!/usr/bin/env python3
"""Fix Lambda VPC configuration to prevent 503 errors in AWS.

Lambda needs VPC config to access RDS database. Without it, all database calls fail with 503.
This script configures the API Lambda with proper VPC settings.
"""

import json
import os
import subprocess
import sys


def run_command(cmd: list, description: str) -> dict | str | None:
    """Run AWS CLI command and return parsed output."""
    print(f"\n{description}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  ERROR: {result.stderr[:200]}")
            return None
        output = result.stdout.strip()
        if output.startswith('{'):
            return json.loads(output)
        return output
    except subprocess.TimeoutExpired:
        print("  ERROR: Command timed out")
        return None
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        return None

def main():
    print("=" * 70)
    print("FIXING LAMBDA VPC CONFIGURATION FOR AWS API ACCESS")
    print("=" * 70)

    function_name = "algo-api-dev"
    region = "us-east-1"

    # Step 1: Get current Lambda configuration
    print("\n1. Checking current Lambda configuration...")
    config = run_command(
        ["aws", "lambda", "get-function-configuration",
         "--function-name", function_name,
         "--region", region,
         "--output", "json"],
        f"Fetching {function_name} configuration"
    )

    if not config:
        print("\nERROR: Could not fetch Lambda configuration")
        print("Make sure AWS credentials are configured and the function exists")
        return 1

    current_vpc = config.get("VpcConfig", {})
    if current_vpc.get("SubnetIds"):
        print(f"  [OK] Lambda already has VPC config: {len(current_vpc['SubnetIds'])} subnets")
        return 0

    print("  [ISSUE] Lambda has NO VPC configuration - cannot access RDS database")

    # Step 2: Get VPC and subnet information from environment
    print("\n2. Detecting VPC and subnet configuration...")

    # Try to get from environment variables or AWS
    env_subnets = os.environ.get("LAMBDA_SUBNET_IDS", "").split(",")
    env_sg = os.environ.get("LAMBDA_SECURITY_GROUP_ID", "")

    if env_subnets and env_subnets[0]:
        subnets = env_subnets
        sg_id = env_sg
        print("  [OK] Using environment variables:")
        print(f"       Subnets: {subnets}")
        print(f"       Security group: {sg_id}")
    else:
        # Alternative: Query VPC from Terraform state or use default
        print("  [INFO] Environment variables not set (LAMBDA_SUBNET_IDS, LAMBDA_SECURITY_GROUP_ID)")
        print("  [INFO] To configure, set environment variables and re-run")
        print("\n  Typical configuration:")
        print("    export LAMBDA_SUBNET_IDS='subnet-xxx,subnet-yyy'")
        print("    export LAMBDA_SECURITY_GROUP_ID='sg-zzz'")
        return 1

    # Step 3: Update Lambda with VPC configuration
    print("\n3. Updating Lambda VPC configuration...")

    update_result = run_command(
        ["aws", "lambda", "update-function-configuration",
         "--function-name", function_name,
         "--region", region,
         "--vpc-config", json.dumps({
             "SubnetIds": subnets,
             "SecurityGroupIds": [sg_id]
         }),
         "--output", "json"],
        f"Configuring {function_name} with VPC"
    )

    if not update_result:
        print("\nERROR: Failed to update Lambda VPC configuration")
        return 1

    print("  [OK] Lambda VPC configuration updated")

    # Step 4: Wait for update to complete
    print("\n4. Waiting for Lambda to update...")
    wait_result = run_command(
        ["aws", "lambda", "wait", "function-updated",
         "--function-name", function_name,
         "--region", region],
        "Waiting for Lambda configuration to apply"
    )

    print("  [OK] Lambda update complete")

    # Step 5: Verify configuration
    print("\n5. Verifying Lambda VPC configuration...")
    verify = run_command(
        ["aws", "lambda", "get-function-configuration",
         "--function-name", function_name,
         "--region", region,
         "--output", "json"],
        "Fetching updated configuration"
    )

    if verify and verify.get("VpcConfig", {}).get("SubnetIds"):
        print("  [OK] Lambda VPC configuration verified!")
        print(f"       Subnets: {verify['VpcConfig']['SubnetIds']}")
        print(f"       Security groups: {verify['VpcConfig'].get('SecurityGroupIds', [])}")
        return 0
    else:
        print("  [ERROR] Lambda VPC configuration not applied")
        return 1

if __name__ == "__main__":
    sys.exit(main())
