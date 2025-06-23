#!/bin/bash

# Financial Dashboard - Serverless Deployment Script
# This script deploys the webapp to AWS Lambda + API Gateway + CloudFront

set -e  # Exit on any error

# Configuration
ENVIRONMENT=${1:-prod}
AWS_REGION=${AWS_REGION:-us-east-1}
STACK_NAME="financial-dashboard-${ENVIRONMENT}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check SAM CLI
    if ! command -v sam &> /dev/null; then
        log_error "SAM CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check Node.js
    if ! command -v node &> /dev/null; then
        log_error "Node.js is not installed. Please install Node.js 18 or later."
        exit 1
    fi
    
    # Check npm
    if ! command -v npm &> /dev/null; then
        log_error "npm is not installed. Please install npm."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials are not configured. Please run 'aws configure'."
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Build Lambda function
build_lambda() {
    log_info "Building Lambda function..."
    
    cd webapp/lambda
    
    # Install dependencies
    log_info "Installing Lambda dependencies..."
    npm ci --only=production
    
    # Verify required files exist
    if [ ! -f "index.js" ]; then
        log_error "Lambda function index.js not found"
        exit 1
    fi
    
    if [ ! -f "package.json" ]; then
        log_error "Lambda package.json not found"
        exit 1
    fi
    
    cd ../..
    log_success "Lambda function built successfully"
}

# Build frontend
build_frontend() {
    log_info "Building frontend..."
    
    cd webapp/frontend
    
    # Install dependencies
    log_info "Installing frontend dependencies..."
    npm ci
    
    # Build with serverless configuration
    log_info "Building frontend for serverless deployment..."
    VITE_SERVERLESS=true VITE_API_URL=/api npm run build
    
    # Verify build output
    if [ ! -d "dist" ]; then
        log_error "Frontend build failed - dist directory not found"
        exit 1
    fi
    
    cd ../..
    log_success "Frontend built successfully"
}

# Deploy infrastructure
deploy_infrastructure() {
    log_info "Deploying infrastructure..."
    
    # Get database secret ARN
    log_info "Looking up database secret..."
    DB_SECRET_ARN=$(aws secretsmanager list-secrets \
        --query "SecretList[?contains(Name, 'rds-db-credentials')].ARN | [0]" \
        --output text \
        --region $AWS_REGION)
    
    if [ "$DB_SECRET_ARN" = "None" ] || [ -z "$DB_SECRET_ARN" ]; then
        log_error "Database secret not found. Please ensure RDS is deployed first."
        exit 1
    fi
    
    log_info "Using database secret: $DB_SECRET_ARN"
    
    # Deploy with SAM
    log_info "Deploying CloudFormation stack..."
    sam deploy \
        --template-file webapp/template-webapp-lambda.yml \
        --stack-name $STACK_NAME \
        --capabilities CAPABILITY_IAM \
        --parameter-overrides \
            EnvironmentName=$ENVIRONMENT \
            DatabaseSecretArn=$DB_SECRET_ARN \
        --no-fail-on-empty-changeset \
        --region $AWS_REGION
    
    log_success "Infrastructure deployed successfully"
}

# Get stack outputs
get_stack_outputs() {
    log_info "Getting stack outputs..."
    
    API_URL=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" \
        --output text \
        --region $AWS_REGION)
    
    BUCKET_NAME=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" \
        --output text \
        --region $AWS_REGION)
    
    CLOUDFRONT_ID=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" \
        --output text \
        --region $AWS_REGION)
    
    WEBSITE_URL=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query "Stacks[0].Outputs[?OutputKey=='WebsiteURL'].OutputValue" \
        --output text \
        --region $AWS_REGION)
    
    log_success "Stack outputs retrieved"
}

# Deploy frontend to S3
deploy_frontend() {
    log_info "Deploying frontend to S3..."
    
    if [ -z "$BUCKET_NAME" ]; then
        log_error "S3 bucket name not found"
        exit 1
    fi
    
    # Sync frontend files
    log_info "Syncing files to S3 bucket: $BUCKET_NAME"
    
    # Upload assets with long cache
    aws s3 sync webapp/frontend/dist s3://$BUCKET_NAME \
        --delete \
        --cache-control "public, max-age=31536000" \
        --exclude "*.html" \
        --exclude "service-worker.js" \
        --region $AWS_REGION
    
    # Upload HTML files with short cache
    aws s3 sync webapp/frontend/dist s3://$BUCKET_NAME \
        --cache-control "public, max-age=300" \
        --include "*.html" \
        --include "service-worker.js" \
        --region $AWS_REGION
    
    log_success "Frontend deployed to S3"
}

# Invalidate CloudFront cache
invalidate_cloudfront() {
    log_info "Invalidating CloudFront cache..."
    
    if [ -z "$CLOUDFRONT_ID" ]; then
        log_error "CloudFront distribution ID not found"
        exit 1
    fi
    
    aws cloudfront create-invalidation \
        --distribution-id $CLOUDFRONT_ID \
        --paths "/*" \
        --region $AWS_REGION
    
    log_success "CloudFront cache invalidated"
}

# Test deployment
test_deployment() {
    log_info "Testing deployment..."
    
    # Test API health
    log_info "Testing API health..."
    for i in {1..10}; do
        if curl -f -s "$API_URL/health" > /dev/null; then
            log_success "API health check passed"
            break
        else
            log_warning "API not ready, attempt $i/10"
            sleep 30
        fi
        
        if [ $i -eq 10 ]; then
            log_error "API health check failed after 10 attempts"
            exit 1
        fi
    done
    
    # Test frontend
    log_info "Testing frontend..."
    if curl -f -s "$WEBSITE_URL" > /dev/null; then
        log_success "Frontend accessibility test passed"
    else
        log_error "Frontend accessibility test failed"
        exit 1
    fi
    
    log_success "All tests passed"
}

# Main deployment function
main() {
    log_info "🚀 Starting Financial Dashboard serverless deployment..."
    log_info "Environment: $ENVIRONMENT"
    log_info "Region: $AWS_REGION"
    log_info "Stack: $STACK_NAME"
    echo
    
    check_prerequisites
    build_lambda
    build_frontend
    deploy_infrastructure
    get_stack_outputs
    deploy_frontend
    invalidate_cloudfront
    test_deployment
    
    # Print summary
    echo
    log_success "🎉 Deployment completed successfully!"
    echo
    echo -e "${BLUE}📋 Deployment Summary:${NC}"
    echo "Environment: $ENVIRONMENT"
    echo "Region: $AWS_REGION"
    echo "Stack: $STACK_NAME"
    echo
    echo -e "${BLUE}🌐 URLs:${NC}"
    echo "Website: $WEBSITE_URL"
    echo "API: $API_URL"
    echo
    echo -e "${BLUE}☁️ AWS Resources:${NC}"
    echo "S3 Bucket: $BUCKET_NAME"
    echo "CloudFront: $CLOUDFRONT_ID"
    echo
    echo -e "${GREEN}💰 Cost Savings: 85-95% reduction vs ECS (estimated $1-5/month)${NC}"
    echo
    log_success "✅ Financial Dashboard is now live on serverless architecture!"
}

# Handle script arguments
case "${1:-}" in
    -h|--help)
        echo "Usage: $0 [environment]"
        echo "Environments: dev, staging, prod (default: prod)"
        exit 0
        ;;
    dev|staging|prod|"")
        main
        ;;
    *)
        log_error "Invalid environment: $1"
        echo "Valid environments: dev, staging, prod"
        exit 1
        ;;
esac
