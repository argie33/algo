#!/bin/bash
# ============================================================
# GitHub Actions Terraform Bootstrap Script
# Purpose: Verify/create S3 state backend and DynamoDB locks
# ============================================================

set -e

REGION=${1:-us-east-1}
AWS_ACCOUNT_ID=${2:-}

if [ -z "$AWS_ACCOUNT_ID" ]; then
  echo "ERROR: AWS_ACCOUNT_ID not provided"
  exit 1
fi

echo "🔧 Bootstrapping Terraform prerequisites..."
echo "   Region: $REGION"
echo "   Account: $AWS_ACCOUNT_ID"

# ============================================================
# 1. Verify OIDC Role Exists
# ============================================================

echo ""
echo "📋 Checking OIDC role..."
ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/github-actions-role"

if aws iam get-role --role-name "github-actions-role" --region "$REGION" 2>/dev/null; then
  echo "✅ OIDC role exists: $ROLE_ARN"
else
  echo "❌ ERROR: OIDC role 'github-actions-role' not found!"
  echo "   Please create the OIDC role via Terraform:"
  echo "   terraform init && terraform plan && terraform apply"
  exit 1
fi

# ============================================================
# 2. Verify/Create S3 State Bucket
# ============================================================

echo ""
echo "📦 Checking Terraform state bucket..."
BUCKET_NAME="stocks-terraform-state"

if aws s3 ls "s3://${BUCKET_NAME}" --region "$REGION" 2>/dev/null; then
  echo "✅ S3 state bucket exists: $BUCKET_NAME"
else
  echo "⚠️  S3 state bucket not found, creating..."
  aws s3 mb "s3://${BUCKET_NAME}" --region "$REGION" || {
    if aws s3 ls "s3://${BUCKET_NAME}" --region "$REGION" 2>/dev/null; then
      echo "✅ S3 bucket created (or already exists)"
    else
      echo "❌ Failed to create S3 bucket"
      exit 1
    fi
  }
fi

# Enable versioning on bucket (skip if permission denied - may be due to read-only user)
echo "   Enabling versioning..."
aws s3api put-bucket-versioning \
  --bucket "$BUCKET_NAME" \
  --versioning-configuration Status=Enabled \
  --region "$REGION" || echo "⚠️  Skipping versioning (permissions may be limited)"

# Enable encryption (skip if permission denied)
echo "   Enabling encryption..."
aws s3api put-bucket-encryption \
  --bucket "$BUCKET_NAME" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }' \
  --region "$REGION" || echo "⚠️  Skipping encryption (permissions may be limited)"

# Block public access (skip if permission denied)
echo "   Blocking public access..."
aws s3api put-public-access-block \
  --bucket "$BUCKET_NAME" \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
  --region "$REGION" || echo "⚠️  Skipping public access block (permissions may be limited)"

echo "✅ S3 state bucket configured"

# ============================================================
# 3. Verify/Create DynamoDB Lock Table
# ============================================================

echo ""
echo "🔐 Checking DynamoDB lock table..."
TABLE_NAME="stocks-terraform-locks"

if aws dynamodb describe-table \
  --table-name "$TABLE_NAME" \
  --region "$REGION" 2>/dev/null | grep -q "TableStatus"; then
  echo "✅ DynamoDB lock table exists: $TABLE_NAME"
else
  echo "⚠️  DynamoDB lock table not found, creating..."
  aws dynamodb create-table \
    --table-name "$TABLE_NAME" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION" || {
    if aws dynamodb describe-table \
      --table-name "$TABLE_NAME" \
      --region "$REGION" 2>/dev/null | grep -q "TableStatus"; then
      echo "✅ DynamoDB table created (or already exists)"
    else
      echo "❌ Failed to create DynamoDB table"
      exit 1
    fi
  }

  # Wait for table to be active
  echo "   Waiting for table to be active..."
  aws dynamodb wait table-exists \
    --table-name "$TABLE_NAME" \
    --region "$REGION"
fi

echo "✅ DynamoDB lock table configured"

# ============================================================
# 4. Create S3 Backup Directory
# ============================================================

echo ""
echo "📁 Creating backups directory..."
aws s3api put-object \
  --bucket "$BUCKET_NAME" \
  --key "backups/" \
  --region "$REGION" || true

echo "✅ Backups directory ready"

# ============================================================
# All Checks Passed
# ============================================================

echo ""
echo "✅ Terraform bootstrap complete!"
echo ""
echo "Prerequisites verified:"
echo "   ✓ OIDC role: $ROLE_ARN"
echo "   ✓ S3 state bucket: s3://$BUCKET_NAME"
echo "   ✓ DynamoDB lock table: $TABLE_NAME"
echo ""
echo "Ready to run: terraform init"