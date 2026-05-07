#!/usr/bin/env python3
"""Monitor CloudFormation deployment and run health checks."""

import subprocess
import json
import time
from datetime import datetime

def run_cmd(cmd):
    """Run command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception as e:
        return f"ERROR: {e}"

def check_stack_status(stack_name):
    """Check CloudFormation stack status."""
    cmd = f"aws cloudformation describe-stacks --stack-name {stack_name} --region us-east-1 2>/dev/null | grep StackStatus"
    output = run_cmd(cmd)
    return output.strip() if output else "NOT_FOUND"

def check_rds_connectivity():
    """Check if RDS is accessible."""
    cmd = "aws rds describe-db-instances --query 'DBInstances[*].DBInstanceIdentifier' --region us-east-1"
    output = run_cmd(cmd)
    return "stocks" in output

def check_lambda_exists():
    """Check if Lambda functions exist."""
    cmd = "aws lambda list-functions --region us-east-1 --query 'Functions[*].FunctionName' 2>/dev/null"
    output = run_cmd(cmd)
    has_webapp = "stocks-webapp-api" in output
    has_algo = "algo-orchestrator" in output
    return has_webapp, has_algo

def main():
    print("=" * 70)
    print("DEPLOYMENT HEALTH CHECK")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 70)
    print()
    
    # Check stacks
    print("1. CloudFormation Stacks:")
    stacks = ["stocks-core", "stocks-data", "stocks-webapp-dev", "stocks-algo-dev"]
    for stack in stacks:
        status = check_stack_status(stack)
        status_str = "COMPLETE" if "COMPLETE" in status else status
        symbol = "[OK]" if "COMPLETE" in status else "[WAIT]"
        print(f"  {symbol} {stack}: {status_str}")
    print()
    
    # Check RDS
    print("2. Database:")
    rds_ok = check_rds_connectivity()
    print(f"  {'[OK]' if rds_ok else '[FAIL]'} RDS 'stocks' instance: {'Found' if rds_ok else 'Not found'}")
    print()
    
    # Check Lambdas
    print("3. Lambda Functions:")
    webapp_ok, algo_ok = check_lambda_exists()
    print(f"  {'[OK]' if webapp_ok else '[FAIL]'} Webapp Lambda: {'Found' if webapp_ok else 'Not found'}")
    print(f"  {'[OK]' if algo_ok else '[FAIL]'} Algo Lambda: {'Found' if algo_ok else 'Not found'}")
    print()
    
    # Summary
    print("=" * 70)
    all_ok = rds_ok and webapp_ok and algo_ok
    if all_ok:
        print("✓ DEPLOYMENT SUCCESSFUL - Ready for testing")
        print()
        print("Next steps:")
        print("  1. Test Bastion -> RDS: aws ssm start-session --target <instance-id>")
        print("  2. Trigger orchestrator: gh workflow run invoke-algo-orchestrator.yml")
        print("  3. Check logs: aws logs tail /aws/lambda/algo-orchestrator --follow")
    else:
        print("✗ DEPLOYMENT IN PROGRESS OR FAILED")
        print("  Stacks may still be deploying. Wait 5-10 minutes and retry.")
        print("  Or check AWS Console for errors.")
    print("=" * 70)

if __name__ == "__main__":
    main()
