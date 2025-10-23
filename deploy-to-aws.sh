#!/bin/bash

##############################################
# AWS Deployment Script for Stock Analysis
##############################################

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION="us-east-1"
DB_INSTANCE_ID="stocks-db"
DB_CLASS="db.t3.medium"
DB_STORAGE="500"
APP_NAME="stocks-algo"
TIMESTAMP=$(date +%s)

# Functions
print_step() {
    echo -e "${BLUE}==== $1 ====${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_aws_credentials() {
    print_step "Checking AWS Credentials"

    if ! aws sts get-caller-identity > /dev/null 2>&1; then
        print_error "AWS credentials not configured"
        exit 1
    fi

    USER_ARN=$(aws sts get-caller-identity --query 'Arn' --output text)
    print_success "AWS credentials valid: $USER_ARN"

    # Check if user has adequate permissions (not just "reader")
    if echo "$USER_ARN" | grep -q "reader"; then
        print_error "Your AWS account has 'reader' permissions only"
        print_error "You need elevated permissions to deploy to AWS"
        print_error "Contact your AWS administrator for deployment permissions"
        exit 1
    fi
}

create_rds_instance() {
    print_step "Creating RDS PostgreSQL Instance"

    # Check if instance already exists
    if aws rds describe-db-instances --db-instance-identifier $DB_INSTANCE_ID --region $AWS_REGION > /dev/null 2>&1; then
        print_success "RDS instance already exists: $DB_INSTANCE_ID"
        return
    fi

    # Prompt for master password
    read -sp "Enter RDS master password: " DB_PASSWORD
    echo

    # Create RDS instance
    aws rds create-db-instance \
        --db-instance-identifier $DB_INSTANCE_ID \
        --db-instance-class $DB_CLASS \
        --engine postgres \
        --engine-version 16.1 \
        --master-username postgres \
        --master-user-password "$DB_PASSWORD" \
        --allocated-storage $DB_STORAGE \
        --storage-type gp3 \
        --publicly-accessible true \
        --region $AWS_REGION

    print_success "RDS instance creation initiated"
    print_step "Waiting for RDS instance to be available (this takes 10-15 minutes)..."

    # Wait for instance to be available
    aws rds wait db-instance-available \
        --db-instance-identifier $DB_INSTANCE_ID \
        --region $AWS_REGION

    print_success "RDS instance is now available"
}

get_rds_endpoint() {
    print_step "Retrieving RDS Endpoint"

    RDS_ENDPOINT=$(aws rds describe-db-instances \
        --db-instance-identifier $DB_INSTANCE_ID \
        --region $AWS_REGION \
        --query 'DBInstances[0].Endpoint.Address' \
        --output text)

    print_success "RDS Endpoint: $RDS_ENDPOINT"
    echo $RDS_ENDPOINT
}

create_s3_buckets() {
    print_step "Creating S3 Buckets"

    BACKUP_BUCKET="${APP_NAME}-backups-${TIMESTAMP}"
    FRONTEND_BUCKET="${APP_NAME}-frontend-${TIMESTAMP}"

    # Create backup bucket
    aws s3 mb s3://$BACKUP_BUCKET --region $AWS_REGION
    print_success "Created backup bucket: $BACKUP_BUCKET"

    # Create frontend bucket
    aws s3 mb s3://$FRONTEND_BUCKET --region $AWS_REGION
    print_success "Created frontend bucket: $FRONTEND_BUCKET"

    # Enable versioning for backup bucket
    aws s3api put-bucket-versioning \
        --bucket $BACKUP_BUCKET \
        --versioning-configuration Status=Enabled

    echo $FRONTEND_BUCKET
}

upload_database_dump() {
    print_step "Uploading Database Dump to S3"

    DUMP_FILE="/tmp/stocks_database.sql"

    if [ ! -f "$DUMP_FILE" ]; then
        print_error "Database dump not found at $DUMP_FILE"
        print_error "Run: pg_dump -h localhost -U postgres -d stocks > $DUMP_FILE"
        exit 1
    fi

    DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
    print_step "Uploading $DUMP_SIZE database dump..."

    aws s3 cp "$DUMP_FILE" s3://$BACKUP_BUCKET/ \
        --storage-class STANDARD_IA

    print_success "Database dump uploaded"
}

restore_database() {
    print_step "Restoring Database to RDS"

    RDS_ENDPOINT=$1
    DB_PASSWORD=$2

    # Create database
    print_step "Creating stocks database..."
    psql -h $RDS_ENDPOINT -U postgres -d postgres -c "CREATE DATABASE stocks;" || true

    # Restore dump (this will take time)
    print_step "Restoring data (this may take 30+ minutes)..."
    psql -h $RDS_ENDPOINT -U postgres -d stocks < /tmp/stocks_database.sql

    print_success "Database restored successfully"
}

build_frontend() {
    print_step "Building Frontend for Production"

    cd /home/stocks/algo/webapp/frontend

    if [ ! -d "node_modules" ]; then
        npm install
    fi

    npm run build
    print_success "Frontend built successfully"
}

deploy_frontend_to_s3() {
    print_step "Deploying Frontend to S3"

    FRONTEND_BUCKET=$1

    aws s3 sync /home/stocks/algo/webapp/frontend/dist/ \
        s3://$FRONTEND_BUCKET/ \
        --delete

    # Enable website hosting
    aws s3 website s3://$FRONTEND_BUCKET/ \
        --index-document index.html \
        --error-document index.html

    # Make files public
    aws s3api put-bucket-policy --bucket $FRONTEND_BUCKET --policy '{
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "PublicRead",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::'$FRONTEND_BUCKET'/*"
        }]
    }'

    FRONTEND_URL="http://${FRONTEND_BUCKET}.s3-website-${AWS_REGION}.amazonaws.com"
    print_success "Frontend deployed to: $FRONTEND_URL"
}

create_deployment_summary() {
    print_step "Deployment Summary"

    echo "============================================"
    echo "AWS Deployment Complete!"
    echo "============================================"
    echo ""
    echo "Database:"
    echo "  RDS Endpoint: $1"
    echo "  Database: stocks"
    echo "  User: postgres"
    echo ""
    echo "Frontend:"
    echo "  S3 Bucket: $2"
    echo "  URL: http://${2}.s3-website-${AWS_REGION}.amazonaws.com"
    echo ""
    echo "Next Steps:"
    echo "1. Update environment variables in Lambda/EC2 to use RDS endpoint"
    echo "2. Deploy backend to Lambda or EC2"
    echo "3. Update frontend API URL to point to backend"
    echo "4. Test all endpoints"
    echo ""
    echo "To access database:"
    echo "  psql -h $1 -U postgres -d stocks"
    echo ""
    echo "============================================"
}

# Main execution
main() {
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║  AWS Deployment - Stock Analysis App   ║"
    echo "╚════════════════════════════════════════╝"
    echo ""

    check_aws_credentials

    create_rds_instance
    RDS_ENDPOINT=$(get_rds_endpoint)

    FRONTEND_BUCKET=$(create_s3_buckets)

    upload_database_dump

    # Note: Database restoration requires database credentials
    # This is done manually due to complexity of password handling
    read -p "Press Enter after manually restoring the database to RDS..."

    build_frontend
    deploy_frontend_to_s3 $FRONTEND_BUCKET

    create_deployment_summary "$RDS_ENDPOINT" "$FRONTEND_BUCKET"
}

# Run main function
main "$@"
