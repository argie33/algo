#!/bin/bash

echo "🔍 Debugging Lambda Configuration"
echo "=================================="

# Check if Lambda exists
echo "📋 Checking Lambda function status..."
aws lambda get-function \
  --function-name financial-dashboard-api-dev \
  --query 'Configuration.{FunctionName:FunctionName,LastModified:LastModified,State:State,Version:Version}' \
  --output table 2>/dev/null || echo "❌ Lambda function not found"

echo ""
echo "📋 Lambda Environment Variables:"
aws lambda get-function-configuration \
  --function-name financial-dashboard-api-dev \
  --query 'Environment.Variables' \
  --output json 2>/dev/null || echo "❌ Could not get Lambda environment variables"

echo ""
echo "📋 Testing configuration endpoint:"
curl -s "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/config" | jq . 2>/dev/null || echo "❌ New config endpoint not available"

echo ""
echo "📋 Testing old CloudFormation endpoint:"
curl -s "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/config/cloudformation?stackName=stocks-webapp-dev" | jq . 2>/dev/null || echo "❌ Old CloudFormation endpoint not available"

echo ""
echo "📋 Testing health endpoint:"
curl -s "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/health" | jq . 2>/dev/null || echo "❌ Health endpoint not available"