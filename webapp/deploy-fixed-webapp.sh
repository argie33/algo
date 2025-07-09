#!/bin/bash

set -e

echo "🚀 Starting complete webapp deployment with database connectivity fix"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Set AWS region
AWS_REGION=${AWS_REGION:-us-east-1}
export AWS_DEFAULT_REGION=$AWS_REGION

print_status "Using AWS region: $AWS_REGION"

# Step 1: Package Lambda code
print_status "Packaging Lambda code..."
cd lambda

# Clean and install dependencies
rm -rf node_modules package-lock.json
npm install --only=production --no-audit --no-fund

# Create deployment package
zip -r ../lambda-deployment.zip . -x "*.git*" "node_modules/.cache/*" "*.DS_Store*"

cd ..

print_success "Lambda code packaged successfully"

# Step 2: Upload Lambda code to S3
print_status "Uploading Lambda package to S3..."

# Get the code bucket name from CloudFormation
CODE_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name stocks-core-infrastructure \
    --query "Stacks[0].Outputs[?OutputKey=='CodeBucketName'].OutputValue" \
    --output text 2>/dev/null || echo "")

if [ -z "$CODE_BUCKET" ]; then
    print_error "Could not find code bucket. Ensure stocks-core-infrastructure stack is deployed."
    exit 1
fi

# Upload with versioned key
LAMBDA_KEY="webapp-lambda-$(date +%Y%m%d-%H%M%S).zip"
aws s3 cp lambda-deployment.zip "s3://$CODE_BUCKET/$LAMBDA_KEY"

print_success "Lambda package uploaded to s3://$CODE_BUCKET/$LAMBDA_KEY"

# Step 3: Get database secret ARN
print_status "Getting database secret ARN..."

DB_SECRET_ARN=$(aws cloudformation describe-stacks \
    --stack-name stocks-app-infrastructure \
    --query "Stacks[0].Outputs[?OutputKey=='SecretArn'].OutputValue" \
    --output text 2>/dev/null || echo "")

if [ -z "$DB_SECRET_ARN" ]; then
    print_error "Could not find database secret ARN. Ensure stocks-app-infrastructure stack is deployed."
    exit 1
fi

print_success "Found database secret: $DB_SECRET_ARN"

# Step 4: Deploy/Update the webapp stack
print_status "Deploying webapp CloudFormation stack..."

STACK_NAME="stocks-webapp-serverless"

# Check if stack exists
if aws cloudformation describe-stacks --stack-name $STACK_NAME >/dev/null 2>&1; then
    print_status "Stack exists, updating..."
    OPERATION="update-stack"
else
    print_status "Stack doesn't exist, creating..."
    OPERATION="create-stack"
fi

# Deploy the stack
aws cloudformation $OPERATION \
    --stack-name $STACK_NAME \
    --template-body file://template-webapp-serverless.yml \
    --parameters \
        ParameterKey=LambdaCodeKey,ParameterValue=$LAMBDA_KEY \
        ParameterKey=CertificateArn,ParameterValue="" \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM

print_status "Waiting for stack deployment to complete..."

# Wait for stack operation to complete
aws cloudformation wait stack-$OPERATION-complete --stack-name $STACK_NAME

# Check if deployment was successful
if [ $? -eq 0 ]; then
    print_success "Stack deployment completed successfully!"
else
    print_error "Stack deployment failed!"
    
    # Get stack events for debugging
    print_status "Recent stack events:"
    aws cloudformation describe-stack-events \
        --stack-name $STACK_NAME \
        --query "StackEvents[?ResourceStatus=='CREATE_FAILED' || ResourceStatus=='UPDATE_FAILED'].[LogicalResourceId,ResourceStatus,ResourceStatusReason]" \
        --output table
    exit 1
fi

# Step 5: Get outputs
print_status "Getting deployment outputs..."

API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
    --output text)

SPA_URL=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query "Stacks[0].Outputs[?OutputKey=='SPAUrl'].OutputValue" \
    --output text)

USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
    --output text)

USER_POOL_CLIENT_ID=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
    --output text)

# Step 6: Test the API
print_status "Testing API endpoints..."

echo ""
print_success "=== DEPLOYMENT COMPLETE ==="
print_success "API Endpoint: $API_ENDPOINT"
print_success "SPA URL: https://$SPA_URL"
print_success "Cognito User Pool ID: $USER_POOL_ID"
print_success "Cognito Client ID: $USER_POOL_CLIENT_ID"
echo ""

# Test basic endpoint
print_status "Testing API connectivity..."
if curl -s -f "$API_ENDPOINT" >/dev/null; then
    print_success "✅ API root endpoint is responding"
else
    print_warning "⚠️  API root endpoint test failed"
fi

# Test health endpoint
print_status "Testing health endpoint..."
if curl -s -f "$API_ENDPOINT/health?quick=true" >/dev/null; then
    print_success "✅ Health endpoint is responding"
else
    print_warning "⚠️  Health endpoint test failed"
fi

# Test stocks endpoint
print_status "Testing stocks endpoint..."
STOCKS_RESPONSE=$(curl -s "$API_ENDPOINT/api/stocks?limit=1" || echo "")
if echo "$STOCKS_RESPONSE" | grep -q "success"; then
    print_success "✅ Stocks endpoint is working with database"
else
    print_warning "⚠️  Stocks endpoint may have database issues"
    echo "Response: $STOCKS_RESPONSE"
fi

echo ""
print_success "🎉 Webapp deployment completed!"
print_status "You can now test your endpoints:"
print_status "- API Health: $API_ENDPOINT/health"
print_status "- Stocks API: $API_ENDPOINT/api/stocks"
print_status "- Stock Screen: $API_ENDPOINT/api/stocks/screen"

# Clean up
rm -f lambda-deployment.zip

print_success "Deployment script completed successfully!"