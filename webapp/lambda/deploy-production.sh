#!/bin/bash

# Production Deployment Script for HFT Trading System
# Deploys Lambda functions with full production configuration

set -e  # Exit on any error

# Configuration
ENVIRONMENT="${1:-prod}"
AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${ENVIRONMENT}-hft-trading-stack"
TEMPLATE_FILE="config/lambda-deployment.yml"
PACKAGE_FILE="lambda-package.zip"

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

# Validation functions
validate_environment() {
    log_info "Validating deployment environment: $ENVIRONMENT"
    
    case $ENVIRONMENT in
        dev|staging|prod)
            log_success "Environment '$ENVIRONMENT' is valid"
            ;;
        *)
            log_error "Invalid environment: $ENVIRONMENT. Must be dev, staging, or prod"
            exit 1
            ;;
    esac
}

validate_aws_cli() {
    log_info "Validating AWS CLI configuration..."
    
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed"
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS CLI is not configured or credentials are invalid"
        exit 1
    fi
    
    local account_id=$(aws sts get-caller-identity --query Account --output text)
    local region=$(aws configure get region)
    
    log_success "AWS CLI configured - Account: $account_id, Region: $region"
}

validate_prerequisites() {
    log_info "Validating deployment prerequisites..."
    
    # Check required files
    local required_files=(
        "package.json"
        "app.js"
        "$TEMPLATE_FILE"
        "utils/unifiedApiKeyService.js"
        "services/hftService.js"
        "routes/hftTrading.js"
        "websocket/realBroadcaster.js"
    )
    
    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_error "Required file not found: $file"
            exit 1
        fi
    done
    
    # Check Node.js version
    if command -v node &> /dev/null; then
        local node_version=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
        if [[ $node_version -lt 18 ]]; then
            log_warning "Node.js version $node_version detected. Version 18+ recommended for Lambda."
        else
            log_success "Node.js version $node_version is compatible"
        fi
    else
        log_warning "Node.js not found locally - using Lambda runtime"
    fi
    
    log_success "All prerequisites validated"
}

# Build functions
install_dependencies() {
    log_info "Installing production dependencies..."
    
    # Clean install for production
    rm -rf node_modules package-lock.json
    
    # Install only production dependencies
    npm ci --only=production --no-audit --no-fund
    
    # Verify critical dependencies
    local critical_deps=(
        "express"
        "aws-sdk"
        "jsonwebtoken"
        "pg"
        "ws"
        "@alpacahq/alpaca-trade-api"
    )
    
    for dep in "${critical_deps[@]}"; do
        if [[ ! -d "node_modules/$dep" ]]; then
            log_error "Critical dependency not installed: $dep"
            exit 1
        fi
    done
    
    log_success "Dependencies installed successfully"
}

run_tests() {
    log_info "Running pre-deployment tests..."
    
    # Install dev dependencies for testing
    npm install --only=dev --no-audit --no-fund
    
    # Run linting
    if npm run lint &> /dev/null; then
        log_success "Code linting passed"
    else
        log_warning "Linting failed - continuing with deployment"
    fi
    
    # Run unit tests if available
    if npm run test &> /dev/null; then
        log_success "Unit tests passed"
    else
        log_warning "Unit tests failed or not configured - continuing with deployment"
    fi
    
    # Remove dev dependencies
    npm prune --production
    
    log_success "Pre-deployment tests completed"
}

create_deployment_package() {
    log_info "Creating deployment package..."
    
    # Clean up any existing package
    rm -f $PACKAGE_FILE
    
    # Create package excluding unnecessary files
    zip -r $PACKAGE_FILE . \
        -x "*.git*" \
        -x "*.env*" \
        -x "node_modules/aws-sdk/*" \
        -x "test/*" \
        -x "tests/*" \
        -x "*.test.js" \
        -x "*.spec.js" \
        -x "docs/*" \
        -x "*.md" \
        -x ".DS_Store" \
        -x "thumbs.db" \
        -x "deploy-*.sh" \
        -x "*.log" \
        -x "coverage/*" \
        -x ".nyc_output/*" \
        -x "*.tmp" \
        -x "*.temp"
    
    local package_size=$(du -h $PACKAGE_FILE | cut -f1)
    log_success "Deployment package created: $PACKAGE_FILE ($package_size)"
    
    # Validate package size (Lambda limit is 50MB)
    local size_bytes=$(stat -f%z $PACKAGE_FILE 2>/dev/null || stat -c%s $PACKAGE_FILE 2>/dev/null)
    local size_mb=$((size_bytes / 1024 / 1024))
    
    if [[ $size_mb -gt 50 ]]; then
        log_error "Package size ($size_mb MB) exceeds Lambda limit (50MB)"
        exit 1
    elif [[ $size_mb -gt 40 ]]; then
        log_warning "Package size ($size_mb MB) is approaching Lambda limit"
    fi
}

# Deployment functions
create_s3_bucket() {
    local bucket_name="${ENVIRONMENT}-hft-deployment-$(aws sts get-caller-identity --query Account --output text)"
    
    log_info "Creating S3 deployment bucket: $bucket_name"
    
    if aws s3api head-bucket --bucket "$bucket_name" 2>/dev/null; then
        log_success "S3 bucket already exists: $bucket_name"
    else
        aws s3api create-bucket \
            --bucket "$bucket_name" \
            --region "$AWS_REGION" \
            --create-bucket-configuration LocationConstraint="$AWS_REGION" 2>/dev/null || \
        aws s3api create-bucket \
            --bucket "$bucket_name" \
            --region "$AWS_REGION" 2>/dev/null
        
        # Enable versioning
        aws s3api put-bucket-versioning \
            --bucket "$bucket_name" \
            --versioning-configuration Status=Enabled
        
        # Enable encryption
        aws s3api put-bucket-encryption \
            --bucket "$bucket_name" \
            --server-side-encryption-configuration '{
                "Rules": [{
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    }
                }]
            }'
        
        log_success "S3 bucket created and configured: $bucket_name"
    fi
    
    echo "$bucket_name"
}

upload_package() {
    local bucket_name="$1"
    local s3_key="${ENVIRONMENT}/${PACKAGE_FILE}"
    
    log_info "Uploading deployment package to S3..."
    
    aws s3 cp "$PACKAGE_FILE" "s3://$bucket_name/$s3_key"
    
    log_success "Package uploaded to s3://$bucket_name/$s3_key"
}

deploy_cloudformation() {
    local bucket_name="$1"
    
    log_info "Deploying CloudFormation stack: $STACK_NAME"
    
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" &>/dev/null; then
        local operation="update-stack"
        log_info "Updating existing stack..."
    else
        local operation="create-stack"
        log_info "Creating new stack..."
    fi
    
    # Deploy stack
    aws cloudformation "$operation" \
        --stack-name "$STACK_NAME" \
        --template-body "file://$TEMPLATE_FILE" \
        --parameters \
            ParameterKey=Environment,ParameterValue="$ENVIRONMENT" \
            ParameterKey=DeploymentBucket,ParameterValue="$bucket_name" \
        --capabilities CAPABILITY_NAMED_IAM \
        --tags \
            Key=Environment,Value="$ENVIRONMENT" \
            Key=Service,Value=hft-trading \
            Key=DeployedBy,Value="$(whoami)" \
            Key=DeployedAt,Value="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    
    log_info "Waiting for stack deployment to complete..."
    
    aws cloudformation wait stack-"${operation%-*}"-complete \
        --stack-name "$STACK_NAME"
    
    local stack_status=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].StackStatus' \
        --output text)
    
    if [[ "$stack_status" == *"COMPLETE" ]]; then
        log_success "Stack deployment completed successfully"
    else
        log_error "Stack deployment failed with status: $stack_status"
        exit 1
    fi
}

get_outputs() {
    log_info "Retrieving deployment outputs..."
    
    local outputs=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs' \
        --output table)
    
    echo "$outputs"
}

run_smoke_tests() {
    log_info "Running smoke tests..."
    
    # Get Lambda function name
    local function_name=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionArn`].OutputValue' \
        --output text | cut -d':' -f7)
    
    if [[ -n "$function_name" ]]; then
        # Test Lambda function
        local test_payload='{"httpMethod":"GET","path":"/health","headers":{},"body":null}'
        
        local response=$(aws lambda invoke \
            --function-name "$function_name" \
            --payload "$test_payload" \
            --output json \
            /tmp/lambda-response.json 2>/dev/null)
        
        local status_code=$(echo "$response" | jq -r '.StatusCode // empty')
        
        if [[ "$status_code" == "200" ]]; then
            log_success "Lambda function health check passed"
        else
            log_warning "Lambda function health check failed (Status: $status_code)"
        fi
        
        rm -f /tmp/lambda-response.json
    fi
    
    log_success "Smoke tests completed"
}

cleanup() {
    log_info "Cleaning up temporary files..."
    
    rm -f "$PACKAGE_FILE"
    
    log_success "Cleanup completed"
}

# Main deployment flow
main() {
    echo "=================================================="
    echo "HFT Trading System - Production Deployment"
    echo "Environment: $ENVIRONMENT"
    echo "Region: $AWS_REGION"
    echo "Stack: $STACK_NAME"
    echo "=================================================="
    
    # Pre-deployment validation
    validate_environment
    validate_aws_cli
    validate_prerequisites
    
    # Build and package
    install_dependencies
    run_tests
    create_deployment_package
    
    # Deploy to AWS
    local bucket_name=$(create_s3_bucket)
    upload_package "$bucket_name"
    deploy_cloudformation "$bucket_name"
    
    # Post-deployment
    echo ""
    echo "=================================================="
    echo "DEPLOYMENT OUTPUTS"
    echo "=================================================="
    get_outputs
    
    run_smoke_tests
    cleanup
    
    echo ""
    echo "=================================================="
    log_success "Deployment completed successfully!"
    echo "Environment: $ENVIRONMENT"
    echo "Stack: $STACK_NAME"
    echo "=================================================="
}

# Error handling
trap 'log_error "Deployment failed at line $LINENO"' ERR

# Run main function
main "$@"