#!/bin/bash
# =============================================================================
# Setup Staging Infrastructure (Isolated RDS)
# =============================================================================
# FIXED F-07: Creates separate staging RDS instance (algo-db-staging)
# instead of sharing dev RDS. Prevents data corruption on dev from staging
# migrations or broken DDL.
#
# Usage:
#   ./scripts/setup-staging-infrastructure.sh
#
# Prerequisites:
#   - AWS credentials configured locally (or OIDC role assumed)
#   - Terraform initialized locally
#   - terraform/terraform.staging.tfvars exists
#
# What it does:
#   1. Create terraform workspace 'staging'
#   2. Apply full infrastructure (VPC, RDS, Lambda, etc.) for staging
#   3. Output staging RDS endpoint
#   4. Next deploy-staging.yml will auto-detect staging RDS and use it
#
# Cost: ~$12/month for t4g.micro RDS staging instance (same as dev)
# =============================================================================

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
TERRAFORM_DIR="$REPO_ROOT/terraform"
STATE_BUCKET="algo-tf-state"  # Update if different
AWS_REGION="us-east-1"

echo "[F-07] Setting up staging infrastructure (isolated RDS)..."
echo ""

# Check prerequisites
if ! command -v terraform &> /dev/null; then
  echo "❌ Terraform not found. Install Terraform and try again."
  exit 1
fi

if [ ! -f "$TERRAFORM_DIR/terraform.staging.tfvars" ]; then
  echo "❌ terraform/terraform.staging.tfvars not found."
  exit 1
fi

if [ ! -f "$TERRAFORM_DIR/main.tf" ]; then
  echo "❌ terraform/main.tf not found."
  exit 1
fi

# Initialize terraform if not already done
cd "$TERRAFORM_DIR"
if [ ! -d ".terraform" ]; then
  echo "[1/5] Initializing terraform..."
  terraform init \
    -backend-config="key=stocks/terraform.tfstate" \
    -backend-config="bucket=$STATE_BUCKET" \
    -backend-config="region=$AWS_REGION"
fi

# Create staging workspace
echo "[2/5] Creating terraform workspace 'staging'..."
terraform workspace new staging 2>/dev/null || terraform workspace select staging
echo "      Workspace: $(terraform workspace show)"

# Plan infrastructure
echo "[3/5] Planning staging infrastructure..."
terraform plan \
  -var-file=terraform.staging.tfvars \
  -out=tfplan_staging \
  -no-color

# Ask for confirmation
echo ""
echo "⚠️  This will create:"
echo "   - Separate VPC for staging (or reuse dev VPC if vars allow)"
echo "   - Separate RDS instance: algo-db-staging (t4g.micro, ~$12/month)"
echo "   - Separate Lambda functions: algo-algo-staging, algo-api-staging"
echo "   - Separate ECS/Fargate for staging loaders"
echo ""
read -p "Continue with terraform apply? (yes/no) " -r
if [[ ! $REPLY =~ ^[yY]$ ]]; then
  echo "Cancelled."
  rm -f tfplan_staging
  exit 0
fi

# Apply infrastructure
echo "[4/5] Applying staging infrastructure..."
terraform apply \
  tfplan_staging \
  -no-color

rm -f tfplan_staging

# Output staging RDS endpoint
echo "[5/5] Staging infrastructure ready."
echo ""
echo "========================================="
echo "✅ STAGING INFRASTRUCTURE READY"
echo "========================================="
echo ""

STAGING_RDS=$(terraform output -raw rds_address 2>/dev/null || echo "")
if [ -z "$STAGING_RDS" ]; then
  echo "⚠️  Could not retrieve staging RDS endpoint."
  echo "    Switch to staging workspace to check:"
  echo "    terraform workspace select staging"
  echo "    terraform output rds_address"
else
  echo "Staging RDS endpoint: $STAGING_RDS"
  echo ""
  echo "Next steps:"
  echo "1. Push to 'staging' branch to deploy Lambda functions"
  echo "2. deploy-staging.yml will auto-detect algo-db-staging and use it"
  echo "3. Staging is now isolated — migrations won't touch production data"
  echo ""
  echo "To switch back to dev (default workspace):"
  echo "  terraform workspace select default"
fi

echo ""
echo "Ongoing costs:"
echo "  - RDS (algo-db-staging): ~$12/month"
echo "  - RDS Proxy (optional): ~$11/month"
echo "  - ECS/Fargate for loaders: same as dev"
echo ""
echo "To save costs later, delete staging infrastructure:"
echo "  terraform workspace select staging"
echo "  terraform destroy -var-file=terraform.staging.tfvars"
echo "  terraform workspace select default"
echo "  terraform workspace delete staging"
