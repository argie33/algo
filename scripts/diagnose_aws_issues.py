#!/usr/bin/env python3
"""Diagnose AWS Lambda and API Gateway issues causing 503 errors and dashboard failures."""

import json
import subprocess
import sys
from datetime import datetime, timedelta


def run_command(cmd, description):
    """Run AWS CLI command and return output."""
    print(f"\n[*] {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(f"  ✗ FAILED: {result.stderr[:200]}")
            return None
        print("  ✓ OK")
        return result.stdout.strip()
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return None

def check_lambda_vpc_config():
    """Check if Lambda has proper VPC configuration."""
    print("\n=== LAMBDA VPC CONFIGURATION ===")

    cmd = "aws lambda get-function-configuration --function-name algo-api-dev --region us-east-1 --query 'VpcConfig'"
    output = run_command(cmd, "Checking API Lambda VPC config")
    if output:
        try:
            config = json.loads(output)
            if config.get("SubnetIds"):
                print(f"  Subnets: {config['SubnetIds']}")
                print(f"  Security Groups: {config['SecurityGroupIds']}")
            else:
                print("  ⚠ WARNING: No VPC configuration found - Lambda cannot reach RDS!")
                return False
        except json.JSONDecodeError:
            print(f"  ✗ Could not parse VPC config: {output[:100]}")
            return False
    return True

def check_provisioned_concurrency():
    """Check if provisioned concurrency is enabled."""
    print("\n=== PROVISIONED CONCURRENCY ===")

    cmd = "aws lambda get-provisioned-concurrency-config --function-name algo-api-dev --region us-east-1 --qualifier LIVE"
    output = run_command(cmd, "Checking provisioned concurrency")
    if output:
        try:
            config = json.loads(output)
            allocated = config.get("AllocatedConcurrentExecutions", 0)
            available = config.get("AvailableConcurrentExecutions", 0)
            print(f"  Allocated: {allocated}")
            print(f"  Available: {available}")
            if allocated == 0:
                print("  ⚠ WARNING: No provisioned concurrency - cold starts may cause 503 errors!")
                return False
        except json.JSONDecodeError:
            print("  ⚠ Could not parse response (may mean no provisioned concurrency)")
            return False
    return True

def check_lambda_errors():
    """Check Lambda CloudWatch logs for errors."""
    print("\n=== LAMBDA ERROR LOGS (Last 10 min) ===")

    # Get logs from the last 10 minutes
    start_time = int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)

    cmd = f"""aws logs filter-log-events \\
        --log-group-name /aws/lambda/algo-api-dev \\
        --start-time {start_time} \\
        --region us-east-1 \\
        --query 'events[?contains(message, `ERROR`) || contains(message, `Exception`) || contains(message, `503`)]' \\
        --max-items 5"""

    output = run_command(cmd, "Checking Lambda error logs")
    if output and output != "[]":
        try:
            events = json.loads(output)
            for event in events:
                msg = event.get("message", "")
                print(f"  {msg[:150]}")
        except json.JSONDecodeError:
            pass

def check_api_gateway_errors():
    """Check API Gateway logs for 503 errors."""
    print("\n=== API GATEWAY 5XX ERRORS (Last hour) ===")

    start_time = int((datetime.now() - timedelta(hours=1)).timestamp() * 1000)

    cmd = f"""aws logs filter-log-events \\
        --log-group-name /aws/apigateway/algo-api-dev \\
        --start-time {start_time} \\
        --region us-east-1 \\
        --filter-pattern '[... status_code = 5* ...]' \\
        --query 'events[].message' \\
        --max-items 10"""

    output = run_command(cmd, "Checking API Gateway 5XX errors")
    if output and output != "[]":
        try:
            messages = json.loads(output)
            print(f"  Found {len(messages)} 5XX errors:")
            for msg in messages[:5]:
                print(f"    {msg[:100]}")
        except json.JSONDecodeError:
            pass

def check_database_connectivity():
    """Check if Lambda can reach RDS database."""
    print("\n=== DATABASE CONNECTIVITY ===")

    # Query Lambda logs to see if there are connection errors
    cmd = """aws logs filter-log-events \\
        --log-group-name /aws/lambda/algo-api-dev \\
        --filter-pattern '[... "connect" AND "refused" ...]' \\
        --region us-east-1 \\
        --query 'events[0].message' \\
        --max-items 1"""

    output = run_command(cmd, "Checking for database connection errors")
    if output and output != "null":
        print(f"  ✗ Found connection error: {output[:200]}")
        return False
    print("  ✓ No connection errors detected")
    return True

def check_reserved_concurrency():
    """Check Lambda reserved concurrency."""
    print("\n=== RESERVED CONCURRENCY ===")

    cmd = "aws lambda get-function-concurrency --function-name algo-api-dev --region us-east-1"
    output = run_command(cmd, "Checking reserved concurrency")
    if output:
        try:
            config = json.loads(output)
            reserved = config.get("ReservedConcurrentExecutions", "Not set")
            print(f"  Reserved: {reserved}")
        except json.JSONDecodeError:
            pass

def check_lambda_code_size():
    """Check Lambda code size."""
    print("\n=== LAMBDA CODE SIZE ===")

    cmd = "aws lambda get-function --function-name algo-api-dev --region us-east-1 --query 'Configuration.CodeSize'"
    output = run_command(cmd, "Checking code size")
    if output:
        try:
            size_bytes = int(output)
            size_mb = size_bytes / (1024 * 1024)
            print(f"  Size: {size_mb:.1f} MB")
            if size_mb > 250:
                print("  ⚠ WARNING: Code size > 250 MB may affect performance")
        except ValueError:
            print(f"  Could not parse size: {output}")

def main():
    """Run all diagnostics."""
    print("=" * 60)
    print("AWS LAMBDA & API GATEWAY DIAGNOSTICS")
    print("=" * 60)

    # Check AWS credentials
    cmd = "aws sts get-caller-identity --region us-east-1"
    output = run_command(cmd, "Checking AWS credentials")
    if not output:
        print("\n✗ FAILED: AWS credentials not configured")
        print("  Set AWS credentials via: aws configure or environment variables")
        sys.exit(1)

    try:
        identity = json.loads(output)
        print(f"  Account: {identity['Account']}")
        print(f"  User: {identity['Arn']}")
    except json.JSONDecodeError:
        pass

    # Run all checks
    vpc_ok = check_lambda_vpc_config()
    pc_ok = check_provisioned_concurrency()
    check_lambda_errors()
    check_api_gateway_errors()
    db_ok = check_database_connectivity()
    check_reserved_concurrency()
    check_lambda_code_size()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if not vpc_ok:
        print("✗ VPC Configuration Issue")
        print("  FIX: Run: bash scripts/fix-lambda-vpc.sh")

    if not pc_ok:
        print("✗ Provisioned Concurrency Not Configured")
        print("  FIX: Run: terraform apply -var api_lambda_provisioned_concurrency=5")

    if not db_ok:
        print("✗ Database Connectivity Issue")
        print("  FIX: Check Lambda VPC configuration and security groups")

    if vpc_ok and pc_ok and db_ok:
        print("✓ All checks passed!")
        print("\nIf 503 errors persist, check:")
        print("  1. Lambda code errors: aws logs tail /aws/lambda/algo-api-dev --follow")
        print("  2. Lambda timeout: increase timeout in terraform/variables.tf")
        print("  3. Cold start: ensure provisioned concurrency is allocated")

if __name__ == "__main__":
    main()
