#!/bin/bash

# Simple Lambda deployment script for Financial Dashboard API
set -e

# Configuration
ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-us-east-1}
STACK_NAME="financial-dashboard-lambda-${ENVIRONMENT}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if we're in the right directory
if [ ! -d "lambda" ] || [ ! -f "template-webapp-lambda.yml" ]; then
    log_error "Please run this script from the webapp directory containing lambda/ folder"
    exit 1
fi

# Build Lambda package
log_info "Building Lambda package..."
cd lambda

# Install production dependencies
log_info "Installing production dependencies..."
npm ci --only=production

# Create deployment package
log_info "Creating deployment package..."
rm -f ../lambda-package.zip

# Use Python's zipfile module as alternative to zip command
python3 -c "
import zipfile
import os
import sys

def create_zip(source_dir, output_file):
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            # Skip cache and test directories
            dirs[:] = [d for d in dirs if not d.endswith('.cache') and d != 'tests']
            
            for file in files:
                # Skip test files
                if file.endswith('.test.js'):
                    continue
                    
                file_path = os.path.join(root, file)
                arc_name = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, arc_name)

create_zip('.', '../lambda-package.zip')
print('Package created successfully')
"

cd ..

# Get database secret ARN - check multiple possible names
log_info "Looking for database secret..."
DB_SECRET_ARN=""

# Try different possible secret names
POSSIBLE_SECRETS=(
    "rds-db-credentials/financial-dashboard"
    "financial-dashboard-db"
    "stocks-db-credentials"
    "rds-db-credentials"
)

for secret_pattern in "${POSSIBLE_SECRETS[@]}"; do
    SECRET_ARN=$(aws secretsmanager list-secrets \
        --query "SecretList[?contains(Name, '${secret_pattern}')].ARN | [0]" \
        --output text \
        --region $AWS_REGION 2>/dev/null || echo "None")
    
    if [ "$SECRET_ARN" != "None" ] && [ -n "$SECRET_ARN" ]; then
        DB_SECRET_ARN=$SECRET_ARN
        log_info "Found database secret: $DB_SECRET_ARN"
        break
    fi
done

if [ -z "$DB_SECRET_ARN" ] || [ "$DB_SECRET_ARN" = "None" ]; then
    log_warning "Database secret not found. Creating mock secret for deployment..."
    
    # Create a temporary secret for deployment
    DB_SECRET_ARN=$(aws secretsmanager create-secret \
        --name "financial-dashboard-db-temp" \
        --description "Temporary database secret for Lambda deployment" \
        --secret-string '{"host":"localhost","port":"5432","username":"user","password":"pass","dbname":"stocks"}' \
        --query "ARN" \
        --output text \
        --region $AWS_REGION)
    
    log_warning "Created temporary secret: $DB_SECRET_ARN"
fi

# Deploy Lambda function
log_info "Deploying Lambda function..."

# Check if function exists
FUNCTION_EXISTS=$(aws lambda get-function --function-name "financial-dashboard-api-${ENVIRONMENT}" --region $AWS_REGION --query 'Configuration.FunctionName' --output text 2>/dev/null || echo "NotFound")

if [ "$FUNCTION_EXISTS" = "NotFound" ]; then
    log_info "Creating new Lambda function..."
    
    # Create IAM role for Lambda if it doesn't exist
    ROLE_ARN=$(aws iam get-role --role-name "financial-dashboard-lambda-role" --query 'Role.Arn' --output text 2>/dev/null || echo "NotFound")
    
    if [ "$ROLE_ARN" = "NotFound" ]; then
        log_info "Creating Lambda execution role..."
        
        # Create trust policy
        cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

        # Create role
        ROLE_ARN=$(aws iam create-role \
            --role-name "financial-dashboard-lambda-role" \
            --assume-role-policy-document file://trust-policy.json \
            --query 'Role.Arn' \
            --output text)
        
        # Attach policies
        aws iam attach-role-policy \
            --role-name "financial-dashboard-lambda-role" \
            --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
        
        aws iam attach-role-policy \
            --role-name "financial-dashboard-lambda-role" \
            --policy-arn "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
        
        rm trust-policy.json
        
        log_info "Waiting for role to be ready..."
        sleep 10
    fi
    
    # Create Lambda function
    aws lambda create-function \
        --function-name "financial-dashboard-api-${ENVIRONMENT}" \
        --runtime nodejs18.x \
        --role $ROLE_ARN \
        --handler index.handler \
        --zip-file fileb://lambda-package.zip \
        --timeout 45 \
        --memory-size 512 \
        --environment Variables="{NODE_ENV=${ENVIRONMENT},DB_SECRET_ARN=${DB_SECRET_ARN},WEBAPP_AWS_REGION=${AWS_REGION}}" \
        --region $AWS_REGION
    
    log_success "Lambda function created"
else
    log_info "Updating existing Lambda function..."
    
    # Update function code
    aws lambda update-function-code \
        --function-name "financial-dashboard-api-${ENVIRONMENT}" \
        --zip-file fileb://lambda-package.zip \
        --region $AWS_REGION
    
    # Update environment variables
    aws lambda update-function-configuration \
        --function-name "financial-dashboard-api-${ENVIRONMENT}" \
        --environment Variables="{NODE_ENV=${ENVIRONMENT},DB_SECRET_ARN=${DB_SECRET_ARN},WEBAPP_AWS_REGION=${AWS_REGION}}" \
        --region $AWS_REGION
    
    log_success "Lambda function updated"
fi

# Setup database tables
log_info "Setting up database tables..."
if [ -f "setup-database.js" ]; then
    export DB_SECRET_ARN="$DB_SECRET_ARN"
    export AWS_REGION="$AWS_REGION"
    if node setup-database.js; then
        log_success "Database tables created successfully"
    else
        log_error "Failed to create database tables"
        exit 1
    fi
else
    log_warning "setup-database.js not found, skipping database setup"
fi

# Create or update API Gateway if needed
log_info "Setting up API Gateway..."

# Check if API exists
API_ID=$(aws apigatewayv2 get-apis --query "Items[?Name=='financial-dashboard-api-${ENVIRONMENT}'].ApiId | [0]" --output text --region $AWS_REGION 2>/dev/null || echo "None")

if [ "$API_ID" = "None" ] || [ -z "$API_ID" ]; then
    log_info "Creating API Gateway..."
    
    # Create HTTP API
    API_ID=$(aws apigatewayv2 create-api \
        --name "financial-dashboard-api-${ENVIRONMENT}" \
        --protocol-type HTTP \
        --cors-configuration AllowOrigins="*",AllowMethods="*",AllowHeaders="*" \
        --query 'ApiId' \
        --output text \
        --region $AWS_REGION)
    
    log_info "Created API Gateway: $API_ID"
fi

# Get Lambda function ARN
LAMBDA_ARN=$(aws lambda get-function \
    --function-name "financial-dashboard-api-${ENVIRONMENT}" \
    --query 'Configuration.FunctionArn' \
    --output text \
    --region $AWS_REGION)

# Create integration
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id $API_ID \
    --integration-type AWS_PROXY \
    --integration-uri $LAMBDA_ARN \
    --payload-format-version "2.0" \
    --query 'IntegrationId' \
    --output text \
    --region $AWS_REGION)

# Create route
aws apigatewayv2 create-route \
    --api-id $API_ID \
    --route-key "ANY /{proxy+}" \
    --target "integrations/$INTEGRATION_ID" \
    --region $AWS_REGION || log_warning "Route may already exist"

# Create catch-all route for root
aws apigatewayv2 create-route \
    --api-id $API_ID \
    --route-key "ANY /" \
    --target "integrations/$INTEGRATION_ID" \
    --region $AWS_REGION || log_warning "Root route may already exist"

# Create stage
aws apigatewayv2 create-stage \
    --api-id $API_ID \
    --stage-name $ENVIRONMENT \
    --auto-deploy \
    --region $AWS_REGION || log_warning "Stage may already exist"

# Add Lambda permission for API Gateway
aws lambda add-permission \
    --function-name "financial-dashboard-api-${ENVIRONMENT}" \
    --statement-id "apigateway-invoke-${ENVIRONMENT}" \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${AWS_REGION}:$(aws sts get-caller-identity --query Account --output text):${API_ID}/*/*" \
    --region $AWS_REGION || log_warning "Permission may already exist"

# Cleanup
rm -f lambda-package.zip

# Get API endpoint
API_ENDPOINT="https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/${ENVIRONMENT}"

# Test the deployment
log_info "Testing deployment..."
sleep 5

for i in {1..5}; do
    if curl -f -s "${API_ENDPOINT}/health?quick=true" > /dev/null; then
        log_success "Health check passed!"
        break
    else
        log_warning "Health check attempt $i/5 failed, retrying..."
        sleep 10
    fi
    
    if [ $i -eq 5 ]; then
        log_warning "Health check failed, but deployment completed. Check logs for issues."
    fi
done

# Print summary
echo
log_success "🎉 Lambda deployment completed!"
echo
echo -e "${BLUE}📋 Deployment Summary:${NC}"
echo "Environment: $ENVIRONMENT"
echo "Function: financial-dashboard-api-${ENVIRONMENT}"
echo "API Endpoint: $API_ENDPOINT"
echo "Database Secret: $DB_SECRET_ARN"
echo
echo -e "${BLUE}🔍 Test URLs:${NC}"
echo "Health Check: ${API_ENDPOINT}/health?quick=true"
echo "API Info: ${API_ENDPOINT}/"
echo
echo -e "${BLUE}🛠️ Next Steps:${NC}"
echo "1. Test the API endpoints"
echo "2. Update frontend API_URL to: $API_ENDPOINT"
echo "3. Ensure database is accessible from Lambda"

echo
log_success "✅ Deployment complete!"