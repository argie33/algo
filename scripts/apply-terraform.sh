#!/bin/bash
# Deploy Terraform changes to fix Step Functions

set -e

cd terraform

echo "=========================================="
echo "DEPLOYING TERRAFORM CHANGES"
echo "=========================================="
echo ""

echo "[1/3] Initializing Terraform..."
terraform init -upgrade \
  -backend-config="bucket=stocks-terraform-state" \
  -backend-config="key=algo/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="encrypt=true"
echo "✓ Terraform initialized"
echo ""

echo "[2/3] Planning changes..."
terraform plan -var-file=terraform.tfvars -out=tfplan
echo "✓ Plan complete"
echo ""

echo "[3/3] Applying changes..."
terraform apply tfplan
echo "✓ Terraform applied successfully"
echo ""

echo "=========================================="
echo "DEPLOYMENT COMPLETE"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Wait 1-2 minutes for AWS to process changes"
echo "2. Trigger Step Functions manually:"
echo ""
echo "   aws stepfunctions start-execution \\"
echo "     --state-machine-arn arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev \\"
echo "     --name test-run-\$(date +%s) \\"
echo "     --region us-east-1 \\"
echo "     --profile algo-developer"
echo ""
echo "3. Monitor the execution:"
echo "   aws stepfunctions describe-execution --execution-arn <ARN> --region us-east-1 --profile algo-developer"
echo ""
