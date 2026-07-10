#!/bin/bash
# Deploy remaining infrastructure fix for orchestrator scheduler
# Run this after AWS credentials are refreshed

set -e

echo "=================================="
echo "Deploy Remaining Fixes"
echo "=================================="
echo ""
echo "Prerequisites:"
echo "1. AWS credentials must be fresh: scripts/refresh-aws-credentials.ps1"
echo "2. Terraform state must be current"
echo ""

# Step 1: Refresh AWS credentials
echo "[1/3] Refreshing AWS credentials..."
if command -v pwsh &> /dev/null; then
    pwsh -NoProfile -ExecutionPolicy Bypass -File "$(pwd)/scripts/refresh-aws-credentials.ps1" || {
        echo "ERROR: Failed to refresh AWS credentials"
        echo "Run manually: scripts/refresh-aws-credentials.ps1"
        exit 1
    }
else
    echo "PowerShell not found. Run manually: scripts/refresh-aws-credentials.ps1"
    read -p "Press enter after running AWS credential refresh..."
fi

# Step 2: Validate Terraform
echo "[2/3] Validating Terraform configuration..."
cd terraform
terraform validate || {
    echo "ERROR: Terraform validation failed"
    exit 1
}

# Step 3: Deploy infrastructure
echo "[3/3] Deploying EventBridge orchestrator scheduler..."
terraform apply -lock=false -auto-approve || {
    echo "WARNING: Terraform apply encountered issues"
    echo "Review errors above and retry: terraform apply -lock=false"
    exit 1
}

echo ""
echo "=================================="
echo "Deployment Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Verify orchestrator is executing:"
echo "   python3 scripts/trigger_orchestrator.py --run morning --mode paper"
echo ""
echo "2. Check orchestrator status in database:"
echo "   SELECT COUNT(*), MAX(started_at) FROM algo_orchestrator_runs"
echo "   WHERE started_at > NOW() - INTERVAL '1 hour';"
echo ""
echo "Expected: 2x daily orchestrator runs (9:30 AM + 5:30 PM ET)"
echo ""
