#!/bin/bash

# Terraform Deployment - Ready to Run
# All AWS cleanup completed, ready for fresh infrastructure deployment

set -e

echo "=========================================="
echo "Terraform Fresh Deployment"
echo "=========================================="
echo ""

cd terraform

# ============================================================
# STEP 1: Clean previous terraform state
# ============================================================
echo "STEP 1: Cleaning previous terraform state..."
rm -rf .terraform/
rm -f .terraform.lock.hcl
rm -f tfplan
echo "✓ Clean"

echo ""

# ============================================================
# STEP 2: Initialize terraform
# ============================================================
echo "STEP 2: Initializing terraform..."
terraform init
echo "✓ Initialized"

echo ""

# ============================================================
# STEP 3: Validate configuration
# ============================================================
echo "STEP 3: Validating configuration..."
terraform validate
echo "✓ Configuration valid"

echo ""

# ============================================================
# STEP 4: Generate plan
# ============================================================
echo "STEP 4: Generating terraform plan..."
terraform plan -out=tfplan
echo ""
echo "Review the plan above carefully:"
echo "  - Should show ~210 resources to ADD"
echo "  - Should show 0 resources to CHANGE"
echo "  - Should show 0 resources to DESTROY"
echo ""

echo ""

# ============================================================
# STEP 5: Deploy
# ============================================================
echo "STEP 5: Deploying infrastructure..."
echo "This will take 15-20 minutes..."
echo ""

terraform apply tfplan

echo ""
echo "=========================================="
echo "✓ DEPLOYMENT COMPLETE"
echo "=========================================="
echo ""
echo "Infrastructure created successfully!"
echo ""
echo "Next steps:"
echo "  1. Check AWS Console to verify resources"
echo "  2. Upload Lambda code to replace placeholders"
echo "  3. Initialize RDS database schema"
echo "  4. Upload frontend assets to S3"
echo "  5. Test API endpoints"
echo ""

# Save outputs
echo "Saving deployment outputs..."
terraform output -json > deployment_outputs.json
echo "✓ Outputs saved to: deployment_outputs.json"

echo ""
echo "Key outputs:"
terraform output -json | grep -E "api_gateway_endpoint|rds_endpoint|frontend_bucket" || echo "(See deployment_outputs.json for full details)"

echo ""
echo "Ready to continue with post-deployment setup!"
