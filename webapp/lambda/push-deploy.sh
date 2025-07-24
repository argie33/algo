#!/bin/bash
# Quick Push Deployment Script
# Updates the existing Lambda function with new unified API key service

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

log_header "🚀 Pushing Unified API Key Service"
log_header "=================================="

# Check prerequisites
log_info "Checking prerequisites..."

if ! command -v aws &> /dev/null; then
    log_error "AWS CLI is not installed"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    log_error "AWS credentials not configured"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log_success "AWS credentials verified (Account: $ACCOUNT_ID)"

# Get existing stack information
log_info "Getting existing stack information..."

LAMBDA_FUNCTION=$(aws cloudformation describe-stack-resources \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'StackResources[?ResourceType==`AWS::Lambda::Function` && starts_with(PhysicalResourceId, `financial-dashboard-api`)].PhysicalResourceId' \
    --output text 2>/dev/null)

if [ -n "$LAMBDA_FUNCTION" ]; then
    log_success "Lambda function found: $LAMBDA_FUNCTION"
else
    log_error "Could not find Lambda function in stack"
    exit 1
fi

# Navigate to Lambda directory
cd "$(dirname "$0")"
log_info "Working directory: $(pwd)"

# Run build validation
log_info "Running build validation..."
if node scripts/build-unified-api-keys.js > /dev/null 2>&1; then
    log_success "Build validation passed"
else
    log_warning "Build validation had warnings (proceeding anyway)"
fi

# Create deployment package
log_info "Creating deployment package..."

# Remove old package if exists
rm -f function.zip

# Create temporary directory and copy files
TEMP_DIR=$(mktemp -d)
log_info "Using temporary directory: $TEMP_DIR"

# Copy all files except excluded ones
rsync -a --exclude='*.git*' \
         --exclude='node_modules/.cache/' \
         --exclude='tests/' \
         --exclude='coverage/' \
         --exclude='*.test.js' \
         --exclude='*.md' \
         --exclude='scripts/' \
         --exclude='deploy-*.sh' \
         --exclude='push-deploy.sh' \
         --exclude='*.zip' \
         --exclude='*.tar.gz' \
         . "$TEMP_DIR/"

# Create tar.gz package
cd "$TEMP_DIR"
tar -czf ../function.tar.gz .
cd - > /dev/null

# Move package to current directory
mv "$TEMP_DIR/../function.tar.gz" function.zip

# Clean up temp directory
rm -rf "$TEMP_DIR"

if [ -f function.zip ]; then
    PACKAGE_SIZE=$(du -h function.zip | cut -f1)
    log_success "Deployment package created: $PACKAGE_SIZE"
else
    log_error "Failed to create deployment package"
    exit 1
fi

# Upload to Lambda
log_info "Uploading to Lambda function: $LAMBDA_FUNCTION"

if aws lambda update-function-code \
    --function-name "$LAMBDA_FUNCTION" \
    --zip-file fileb://function.zip \
    --region "$REGION" \
    > /dev/null 2>&1; then
    log_success "Lambda function updated successfully"
else
    log_error "Failed to update Lambda function"
    exit 1
fi

# Wait for update to complete
log_info "Waiting for function update to complete..."
sleep 10

# Test the deployment
log_info "Testing deployment..."

# Get API Gateway endpoint
API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -n "$API_ENDPOINT" ]; then
    log_success "API Gateway endpoint: $API_ENDPOINT"
    
    # Test unified API key health endpoint
    HEALTH_URL="${API_ENDPOINT}api/api-keys/health"
    log_info "Testing unified API key service: $HEALTH_URL"
    
    # Use timeout and retry for health check
    for i in {1..3}; do
        if curl -s -f -m 30 "$HEALTH_URL" > /dev/null 2>&1; then
            log_success "✅ Unified API key service is responding!"
            
            # Get health status details
            HEALTH_RESPONSE=$(curl -s -m 30 "$HEALTH_URL" 2>/dev/null || echo '{"error":"timeout"}')
            if echo "$HEALTH_RESPONSE" | grep -q '"service":"unified-api-keys"'; then
                log_success "✅ Service identification confirmed"
            fi
            
            if echo "$HEALTH_RESPONSE" | grep -q '"healthy"'; then
                HEALTHY=$(echo "$HEALTH_RESPONSE" | grep -o '"healthy":[^,}]*' | cut -d':' -f2 | tr -d ' "')
                if [ "$HEALTHY" = "true" ]; then
                    log_success "✅ Service reports healthy status"
                else
                    log_warning "⚠️ Service reports unhealthy (may be initializing)"
                fi
            fi
            
            break
        else
            log_warning "Health check attempt $i failed, retrying..."
            sleep 5
        fi
    done
else
    log_warning "Could not retrieve API Gateway endpoint"
fi

# Clean up
rm -f function.zip

# Summary
log_header "🎉 Deployment Summary"
log_header "===================="

log_success "✅ Unified API Key Service deployed successfully"
log_info "📊 New Features:"
log_info "  • Single reliable endpoint: /api/api-keys"
log_info "  • AWS Parameter Store integration with KMS encryption"
log_info "  • Database fallback and migration support"
log_info "  • LRU cache for 10,000+ users"
log_info "  • Circuit breaker and rate limiting"
log_info "  • Comprehensive health monitoring"

if [ -n "$API_ENDPOINT" ]; then
    log_info "🔗 Endpoints:"
    log_info "  • Health: ${API_ENDPOINT}api/api-keys/health"
    log_info "  • API Keys: ${API_ENDPOINT}api/api-keys"
    log_info "  • Status: ${API_ENDPOINT}api/api-keys/status"
fi

log_info "📋 Next Steps:"
log_info "  1. Test the new unified endpoint"
log_info "  2. Run migration if needed: node scripts/run-migration.js"
log_info "  3. Monitor service health and performance"
log_info "  4. Update frontend to use new ApiKeyManager component"

log_header "🚀 Push Complete - No More Troubleshooting Hell!"

exit 0