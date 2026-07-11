#!/bin/bash
# Session 60: Deploy Critical Fixes to AWS
# This script deploys all fixes needed to get the system fully operational

set -e  # Exit on any error

echo "=========================================="
echo "Session 60: AWS Deployment Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Validate environment
echo -e "${YELLOW}Step 1: Validating AWS environment...${NC}"
if ! command -v aws &> /dev/null; then
    echo -e "${RED}ERROR: AWS CLI not found. Install with: pip install awscli${NC}"
    exit 1
fi

if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo -e "${RED}ERROR: AWS credentials not configured. Run: aws configure${NC}"
    exit 1
fi

AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${AWS_REGION:-us-east-1}
echo -e "${GREEN}✓ AWS CLI configured (Account: $AWS_ACCOUNT, Region: $AWS_REGION)${NC}"
echo ""

# Step 2: Deploy Terraform changes
echo -e "${YELLOW}Step 2: Deploying Terraform changes (provisioned concurrency)...${NC}"
cd terraform

# Initialize modules if needed
if [ ! -d ".terraform" ]; then
    echo "Initializing Terraform modules..."
    terraform init -upgrade
fi

# Validate configuration
echo "Validating Terraform configuration..."
terraform validate

# Plan changes
echo "Planning Terraform deployment..."
terraform plan -out=tfplan

# Apply changes
echo "Applying Terraform changes..."
terraform apply tfplan

echo -e "${GREEN}✓ Terraform deployment complete${NC}"
cd ..
echo ""

# Step 3: Enable EventBridge Scheduler
echo -e "${YELLOW}Step 3: Verifying EventBridge Scheduler is ENABLED...${NC}"

SCHEDULER_STATUS=$(aws scheduler get-schedule \
  --name algo-orchestrator-2x-daily-dev \
  --region $AWS_REGION \
  --query 'State' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$SCHEDULER_STATUS" = "ENABLED" ]; then
    echo -e "${GREEN}✓ EventBridge Scheduler is ENABLED${NC}"
elif [ "$SCHEDULER_STATUS" = "DISABLED" ]; then
    echo -e "${YELLOW}Enabling EventBridge Scheduler...${NC}"
    aws scheduler update-schedule \
      --name algo-orchestrator-2x-daily-dev \
      --state ENABLED \
      --region $AWS_REGION
    echo -e "${GREEN}✓ EventBridge Scheduler enabled${NC}"
else
    echo -e "${RED}WARNING: Could not find scheduler rule${NC}"
fi
echo ""

# Step 4: Verify Lambda configuration
echo -e "${YELLOW}Step 4: Verifying API Lambda configuration...${NC}"

echo "Checking Lambda VPC configuration..."
VPC_CONFIG=$(aws lambda get-function-configuration \
  --function-name algo-api-dev \
  --region $AWS_REGION \
  --query 'VpcConfig' 2>/dev/null | head -5)

if echo "$VPC_CONFIG" | grep -q "SubnetIds"; then
    echo -e "${GREEN}✓ Lambda has VPC configuration${NC}"
else
    echo -e "${RED}WARNING: Lambda may not have VPC configuration${NC}"
fi

echo "Checking provisioned concurrency..."
PC_CONFIG=$(aws lambda list-provisioned-concurrency-configs \
  --function-name algo-api-dev \
  --region $AWS_REGION \
  --query 'ProvisionedConcurrencyConfigs[0].ProvisionedConcurrentExecutions' \
  --output text 2>/dev/null || echo "0")

if [ "$PC_CONFIG" -gt 0 ]; then
    echo -e "${GREEN}✓ Provisioned Concurrency: $PC_CONFIG units${NC}"
else
    echo -e "${YELLOW}Note: Provisioned concurrency not yet active (takes 5-10 min after deployment)${NC}"
fi
echo ""

# Step 5: Test API connectivity
echo -e "${YELLOW}Step 5: Testing API connectivity...${NC}"

API_ENDPOINT=$(aws apigatewayv2 get-apis \
  --query "Items[?Name=='algo-api-dev'].ApiEndpoint" \
  --region $AWS_REGION \
  --output text 2>/dev/null || echo "")

if [ -z "$API_ENDPOINT" ]; then
    echo -e "${RED}ERROR: Could not find API Gateway endpoint${NC}"
else
    echo "Testing API endpoint: $API_ENDPOINT"

    # Try to get portfolio (requires valid Cognito token in prod, but should return something)
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
      -H "Authorization: Bearer dev-admin" \
      "$API_ENDPOINT/api/health" || echo "000")

    if [ "$HTTP_STATUS" = "200" ]; then
        echo -e "${GREEN}✓ API is responding (HTTP 200)${NC}"
    elif [ "$HTTP_STATUS" = "403" ] || [ "$HTTP_STATUS" = "401" ]; then
        echo -e "${YELLOW}✓ API is responding (HTTP $HTTP_STATUS - auth required, this is expected)${NC}"
    else
        echo -e "${RED}WARNING: API returned HTTP $HTTP_STATUS${NC}"
    fi
fi
echo ""

# Step 6: Check recent Lambda invocations
echo -e "${YELLOW}Step 6: Checking Lambda invocation history...${NC}"

INVOCATIONS=$(aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=algo-orchestrator-dev \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum \
  --region $AWS_REGION \
  --query 'Datapoints[0].Sum' \
  --output text 2>/dev/null || echo "0")

if [ "$INVOCATIONS" != "None" ] && [ "$INVOCATIONS" != "0" ]; then
    echo -e "${GREEN}✓ Orchestrator Lambda invoked $INVOCATIONS times in last 24 hours${NC}"
else
    echo -e "${YELLOW}Note: Orchestrator may not have run yet today (runs at 9:30 AM and 5:30 PM ET)${NC}"
fi
echo ""

# Step 7: Check CloudWatch logs for errors
echo -e "${YELLOW}Step 7: Checking CloudWatch logs for errors...${NC}"

RECENT_ERRORS=$(aws logs tail /aws/lambda/algo-api-dev \
  --since 1h \
  --format short 2>/dev/null | grep -i "error\|timeout\|refused" | wc -l || echo "0")

if [ "$RECENT_ERRORS" -gt 0 ]; then
    echo -e "${RED}WARNING: Found $RECENT_ERRORS error messages in Lambda logs (last hour)${NC}"
    echo "View logs with: aws logs tail /aws/lambda/algo-api-dev --since 1h"
else
    echo -e "${GREEN}✓ No errors in Lambda logs (last hour)${NC}"
fi
echo ""

# Step 8: Summary
echo "=========================================="
echo -e "${GREEN}DEPLOYMENT COMPLETE${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Wait 5-10 minutes for Lambda provisioned concurrency to activate"
echo "2. Test dashboard in AWS mode (without --local flag)"
echo "3. Verify orchestrator runs at scheduled times (9:30 AM, 5:30 PM ET)"
echo "4. Check dashboard panels for data display"
echo ""
echo "If dashboard still shows 'data not available':"
echo "  • Check CloudWatch logs: aws logs tail /aws/lambda/algo-api-dev --follow"
echo "  • Verify RDS security group allows Lambda: aws ec2 describe-security-groups --group-ids sg-xxx"
echo "  • Check data freshness: SELECT MAX(date) FROM price_daily (should be today's date)"
echo ""
echo "Rollback Terraform changes if needed:"
echo "  cd terraform && terraform destroy"
echo ""
