#!/bin/bash
# ============================================================
# Bootstrap OIDC Provider and GitHub Actions Role
# ============================================================
# This script ensures the prerequisites exist for Terraform:
# 1. GitHub OIDC Provider (for GitHub Actions → AWS authentication)
# 2. github-actions-role (IAM role assumed by GitHub Actions)
# 3. S3 Terraform state bucket with DynamoDB lock table

set -e

AWS_REGION="${1:-us-east-1}"
AWS_ACCOUNT_ID="${2:-}"

echo "════════════════════════════════════════════════════════"
echo "🔧 Bootstrap: Setting up AWS prerequisites"
echo "════════════════════════════════════════════════════════"
echo "AWS Region: $AWS_REGION"
echo "AWS Account ID: $AWS_ACCOUNT_ID"
echo ""

# ============================================================
# 1. Create GitHub OIDC Provider
# ============================================================
echo "1️⃣  OIDC Provider"

# List all providers
EXISTING=$(aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList" --output json)

# Check if GitHub OIDC provider exists
OIDC_ARN=$(echo "$EXISTING" | grep -o "arn:aws:iam::[0-9]*:oidc-provider/token.actions.githubusercontent.com" || true)

if [ -z "$OIDC_ARN" ]; then
  echo "   Creating GitHub OIDC Provider..."

  # Create the OIDC provider and capture the ARN from the response
  CREATE_RESPONSE=$(aws iam create-open-id-connect-provider \
    --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 1b511abead59c6ce207077c0bf4113469e1f0b03 \
    --output json)

  OIDC_ARN=$(echo "$CREATE_RESPONSE" | grep -o "arn:aws:iam::[0-9]*:oidc-provider/token.actions.githubusercontent.com")

  if [ -z "$OIDC_ARN" ]; then
    echo "   Error: Could not create OIDC provider"
    echo "$CREATE_RESPONSE"
    exit 1
  fi

  echo "   ✅ Created: $OIDC_ARN"
  sleep 2
else
  echo "   ✅ Already exists: $OIDC_ARN"
fi

echo "   Using OIDC ARN: $OIDC_ARN"

# ============================================================
# 2. Create GitHub Actions IAM Role
# ============================================================
echo ""
echo "2️⃣  GitHub Actions Role"

if aws iam get-role --role-name github-actions-role 2>/dev/null >/dev/null; then
  echo "   ✅ Already exists"
else
  echo "   Creating github-actions-role..."

  # Create trust policy JSON
  TRUST_POLICY=$(cat <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "OIDC_ARN_PLACEHOLDER"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:argie33/algo:*"
        }
      }
    }
  ]
}
EOF
)

  # Replace placeholder with actual ARN
  TRUST_POLICY="${TRUST_POLICY//OIDC_ARN_PLACEHOLDER/$OIDC_ARN}"
  echo "$TRUST_POLICY" > /tmp/trust-policy.json

  aws iam create-role \
    --role-name github-actions-role \
    --assume-role-policy-document file:///tmp/trust-policy.json \
    --region "$AWS_REGION" 2>/dev/null || true

  sleep 1

  # Attach Terraform permissions
  TERRAFORM_POLICY=$(cat <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iam:*",
        "ec2:*",
        "rds:*",
        "ecs:*",
        "ecr:*",
        "lambda:*",
        "apigateway:*",
        "cloudfront:*",
        "cognito-idp:*",
        "s3:*",
        "dynamodb:*",
        "secretsmanager:*",
        "cloudwatch:*",
        "logs:*",
        "events:*",
        "scheduler:*",
        "sns:*",
        "kms:*",
        "cloudformation:*",
        "autoscaling:*"
      ],
      "Resource": "*"
    }
  ]
}
EOF
)

  echo "$TERRAFORM_POLICY" > /tmp/terraform-policy.json

  aws iam put-role-policy \
    --role-name github-actions-role \
    --policy-name terraform-deployment \
    --policy-document file:///tmp/terraform-policy.json \
    --region "$AWS_REGION"

  echo "   ✅ Created with Terraform permissions"
fi

# ============================================================
# 3. Create S3 Terraform State Bucket
# ============================================================
echo ""
echo "3️⃣  S3 State Bucket"

if aws s3 ls s3://stocks-terraform-state --region "$AWS_REGION" 2>/dev/null >/dev/null; then
  echo "   ✅ Already exists"
else
  echo "   Creating S3 bucket..."
  aws s3 mb s3://stocks-terraform-state \
    --region "$AWS_REGION"

  # Enable versioning for safety
  aws s3api put-bucket-versioning \
    --bucket stocks-terraform-state \
    --versioning-configuration Status=Enabled \
    --region "$AWS_REGION"

  echo "   ✅ Created with versioning enabled"
fi

# ============================================================
# 4. Create DynamoDB Lock Table
# ============================================================
echo ""
echo "4️⃣  DynamoDB Lock Table"

if aws dynamodb describe-table \
   --table-name stocks-terraform-locks \
   --region "$AWS_REGION" 2>/dev/null >/dev/null; then
  echo "   ✅ Already exists"
else
  echo "   Creating DynamoDB table..."
  aws dynamodb create-table \
    --table-name stocks-terraform-locks \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$AWS_REGION"

  # Wait for table to be created
  echo "   Waiting for table to become active..."
  aws dynamodb wait table-exists \
    --table-name stocks-terraform-locks \
    --region "$AWS_REGION"

  echo "   ✅ Created and active"
fi

# ============================================================
# Summary
# ============================================================
echo ""
echo "════════════════════════════════════════════════════════"
echo "✅ Bootstrap Complete!"
echo "════════════════════════════════════════════════════════"
echo ""
echo "Ready for Terraform deployment:"
echo "  - OIDC Provider: $OIDC_ARN"
echo "  - GitHub Actions Role: arn:aws:iam::$AWS_ACCOUNT_ID:role/github-actions-role"
echo "  - S3 State Bucket: stocks-terraform-state"
echo "  - DynamoDB Lock Table: stocks-terraform-locks"
echo ""
