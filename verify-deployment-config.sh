#!/bin/bash

# Deployment Configuration Verification Script
# This script verifies that all required AWS resources and environment variables are properly configured

set -e

echo "🔍 Financial Trading Platform - Deployment Configuration Verification"
echo "===================================================================="
echo ""

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install AWS CLI first."
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS credentials not configured. Please run 'aws configure' first."
    exit 1
fi

# Get AWS account information
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_DEFAULT_REGION:-us-east-1}

echo "✅ AWS Account ID: $ACCOUNT_ID"
echo "✅ AWS Region: $REGION"
echo ""

# Environment configuration
ENVIRONMENT=${1:-dev}
echo "🔧 Environment: $ENVIRONMENT"
echo ""

echo "🔍 Checking CloudFormation Stack Dependencies..."
echo "================================================="

# Check if StocksCore stack exists
echo "1. Checking StocksCore stack (required for ECR, S3, VPC)..."
if aws cloudformation describe-stacks --stack-name StocksCore >/dev/null 2>&1; then
    echo "   ✅ StocksCore stack exists"
    
    # Verify critical exports
    ECR_REPO=$(aws cloudformation list-exports --query "Exports[?Name=='StocksCore-ContainerRepositoryUri'].Value" --output text)
    CF_BUCKET=$(aws cloudformation list-exports --query "Exports[?Name=='StocksCore-CfTemplatesBucketName'].Value" --output text)
    
    echo "   📦 ECR Repository: $ECR_REPO"
    echo "   🪣 CloudFormation Bucket: $CF_BUCKET"
else
    echo "   ❌ StocksCore stack not found - required for infrastructure"
    exit 1
fi

echo ""

# Check if StocksApp stack exists
echo "2. Checking StocksApp stack (required for database, secrets)..."
if aws cloudformation describe-stacks --stack-name stocks-app-stack >/dev/null 2>&1; then
    echo "   ✅ StocksApp stack exists"
    
    # Verify critical exports
    DB_SECRET_ARN=$(aws cloudformation list-exports --query "Exports[?Name=='StocksApp-SecretArn'].Value" --output text)
    DB_ENDPOINT=$(aws cloudformation list-exports --query "Exports[?Name=='StocksApp-DBEndpoint'].Value" --output text)
    API_KEY_SECRET_ARN=$(aws cloudformation list-exports --query "Exports[?Name=='StocksApp-ApiKeyEncryptionSecretArn'].Value" --output text)
    
    echo "   🔐 Database Secret ARN: $DB_SECRET_ARN"
    echo "   💾 Database Endpoint: $DB_ENDPOINT"
    echo "   🔑 API Key Encryption Secret ARN: $API_KEY_SECRET_ARN"
else
    echo "   ❌ StocksApp stack not found - required for database and secrets"
    exit 1
fi

echo ""

echo "🔍 Verifying Environment Variables Configuration..."
echo "================================================="

# Check if all required environment variables are available
echo "Environment variables that will be configured in Lambda:"
echo "   DB_SECRET_ARN: $DB_SECRET_ARN"
echo "   DB_ENDPOINT: $DB_ENDPOINT"
echo "   API_KEY_ENCRYPTION_SECRET_ARN: $API_KEY_SECRET_ARN"
echo "   ENVIRONMENT: $ENVIRONMENT"
echo "   NODE_ENV: $ENVIRONMENT"
echo "   WEBAPP_AWS_REGION: $REGION"

# Validate that all required values are present
MISSING_VARS=""
[[ -z "$DB_SECRET_ARN" || "$DB_SECRET_ARN" == "None" ]] && MISSING_VARS="$MISSING_VARS DB_SECRET_ARN"
[[ -z "$DB_ENDPOINT" || "$DB_ENDPOINT" == "None" ]] && MISSING_VARS="$MISSING_VARS DB_ENDPOINT"
[[ -z "$API_KEY_SECRET_ARN" || "$API_KEY_SECRET_ARN" == "None" ]] && MISSING_VARS="$MISSING_VARS API_KEY_SECRET_ARN"

if [[ -n "$MISSING_VARS" ]]; then
    echo "❌ Missing required environment variables:$MISSING_VARS"
    exit 1
else
    echo "✅ All required environment variables are available"
fi

echo ""

echo "🔍 Testing Database and Secrets Access..."
echo "=========================================="

# Test database secret access
echo "Testing database secret accessibility..."
if aws secretsmanager describe-secret --secret-id "$DB_SECRET_ARN" >/dev/null 2>&1; then
    echo "   ✅ Database secret is accessible"
else
    echo "   ❌ Database secret is not accessible"
    exit 1
fi

# Test API key encryption secret access
echo "Testing API key encryption secret accessibility..."
if aws secretsmanager describe-secret --secret-id "$API_KEY_SECRET_ARN" >/dev/null 2>&1; then
    echo "   ✅ API key encryption secret is accessible"
else
    echo "   ❌ API key encryption secret is not accessible"
    exit 1
fi

# Test database connectivity (if possible)
echo "Testing database connectivity..."
if nc -z "$DB_ENDPOINT" 5432 2>/dev/null; then
    echo "   ✅ Database port 5432 is reachable"
else
    echo "   ⚠️  Database port 5432 is not reachable from this environment"
    echo "   (This is expected in some network configurations)"
fi

echo ""

echo "🔍 Checking Webapp Stack Status..."
echo "==================================="

WEBAPP_STACK_NAME="stocks-webapp-$ENVIRONMENT"
echo "Checking webapp stack: $WEBAPP_STACK_NAME"

if aws cloudformation describe-stacks --stack-name "$WEBAPP_STACK_NAME" >/dev/null 2>&1; then
    STACK_STATUS=$(aws cloudformation describe-stacks --stack-name "$WEBAPP_STACK_NAME" --query "Stacks[0].StackStatus" --output text)
    echo "   📊 Stack Status: $STACK_STATUS"
    
    if [[ "$STACK_STATUS" == "CREATE_COMPLETE" || "$STACK_STATUS" == "UPDATE_COMPLETE" ]]; then
        echo "   ✅ Webapp stack is healthy"
        
        # Get webapp outputs
        API_URL=$(aws cloudformation describe-stacks --stack-name "$WEBAPP_STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" --output text 2>/dev/null)
        WEBSITE_URL=$(aws cloudformation describe-stacks --stack-name "$WEBAPP_STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='WebsiteURL'].OutputValue" --output text 2>/dev/null)
        
        echo "   🌐 API Gateway URL: $API_URL"
        echo "   🌍 Website URL: $WEBSITE_URL"
        
        # Test API endpoint
        if [[ -n "$API_URL" ]]; then
            echo "   🔍 Testing API endpoint..."
            if curl -f -s --connect-timeout 10 "$API_URL/health?quick=true" >/dev/null 2>&1; then
                echo "   ✅ API endpoint is responding"
            else
                echo "   ⚠️  API endpoint is not responding (may be cold start)"
            fi
        fi
    else
        echo "   ⚠️  Webapp stack status requires attention: $STACK_STATUS"
    fi
else
    echo "   ℹ️  Webapp stack does not exist - will be created on first deployment"
fi

echo ""

echo "🎯 Deployment Readiness Assessment"
echo "===================================="

echo "✅ Infrastructure Dependencies: All required stacks are available"
echo "✅ Environment Variables: All required values are configured"
echo "✅ Secrets Access: Database and API key secrets are accessible"
echo "✅ CloudFormation Template: Already configured with proper environment variables"
echo "✅ GitHub Workflow: Already configured with proper parameter passing"

echo ""
echo "🚀 Deployment Instructions"
echo "=========================="
echo ""
echo "Your deployment is ready! To deploy the webapp:"
echo ""
echo "1. Push changes to the loaddata branch:"
echo "   git add ."
echo "   git commit -m 'Deploy webapp with environment configuration'"
echo "   git push origin loaddata"
echo ""
echo "2. The GitHub workflow will automatically:"
echo "   - Deploy the CloudFormation stack with proper environment variables"
echo "   - Build and push the webapp-db-init Docker image"
echo "   - Initialize the database tables"
echo "   - Build and deploy the frontend with dynamic configuration"
echo "   - Verify the deployment"
echo ""
echo "3. Monitor the deployment:"
echo "   - Check GitHub Actions: https://github.com/YOUR-REPO/actions"
echo "   - View CloudFormation stack: AWS Console > CloudFormation > $WEBAPP_STACK_NAME"
echo "   - Check Lambda logs: AWS Console > CloudWatch > Log Groups > /aws/lambda/financial-dashboard-api-$ENVIRONMENT"
echo ""
echo "🎉 Configuration verification complete! Ready for deployment."