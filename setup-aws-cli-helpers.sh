#!/bin/bash

##############################################
# AWS CLI Helper Functions
# Simplifies AWS deployment from local dev
##############################################

set -e
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_step() { echo -e "${BLUE}▶ $1${NC}"; }
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }

# ================================================================
# 1. DEPLOY FRONTEND TO S3 + CLOUDFRONT
# ================================================================
deploy_frontend() {
    print_step "Deploying Frontend to S3..."
    
    S3_BUCKET="stocks-dashboard-${AWS_ACCOUNT_ID}"
    CLOUDFRONT_ID="${CLOUDFRONT_DISTRIBUTION_ID:-}"
    
    # Create bucket if doesn't exist
    aws s3 mb s3://$S3_BUCKET --region us-east-1 2>/dev/null || true
    
    # Configure for static website hosting
    aws s3api put-bucket-website \
        --bucket $S3_BUCKET \
        --website-configuration '{
            "IndexDocument": {"Suffix": "index.html"},
            "ErrorDocument": {"Key": "index.html"}
        }'
    
    # Block public access for security (CloudFront handles access)
    aws s3api put-public-access-block \
        --bucket $S3_BUCKET \
        --public-access-block-configuration \
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
    
    # Sync frontend build
    cd /home/stocks/algo/webapp/frontend
    aws s3 sync dist/ s3://$S3_BUCKET/ --delete --cache-control "public,max-age=3600"
    
    # Invalidate CloudFront cache if exists
    if [ ! -z "$CLOUDFRONT_ID" ]; then
        aws cloudfront create-invalidation \
            --distribution-id $CLOUDFRONT_ID \
            --paths "/*"
        print_success "CloudFront cache invalidated"
    fi
    
    print_success "Frontend deployed to S3://$S3_BUCKET"
    echo "S3 Website URL: http://${S3_BUCKET}.s3-website-us-east-1.amazonaws.com"
}

# ================================================================
# 2. DEPLOY BACKEND TO LAMBDA
# ================================================================
deploy_backend() {
    print_step "Deploying Backend Lambda..."
    
    LAMBDA_FUNCTION="stocks-api"
    
    cd /home/stocks/algo/webapp/lambda
    
    # Create deployment package
    print_step "Creating Lambda deployment package..."
    zip -r /tmp/lambda-deployment.zip . \
        -x "node_modules/*" "dist/*" ".git/*" \
        > /dev/null 2>&1
    
    # Update Lambda function code
    print_step "Uploading to Lambda..."
    aws lambda update-function-code \
        --function-name $LAMBDA_FUNCTION \
        --zip-file fileb:///tmp/lambda-deployment.zip \
        --query 'FunctionArn' \
        --output text
    
    # Set environment variables
    print_step "Setting environment variables..."
    aws lambda update-function-configuration \
        --function-name $LAMBDA_FUNCTION \
        --environment "Variables={
            POSTGRES_HOST=${POSTGRES_HOST},
            POSTGRES_PORT=5432,
            POSTGRES_USER=${POSTGRES_USER},
            POSTGRES_PASSWORD=${POSTGRES_PASSWORD},
            POSTGRES_DB=stocks,
            NODE_ENV=production
        }"
    
    print_success "Lambda function deployed: $LAMBDA_FUNCTION"
}

# ================================================================
# 3. CREATE/UPDATE RDS DATABASE
# ================================================================
setup_rds() {
    print_step "Setting up RDS PostgreSQL..."
    
    DB_INSTANCE="stocks-db"
    DB_CLASS="db.t3.medium"
    DB_STORAGE="100"
    
    # Check if instance exists
    if aws rds describe-db-instances \
        --db-instance-identifier $DB_INSTANCE \
        --region us-east-1 > /dev/null 2>&1; then
        print_warning "RDS instance already exists: $DB_INSTANCE"
    else
        print_step "Creating RDS instance (this may take 10-15 minutes)..."
        aws rds create-db-instance \
            --db-instance-identifier $DB_INSTANCE \
            --db-instance-class $DB_CLASS \
            --engine postgres \
            --engine-version 15.3 \
            --master-username postgres \
            --master-user-password ${POSTGRES_PASSWORD} \
            --allocated-storage $DB_STORAGE \
            --storage-type gp3 \
            --publicly-accessible \
            --multi-az
    fi
    
    # Get RDS endpoint
    ENDPOINT=$(aws rds describe-db-instances \
        --db-instance-identifier $DB_INSTANCE \
        --query 'DBInstances[0].Endpoint.Address' \
        --output text)
    
    print_success "RDS Endpoint: $ENDPOINT"
    export POSTGRES_HOST=$ENDPOINT
}

# ================================================================
# 4. IMPORT DATA INTO RDS
# ================================================================
import_data() {
    print_step "Importing data into RDS..."
    
    if [ ! -f /home/stocks/algo/aws_data_dump.sql ]; then
        print_error "Data dump file not found: aws_data_dump.sql"
        return 1
    fi
    
    psql -h $POSTGRES_HOST \
        -U postgres \
        -d postgres \
        -f /home/stocks/algo/aws_data_dump.sql
    
    print_success "Data imported successfully"
}

# ================================================================
# 5. CREATE API GATEWAY
# ================================================================
setup_api_gateway() {
    print_step "Setting up API Gateway..."
    
    # This typically requires AWS Console or CloudFormation
    # Here's a reference for CLI approach
    
    API_NAME="stocks-api"
    LAMBDA_ARN=$(aws lambda get-function \
        --function-name stocks-api \
        --query 'Configuration.FunctionArn' \
        --output text)
    
    # Grant API Gateway permission to invoke Lambda
    aws lambda add-permission \
        --function-name stocks-api \
        --statement-id AllowAPIGatewayInvoke \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        2>/dev/null || true
    
    print_success "API Gateway permissions configured"
    print_warning "Note: Create REST API in AWS Console and configure resources"
}

# ================================================================
# 6. FULL DEPLOYMENT
# ================================================================
full_deploy() {
    print_step "Starting full AWS deployment..."
    
    # Check AWS credentials
    if ! aws sts get-caller-identity > /dev/null 2>&1; then
        print_error "AWS credentials not configured"
        exit 1
    fi
    
    print_success "AWS credentials valid"
    
    # Deploy components
    deploy_frontend
    deploy_backend
    setup_api_gateway
    
    print_success "Deployment complete!"
    echo ""
    echo "Next steps:"
    echo "1. Configure API Gateway in AWS Console"
    echo "2. Set up CloudFront distribution"
    echo "3. Run tests against deployed endpoints"
}

# ================================================================
# EXPORT CURRENT LOCAL DATA FOR BACKUP
# ================================================================
export_local_data() {
    print_step "Exporting local database..."
    
    OUTPUT="/home/stocks/algo/aws_data_dump_$(date +%Y%m%d_%H%M%S).sql"
    
    pg_dump \
        -h localhost \
        -U postgres \
        -d stocks \
        --no-owner \
        --no-privileges \
        > $OUTPUT
    
    # Compress
    gzip $OUTPUT
    
    print_success "Data exported to: ${OUTPUT}.gz"
    ls -lh ${OUTPUT}.gz
}

# ================================================================
# VERIFY DEPLOYMENT
# ================================================================
verify_deployment() {
    print_step "Verifying deployment..."
    
    # Check Lambda function
    if aws lambda get-function --function-name stocks-api > /dev/null 2>&1; then
        print_success "Lambda function online"
    else
        print_error "Lambda function not found"
    fi
    
    # Check RDS
    if [ ! -z "$POSTGRES_HOST" ]; then
        if pg_isready -h $POSTGRES_HOST -U postgres > /dev/null 2>&1; then
            print_success "RDS database accessible"
        else
            print_error "RDS database not accessible"
        fi
    fi
    
    # Check S3
    if aws s3 ls s3://stocks-dashboard-${AWS_ACCOUNT_ID}/ > /dev/null 2>&1; then
        print_success "S3 bucket accessible"
    else
        print_error "S3 bucket not found"
    fi
}

# ================================================================
# HELP
# ================================================================
show_help() {
    cat <<HELP
AWS Deployment Helper

Usage: $0 <command>

Commands:
    deploy-frontend    Deploy React frontend to S3 + CloudFront
    deploy-backend     Deploy Lambda API backend
    setup-rds          Create RDS PostgreSQL instance
    import-data        Import local data to RDS
    setup-api          Configure API Gateway
    full-deploy        Complete deployment (all steps)
    export-local       Export current local database
    verify             Verify deployment health
    help              Show this help message

Environment Variables Required:
    AWS_ACCOUNT_ID          Your AWS account ID
    POSTGRES_PASSWORD       Database password
    CLOUDFRONT_DISTRIBUTION_ID  (optional) for cache invalidation

Example:
    export AWS_ACCOUNT_ID=123456789012
    export POSTGRES_PASSWORD=SecurePassword123
    $0 full-deploy

HELP
}

# ================================================================
# MAIN
# ================================================================
case "${1:-help}" in
    deploy-frontend) deploy_frontend ;;
    deploy-backend) deploy_backend ;;
    setup-rds) setup_rds ;;
    import-data) import_data ;;
    setup-api) setup_api_gateway ;;
    full-deploy) full_deploy ;;
    export-local) export_local_data ;;
    verify) verify_deployment ;;
    help|--help|-h) show_help ;;
    *) print_error "Unknown command: $1"; show_help; exit 1 ;;
esac

