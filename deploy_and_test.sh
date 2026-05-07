#!/bin/bash
set -e

echo "=========================================="
echo "STOCK ALGO - DEPLOYMENT & TEST HARNESS"
echo "=========================================="
echo

# Check prerequisites
echo "[1/5] Checking prerequisites..."
if ! command -v gh &> /dev/null; then
    echo "ERROR: GitHub CLI not found. Install with: brew install gh"
    exit 1
fi

if ! command -v aws &> /dev/null; then
    echo "ERROR: AWS CLI not found"
    exit 1
fi

echo "  OK: gh and aws CLI available"
echo

# Stage 1: Deploy infrastructure
echo "[2/5] Deploying CloudFormation stacks..."
echo "  Starting: deploy-core.yml (NAT Gateway, VPC, subnets)"
gh workflow run deploy-core.yml 2>&1 | grep -E "status|error|failed" || echo "  Deployment queued"

sleep 5

echo "  Starting: deploy-data-infrastructure.yml (RDS, ECS, Secrets)"
gh workflow run deploy-data-infrastructure.yml 2>&1 | grep -E "status|error|failed" || echo "  Deployment queued"

sleep 5

echo "  Starting: deploy-webapp.yml (Lambda API)"
gh workflow run deploy-webapp.yml 2>&1 | grep -E "status|error|failed" || echo "  Deployment queued"

sleep 5

echo "  Starting: deploy-algo.yml (Orchestrator Lambda)"
gh workflow run deploy-algo.yml 2>&1 | grep -E "status|error|failed" || echo "  Deployment queued"

echo "  [WAIT 15-20 minutes for stacks to complete...]"
echo

# Stage 2: Wait for deployments
echo "[3/5] Waiting for CloudFormation stacks (this takes ~20 min)..."
echo "  Monitor progress: gh workflow list"
echo

# Stage 3: Test connectivity
echo "[4/5] Basic connectivity tests (when stacks are ready)..."
echo "  TODO: Test Bastion -> RDS"
echo "  TODO: Test Lambda API endpoint"
echo

# Stage 4: Run orchestrator test
echo "[5/5] End-to-end orchestrator test..."
echo "  TODO: Trigger orchestrator in dry-run mode"
echo "  TODO: Check all 7 phases complete"
echo "  TODO: Verify data in RDS"
echo "  TODO: Check watermarks created"
echo

echo "=========================================="
echo "DEPLOYMENT STARTED"
echo "=========================================="
echo
echo "Next steps:"
echo "1. Monitor deployments: gh workflow list"
echo "2. When complete, run: python deploy_monitor.py"
echo "3. Review any errors and fix"
echo "4. Run orchestrator test when ready"
echo

