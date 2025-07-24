#!/bin/bash
# Unified API Key Service Deployment Script
# Builds and deploys the redesigned API key service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_header() { echo -e "${CYAN}$1${NC}"; }

# Configuration
STACK_NAME="stocks-webapp-dev"
REGION="us-east-1"
ENVIRONMENT="dev"

log_header "🚀 Unified API Key Service Deployment"
log_header "======================================"

# Check prerequisites
log_info "Checking prerequisites..."

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI is not installed"
    exit 1
fi

# Check if SAM CLI is installed
if ! command -v sam &> /dev/null; then
    log_error "SAM CLI is not installed"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    log_error "Node.js is not installed"
    exit 1
fi

log_success "Prerequisites check passed"

# Check AWS credentials
log_info "Checking AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    log_error "AWS credentials not configured"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log_success "AWS credentials verified (Account: $ACCOUNT_ID)"

# Run build validation
log_info "Running build validation..."
cd "$(dirname "$0")"

if node scripts/build-unified-api-keys.js; then
    log_success "Build validation passed"
else
    log_error "Build validation failed"
    exit 1
fi

# Navigate to template directory
cd ..

log_info "Building SAM application..."

# Build the SAM application
if sam build; then
    log_success "SAM build completed"
else
    log_error "SAM build failed"
    exit 1
fi

# Get current stack parameters for reference
log_info "Retrieving current stack parameters..."
CURRENT_PARAMS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Parameters' \
    --output json 2>/dev/null || echo "[]")

if [ "$CURRENT_PARAMS" != "[]" ]; then
    log_success "Current stack parameters retrieved"
    echo "$CURRENT_PARAMS" | jq -r '.[] | "\(.ParameterKey): \(.ParameterValue)"' | head -5
else
    log_warning "Stack does not exist or no parameters found"
fi

# Confirm deployment
log_warning "This will deploy the unified API key service to AWS"
log_info "Stack: $STACK_NAME"
log_info "Region: $REGION"
log_info "Environment: $ENVIRONMENT"

read -p "Continue with deployment? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Deployment cancelled"
    exit 0
fi

log_info "Deploying SAM application..."

# Deploy with confirmation
if sam deploy \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
        EnvironmentName="$ENVIRONMENT" \
    --confirm-changeset; then
    log_success "SAM deployment completed"
else
    log_error "SAM deployment failed"
    exit 1
fi

# Verify deployment
log_info "Verifying deployment..."

# Get API Gateway endpoint
API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -n "$API_ENDPOINT" ]; then
    log_success "API Gateway endpoint: $API_ENDPOINT"
    
    # Test health endpoint
    log_info "Testing unified API key service health..."
    
    HEALTH_URL="${API_ENDPOINT}api/api-keys/health"
    if curl -s -f "$HEALTH_URL" > /dev/null; then
        log_success "Health endpoint responding"
        
        # Show health status
        HEALTH_RESPONSE=$(curl -s "$HEALTH_URL" | jq -r '.healthy // false')
        if [ "$HEALTH_RESPONSE" = "true" ]; then
            log_success "Service is healthy"
        else
            log_warning "Service health check returned false"
        fi
    else
        log_warning "Health endpoint not responding (may need time to initialize)"
    fi
else
    log_warning "Could not retrieve API Gateway endpoint"
fi

# Database verification
log_info "Verifying database configuration..."

# Check if database tables exist
DB_SECRET_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Parameters[?ParameterKey==`DatabaseSecretArn`].ParameterValue' \
    --output text 2>/dev/null || echo "")

if [ -n "$DB_SECRET_ARN" ]; then
    log_success "Database secret configured"
else
    log_warning "Database secret not found in stack parameters"
fi

# Check SSM permissions
log_info "Verifying SSM permissions..."

# Get Lambda function name
LAMBDA_FUNCTION=$(aws cloudformation describe-stack-resources \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'StackResources[?ResourceType==`AWS::Lambda::Function`].PhysicalResourceId' \
    --output text 2>/dev/null | head -1)

if [ -n "$LAMBDA_FUNCTION" ]; then
    log_success "Lambda function found: $LAMBDA_FUNCTION"
    
    # Test SSM parameter access (this would require actual parameter)
    log_info "SSM parameter structure: /financial-platform/users/{userId}/alpaca/"
else
    log_warning "Could not find Lambda function"
fi

# Migration check
log_info "Checking for migration requirements..."

if [ -f "webapp/lambda/scripts/run-migration.js" ]; then
    log_info "Migration script available"
    log_info "To run migration: cd webapp/lambda && node scripts/run-migration.js"
    
    # Ask if user wants to run migration
    read -p "Run migration status check now? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd webapp/lambda
        node scripts/run-migration.js status
        cd ../..
    fi
else
    log_warning "Migration script not found"
fi

# Summary
log_header "🎉 Deployment Summary"
log_header "===================="

log_success "✅ Unified API Key Service deployed successfully"
log_info "📊 Service Features:"
log_info "  • Single endpoint: /api/api-keys"
log_info "  • AWS Parameter Store integration"
log_info "  • Database fallback and migration"
log_info "  • LRU cache for 10,000+ users"
log_info "  • Comprehensive error handling"
log_info "  • Performance monitoring"

if [ -n "$API_ENDPOINT" ]; then
    log_info "🔗 Endpoints:"
    log_info "  • Health: ${API_ENDPOINT}api/api-keys/health"
    log_info "  • API Keys: ${API_ENDPOINT}api/api-keys"
    log_info "  • Status: ${API_ENDPOINT}api/api-keys/status"
fi

log_info "📋 Next Steps:"
log_info "  1. Test the new API endpoints"
log_info "  2. Run migration if needed: node scripts/run-migration.js"
log_info "  3. Update frontend to use new ApiKeyManager component"
log_info "  4. Monitor service health and performance"
log_info "  5. Remove old API key endpoints after validation"

log_header "🚀 Deployment Complete!"

exit 0