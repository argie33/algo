#!/bin/bash

echo "🚀 Force Deployment Script"
echo "=========================="

# Get the stack name and CloudFront distribution ID
STACK_NAME="stocks-webapp-dev"
CLOUDFRONT_ID="E2X9GFJG11X571"

echo "📋 Current Status Check:"
echo "Stack: $STACK_NAME"
echo "CloudFront: $CLOUDFRONT_ID"

# Check Lambda status
echo ""
echo "📋 Current Lambda Status:"
aws lambda get-function --function-name financial-dashboard-api-dev --query 'Configuration.LastModified' --output text

# Check if we have the new environment variables
echo ""
echo "📋 Checking for new environment variables:"
NEW_VARS=$(aws lambda get-function-configuration --function-name financial-dashboard-api-dev --query 'Environment.Variables.SERVICES_STACK_NAME' --output text 2>/dev/null)
if [ "$NEW_VARS" = "None" ] || [ -z "$NEW_VARS" ]; then
    echo "❌ New environment variables not found - Lambda needs redeployment"
    NEED_LAMBDA_DEPLOY=true
else
    echo "✅ New environment variables found: $NEW_VARS"
    NEED_LAMBDA_DEPLOY=false
fi

# Check CloudFront cache age
echo ""
echo "📋 CloudFront Distribution Status:"
aws cloudfront get-distribution --id $CLOUDFRONT_ID --query 'Distribution.{Status:Status,LastModifiedTime:LastModifiedTime}' --output table

# Option 1: Invalidate CloudFront cache to force frontend refresh
echo ""
echo "🔄 Invalidating CloudFront cache to refresh frontend..."
INVALIDATION_ID=$(aws cloudfront create-invalidation \
    --distribution-id $CLOUDFRONT_ID \
    --paths "/*" \
    --query 'Invalidation.Id' \
    --output text)

echo "✅ CloudFront invalidation created: $INVALIDATION_ID"
echo "⏳ Cache invalidation usually takes 1-5 minutes"

# Option 2: Manual Lambda deployment (if environment variables are missing)
if [ "$NEED_LAMBDA_DEPLOY" = true ]; then
    echo ""
    echo "🚀 Lambda needs redeployment with new configuration..."
    echo "📋 This requires running the full GitHub workflow or manual SAM deployment"
    echo ""
    echo "🔧 Quick manual deployment option:"
    echo "1. Ensure services stack outputs are available"
    echo "2. Run SAM build and deploy with new parameters"
    echo ""
    
    # Check services stack outputs
    echo "📋 Checking services stack outputs:"
    aws cloudformation describe-stacks --stack-name stocks-aws-services-dev --query 'Stacks[0].Outputs[?OutputKey==`RedisEndpoint`].OutputValue' --output text || echo "❌ Services stack not found"
fi

echo ""
echo "📊 Quick Test Commands:"
echo "# Test new config endpoint:"
echo "curl 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/config'"
echo ""
echo "# Test frontend (wait 2-3 minutes after invalidation):"
echo "curl -I 'https://d1zb7knau41vl9.cloudfront.net' | grep -i 'last-modified\\|etag'"
echo ""
echo "🔄 After cache invalidation completes, the frontend should load the fixed SessionManager"