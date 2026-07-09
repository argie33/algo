#!/bin/bash

# Emergency deployment script for EventBridge orchestrator schedules
# This script deploys the full infrastructure via GitHub Actions
# Usage: bash scripts/deploy-infrastructure.sh

set -e

echo "=========================================="
echo "Algo System Deployment Script"
echo "=========================================="
echo ""
echo "This script will deploy the EventBridge Scheduler rules"
echo "that trigger the algo orchestrator Lambda function."
echo ""
echo "Prerequisites:"
echo "  - GitHub CLI (gh) installed and authenticated"
echo "  - Push access to argie33/algo repository"
echo ""

# Check for GitHub CLI
if ! command -v gh &> /dev/null; then
    echo "ERROR: GitHub CLI not found. Install it first:"
    echo "  brew install gh  # macOS"
    echo "  choco install gh # Windows"
    exit 1
fi

# Verify git is clean
echo "[1/4] Verifying git status..."
git status --short
if [ $? -ne 0 ]; then
    echo "ERROR: Git status check failed"
    exit 1
fi

if ! git diff-index --quiet HEAD --; then
    echo "ERROR: Uncommitted changes detected. Commit or stash them first:"
    echo "  git add -A && git commit -m 'Your message'"
    exit 1
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
    echo "ERROR: You must be on 'main' branch. Currently on: $BRANCH"
    exit 1
fi

echo "[OK] Repository clean and on main branch"
echo ""

# Get latest commit
COMMIT=$(git rev-parse --short HEAD)
echo "[2/4] Latest commit: $COMMIT"
echo ""

# Trigger deployment
echo "[3/4] Triggering GitHub Actions deployment..."
echo ""
gh workflow run deploy-all-infrastructure.yml \
  --ref main \
  -R argie33/algo

echo "[OK] Deployment workflow triggered"
echo ""

# Monitor the run
echo "[4/4] Waiting for workflow to start..."
sleep 5

# Get latest run
RUN_ID=$(gh run list -R argie33/algo --workflow deploy-all-infrastructure.yml --limit 1 --json databaseId --jq '.[] | .databaseId' 2>/dev/null | head -1)

if [ -z "$RUN_ID" ]; then
    echo "ERROR: Could not fetch workflow run ID"
    exit 1
fi

echo "[OK] Workflow run: $RUN_ID"
echo ""
echo "Monitor deployment progress:"
echo "  gh run view $RUN_ID --log -R argie33/algo"
echo ""
echo "Once deployment completes (15-20 min):"
echo "  aws scheduler list-schedules --region us-east-1"
echo ""
echo "Verify orchestrator Lambda deployed:"
echo "  aws lambda get-function --function-name algo-orchestrator-dev --region us-east-1"
