#!/bin/bash
# Automated System Deployment - Sets up GitHub Secrets and deploys to AWS

set -e

echo "==============================================="
echo "ALGO TRADING SYSTEM - AUTOMATED DEPLOYMENT"
echo "==============================================="
echo ""
echo "This script will:"
echo "1. Verify your Alpaca credentials"
echo "2. Set GitHub Secrets"
echo "3. Trigger deployment via GitHub Actions"
echo "4. Monitor deployment progress"
echo ""

# Step 1: Get Alpaca credentials
echo "[1] Enter your Alpaca Paper Trading Credentials"
echo "==========================================="
read -p "Enter your Alpaca API Key (pk_...): " ALPACA_KEY
read -sp "Enter your Alpaca API Secret: " ALPACA_SECRET
echo ""

if [ -z "$ALPACA_KEY" ] || [ -z "$ALPACA_SECRET" ]; then
    echo "ERROR: Credentials cannot be empty"
    exit 1
fi

echo "[OK] Credentials provided"
echo ""

# Step 2: Verify GitHub CLI is installed
echo "[2] Checking GitHub CLI..."
if ! command -v gh &> /dev/null; then
    echo "ERROR: GitHub CLI not found. Install from: https://cli.github.com"
    exit 1
fi
echo "[OK] GitHub CLI found"
echo ""

# Step 3: Verify git repository
echo "[3] Checking git repository..."
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "ERROR: Not in a git repository"
    exit 1
fi

REPO_NAME=$(git config --get remote.origin.url | sed 's/.*\///' | sed 's/\.git//')
REPO_OWNER=$(git config --get remote.origin.url | sed 's/.*:\|.*\///' | sed 's/\/.*//')
echo "[OK] Repository: $REPO_OWNER/$REPO_NAME"
echo ""

# Step 4: Set GitHub Secrets
echo "[4] Setting GitHub Secrets..."
echo "This will set:"
echo "  - ALPACA_API_KEY_ID"
echo "  - ALPACA_API_SECRET_KEY"
echo ""

gh secret set ALPACA_API_KEY_ID --body "$ALPACA_KEY" -R "$REPO_OWNER/$REPO_NAME"
echo "[OK] ALPACA_API_KEY_ID set"

gh secret set ALPACA_API_SECRET_KEY --body "$ALPACA_SECRET" -R "$REPO_OWNER/$REPO_NAME"
echo "[OK] ALPACA_API_SECRET_KEY set"
echo ""

# Step 5: Trigger deployment
echo "[5] Triggering deployment..."
git push origin main
echo "[OK] Push triggered - GitHub Actions will automatically deploy"
echo ""

# Step 6: Monitor deployment
echo "[6] Monitoring deployment progress..."
echo "Waiting for workflow to appear..."
sleep 5

# Get the latest workflow run
WORKFLOW_FILE="deploy-all-infrastructure.yml"
WORKFLOW_RUN=$(gh run list -R "$REPO_OWNER/$REPO_NAME" --workflow "$WORKFLOW_FILE" --limit 1 --json databaseId -q '.[0].databaseId')

if [ -z "$WORKFLOW_RUN" ]; then
    echo "[WARN] Could not find workflow run. Monitoring via:"
    echo "  https://github.com/$REPO_OWNER/$REPO_NAME/actions"
else
    echo "[OK] Monitoring run: $WORKFLOW_RUN"
    echo ""
    echo "Status:"

    # Watch the workflow
    while true; do
        STATUS=$(gh run view "$WORKFLOW_RUN" -R "$REPO_OWNER/$REPO_NAME" --json conclusion,status -q '.status // .conclusion // "pending"')

        case "$STATUS" in
            "completed")
                CONCLUSION=$(gh run view "$WORKFLOW_RUN" -R "$REPO_OWNER/$REPO_NAME" --json conclusion -q '.conclusion')
                if [ "$CONCLUSION" = "success" ]; then
                    echo "[OK] Deployment SUCCEEDED!"
                    break
                else
                    echo "[FAIL] Deployment failed. Check logs:"
                    echo "  https://github.com/$REPO_OWNER/$REPO_NAME/actions/runs/$WORKFLOW_RUN"
                    exit 1
                fi
                ;;
            "in_progress")
                echo "  [IN PROGRESS] Still deploying..."
                sleep 10
                ;;
            "queued")
                echo "  [QUEUED] Waiting to start..."
                sleep 5
                ;;
            *)
                echo "  [STATUS] $STATUS"
                sleep 10
                ;;
        esac
    done
fi

echo ""
echo "==============================================="
echo "DEPLOYMENT COMPLETE!"
echo "==============================================="
echo ""
echo "Next steps:"
echo "1. Verify AWS Secrets Manager:"
echo "   aws secretsmanager get-secret-value --secret-id algo/alpaca --region us-east-1"
echo ""
echo "2. Test orchestrator Lambda:"
echo "   aws lambda invoke --function-name algo-orchestrator-dev /tmp/out.json --region us-east-1"
echo ""
echo "3. Open dashboard:"
echo "   https://your-cloudfront-domain"
echo ""
echo "4. Wait for orchestrator to run (next scheduled time)"
echo ""
echo "System is now LIVE for paper trading!"
echo ""
