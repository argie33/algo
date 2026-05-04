#!/bin/bash
echo "=========================================="
echo "CHECKING ACTUAL DEPLOYMENT STATUS"
echo "=========================================="
echo ""

# Check if AWS credentials are available
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "❌ AWS_ACCOUNT_ID not set"
    echo "   Cannot verify AWS resources"
else
    echo "✅ AWS_ACCOUNT_ID available: $AWS_ACCOUNT_ID"
fi

echo ""
echo "=========================================="
echo "CHECKING CLOUDFORMATION STACKS"
echo "=========================================="
echo ""

# Try to list CloudFormation stacks
echo "Attempting to list CloudFormation stacks..."
if command -v aws &> /dev/null; then
    echo "AWS CLI is available"
    echo ""
    echo "Try: aws cloudformation list-stacks --region us-east-1 --query 'StackSummaries[].StackName'"
else
    echo "❌ AWS CLI not available - cannot verify CloudFormation stacks"
fi

echo ""
echo "=========================================="
echo "WHAT WE NEED TO VERIFY"
echo "=========================================="
echo ""
echo "Required CloudFormation Stacks:"
echo "  1. stocks-oidc-bootstrap"
echo "  2. stocks-core-vpc (or similar)"
echo "  3. stocks-app-stack"
echo "  4. stocks-app-ecs-tasks"
echo "  5. stocks-webapp-dev"
echo "  6. stocks-algo-orchestrator"
echo ""
echo "Required AWS Resources:"
echo "  ✓ Lambda functions: algo-orchestrator, <webapp-function>"
echo "  ✓ EventBridge rule: algo-eod-orchestrator (ENABLED)"
echo "  ✓ RDS instance: stocks (status available)"
echo "  ✓ ECS cluster: stocks-cluster"
echo "  ✓ Secrets Manager secrets: stocks-db-credentials, alpaca-api-key"
echo ""
echo "Required GitHub Workflows:"
echo "  ✓ Latest runs should show deployments"
echo "  ✓ No errors in workflow logs"
echo "  ✓ CloudFormation operations succeeded"
