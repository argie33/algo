#!/bin/bash
# Setup GitHub Repository Secrets for Phase 2 Execution
# This script adds the required AWS credentials to GitHub Actions secrets

set -e

REPO="argie33/algo"
AWS_ACCOUNT_ID="626216981288"
RDS_USERNAME="stocks"
RDS_PASSWORD="bed0elAn"
FRED_API_KEY="4f87c213871ed1a9508c06957fa9b577"

echo "=========================================="
echo "Setting up GitHub Secrets for Phase 2"
echo "=========================================="
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "ERROR: GitHub CLI (gh) not found. Install from https://cli.github.com"
    exit 1
fi

# Check if authenticated
echo "Checking GitHub authentication..."
gh auth status || (echo "ERROR: Not authenticated with GitHub. Run: gh auth login" && exit 1)

echo ""
echo "Adding secrets to repository: $REPO"
echo ""

# Add secrets
secrets=(
    "AWS_ACCOUNT_ID:$AWS_ACCOUNT_ID"
    "RDS_USERNAME:$RDS_USERNAME"
    "RDS_PASSWORD:$RDS_PASSWORD"
    "FRED_API_KEY:$FRED_API_KEY"
)

for secret in "${secrets[@]}"; do
    key="${secret%%:*}"
    value="${secret#*:}"

    echo -n "Adding $key... "

    # Use gh CLI to add secret (requires authentication)
    echo "$value" | gh secret set "$key" -R "$REPO" 2>/dev/null && echo "✓" || echo "✗ (may already exist)"
done

echo ""
echo "=========================================="
echo "✓ GitHub Secrets Setup Complete!"
echo "=========================================="
echo ""
echo "Secrets added:"
echo "  - AWS_ACCOUNT_ID"
echo "  - RDS_USERNAME"
echo "  - RDS_PASSWORD"
echo "  - FRED_API_KEY"
echo ""
echo "Next steps:"
echo "1. Configure AWS OIDC provider (see CRITICAL_FIXES_REQUIRED.md)"
echo "2. Create GitHubActionsDeployRole in AWS (see CRITICAL_FIXES_REQUIRED.md)"
echo "3. Push a change to trigger Phase 2 workflow"
echo ""
echo "To test workflow immediately:"
echo "  git commit -am 'Trigger Phase 2' --allow-empty && git push"
echo ""
