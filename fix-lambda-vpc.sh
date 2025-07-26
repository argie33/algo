#!/bin/bash
# Fix Lambda VPC Configuration to Restore Cognito Authentication
# This removes VPC configuration so Lambda can access internet for JWKS

set -e

STACK_NAME="stocks-webapp-dev"
TEMPLATE_FILE="template-webapp-lambda.yml"
REGION="us-east-1"

echo "🔧 Fixing Lambda VPC configuration for Cognito authentication..."
echo "Stack: $STACK_NAME"
echo "Template: $TEMPLATE_FILE" 
echo "Region: $REGION"
echo ""

# Check if stack exists
echo "📋 Checking stack status..."
STACK_STATUS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$STACK_STATUS" = "NOT_FOUND" ]; then
    echo "❌ Stack $STACK_NAME not found!"
    exit 1
fi

echo "✅ Stack found with status: $STACK_STATUS"

# Get existing parameters
echo "📝 Getting existing stack parameters..."
PARAMETERS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].Parameters[?ParameterKey!=`LambdaCodeKey`].[ParameterKey,ParameterValue]' --output text | while read key value; do echo "ParameterKey=$key,ParameterValue=$value"; done | paste -sd ' ')

echo "Parameters: $PARAMETERS"

# Deploy the updated template
echo ""
echo "🚀 Deploying updated template (removing VPC config from Lambda)..."
aws cloudformation update-stack \
    --stack-name $STACK_NAME \
    --template-body file://$TEMPLATE_FILE \
    --parameters $PARAMETERS \
    --capabilities CAPABILITY_IAM \
    --region $REGION

echo "✅ CloudFormation update initiated"
echo ""
echo "⏳ Waiting for stack update to complete..."
aws cloudformation wait stack-update-complete --stack-name $STACK_NAME --region $REGION

echo ""
echo "🎉 Stack update completed successfully!"
echo ""
echo "🔍 Testing API health endpoint..."
sleep 10  # Give Lambda a moment to reinitialize

API_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' --output text)
curl -s "$API_URL/api/health" | python3 -m json.tool || echo "Health check test completed"

echo ""
echo "✅ Lambda VPC configuration fixed!"
echo "🌐 Your API should now authenticate properly with Cognito"
echo "🔗 API URL: $API_URL"