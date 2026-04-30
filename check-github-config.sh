#!/bin/bash

echo "GitHub Actions Configuration Audit"
echo "==================================="
echo ""
echo "Required GitHub Secrets:"
echo "  - AWS_ACCOUNT_ID: (for OIDC role assumption)"
echo "  - AWS_ROLE_ARN: (for OIDC role assumption)"  
echo "  - RDS_USERNAME: (database credentials)"
echo "  - RDS_PASSWORD: (database credentials)"
echo "  - FRED_API_KEY: (optional, for economic data)"
echo "  - IBKR_USERNAME: (optional, for trading data)"
echo "  - IBKR_PASSWORD: (optional, for trading data)"
echo ""

echo "Current environment (.env.local):"
grep "AWS_ACCOUNT_ID\|AWS_ACCESS_KEY\|AWS_SECRET" .env.local || echo "  Not found"

echo ""
echo "Workflow file checks:"
grep "secrets\." .github/workflows/deploy-app-stocks.yml | grep -o "secrets\.[A-Z_]*" | sort | uniq

echo ""
echo "AWS Configuration Required:"
echo "  1. Create OIDC provider in AWS"
echo "  2. Create GitHubActionsDeployRole with OIDC trust"
echo "  3. Set GitHub secrets: AWS_ACCOUNT_ID, RDS_USERNAME, RDS_PASSWORD, FRED_API_KEY"
echo ""
echo "Until these are configured, the workflow CANNOT succeed"

