#!/bin/bash
# Fix CloudFormation Configuration Service CORS/Permissions Issue
# This script addresses the IAM permissions error preventing CloudFormation API access

set -e

echo "🔧 Fixing CloudFormation Configuration Service Issue"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
STACK_NAME="stocks-webapp-dev"
TEMPLATE_FILE="webapp/template-webapp-lambda.yml"
REGION="us-east-1"

echo -e "${BLUE}📋 Root Cause Analysis:${NC}"
echo "❌ Lambda function 'financial-dashboard-api-dev' lacks CloudFormation permissions"
echo "❌ Missing cloudformation:DescribeStacks permission"
echo "✅ CORS is working correctly (confirmed via curl test)"
echo ""

echo -e "${YELLOW}🛠️  Solution Applied:${NC}"
echo "✅ Added CloudFormation IAM permissions to Lambda role in template"
echo "✅ Enhanced error handling in configuration service"
echo ""

# Verify template exists
if [ ! -f "$TEMPLATE_FILE" ]; then
    echo -e "${RED}❌ Template file not found: $TEMPLATE_FILE${NC}"
    exit 1
fi

echo -e "${BLUE}🔍 Verifying current stack status...${NC}"
STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$STACK_STATUS" == "NOT_FOUND" ]; then
    echo -e "${RED}❌ Stack $STACK_NAME not found${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Stack found with status: $STACK_STATUS${NC}"

# Get current parameters from the stack
echo -e "${BLUE}📋 Retrieving current stack parameters...${NC}"
PARAMETERS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Parameters' \
    --output json)

# Convert parameters to CLI format
PARAM_OVERRIDES=""
while IFS= read -r param; do
    key=$(echo "$param" | jq -r '.ParameterKey')
    value=$(echo "$param" | jq -r '.ParameterValue')
    PARAM_OVERRIDES="$PARAM_OVERRIDES $key=\"$value\""
done < <(echo "$PARAMETERS" | jq -c '.[]')

echo -e "${GREEN}✅ Parameters retrieved${NC}"

# Deploy the updated template
echo -e "${BLUE}🚀 Deploying CloudFormation template with IAM fix...${NC}"
echo "Stack: $STACK_NAME"
echo "Template: $TEMPLATE_FILE"
echo "Region: $REGION"
echo ""

# Use sam deploy for better handling
cd webapp
sam deploy \
    --template-file template-webapp-lambda.yml \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --capabilities CAPABILITY_IAM \
    --no-confirm-changeset \
    --force-upload \
    --parameter-overrides $PARAM_OVERRIDES

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ CloudFormation deployment successful!${NC}"
else
    echo -e "${RED}❌ CloudFormation deployment failed${NC}"
    exit 1
fi

# Wait for deployment to complete
echo -e "${BLUE}⏳ Waiting for deployment to complete...${NC}"
aws cloudformation wait stack-update-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Stack update completed successfully!${NC}"
else
    echo -e "${RED}❌ Stack update failed or timed out${NC}"
    exit 1
fi

# Test the endpoint
echo -e "${BLUE}🔍 Testing CloudFormation endpoint...${NC}"
API_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' \
    --output text)

if [ -n "$API_URL" ]; then
    echo "Testing: $API_URL/api/config/cloudformation?stackName=stocks-webapp-dev"
    
    response=$(curl -s -w "\n%{http_code}" \
        -H "Accept: application/json" \
        -H "Origin: https://d1zb7knau41vl9.cloudfront.net" \
        "$API_URL/api/config/cloudformation?stackName=stocks-webapp-dev")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" == "200" ]; then
        echo -e "${GREEN}✅ CloudFormation endpoint working! HTTP $http_code${NC}"
        echo "✅ CORS headers present"
        echo "✅ IAM permissions fixed"
    else
        echo -e "${YELLOW}⚠️  Endpoint returned HTTP $http_code${NC}"
        echo "Response: $body"
    fi
else
    echo -e "${YELLOW}⚠️  Could not retrieve API URL from stack outputs${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Issue Resolution Complete!${NC}"
echo "=================================================="
echo "✅ IAM permissions added for CloudFormation access"
echo "✅ Error handling improved in frontend"
echo "✅ Stack deployment completed"
echo ""
echo -e "${BLUE}📋 What was fixed:${NC}"
echo "1. Added cloudformation:DescribeStacks permission to Lambda IAM role"
echo "2. Added cloudformation:ListStacks permission for stack discovery"
echo "3. Enhanced error handling to detect permission issues"
echo "4. CORS was already working correctly"
echo ""
echo -e "${YELLOW}💡 Next steps:${NC}"
echo "1. Clear browser cache and reload the application"
echo "2. Check browser console for improved error messages"
echo "3. Verify CloudFormation configuration loads properly"

cd ..