#!/bin/bash
# Fix GitHub Actions OIDC Trust Policy
# Run locally with: bash scripts/fix-oidc-trust-policy.sh
# Requires: AWS CLI configured with valid credentials

set -e

ROLE_NAME="algo-svc-github-actions-dev"
GITHUB_ORG="argie33"
GITHUB_REPO="algo"

echo "🔧 Fixing GitHub Actions OIDC Trust Policy"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 1: Get current trust policy
echo "📋 Step 1: Fetching current trust policy..."
CURRENT_POLICY=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.AssumeRolePolicyDocument' --output json)

echo "✅ Retrieved trust policy"
echo ""

# Step 2: Create new trust policy with OIDC support
echo "🔐 Step 2: Creating updated trust policy with GitHub OIDC..."

NEW_POLICY=$(cat << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:GITHUB_ORG/GITHUB_REPO:ref:refs/heads/main"
        }
      }
    }
  ]
}
EOF
)

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
echo "Account ID: $ACCOUNT_ID"

# Replace placeholders
NEW_POLICY="${NEW_POLICY//ACCOUNT_ID/$ACCOUNT_ID}"
NEW_POLICY="${NEW_POLICY//GITHUB_ORG/$GITHUB_ORG}"
NEW_POLICY="${NEW_POLICY//GITHUB_REPO/$GITHUB_REPO}"

echo "✅ Created new trust policy"
echo ""

# Step 3: Update the role
echo "🚀 Step 3: Updating role trust policy..."

aws iam update-assume-role-policy-document \
  --role-name "$ROLE_NAME" \
  --policy-document "$NEW_POLICY"

echo "✅ Updated trust policy"
echo ""

# Step 4: Verify
echo "✔️  Step 4: Verifying changes..."
UPDATED_POLICY=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.AssumeRolePolicyDocument' --output json)

if echo "$UPDATED_POLICY" | jq -e '.Statement[0].Principal.Federated | contains("oidc-provider")' > /dev/null; then
  echo "✅ OIDC provider configured correctly"
else
  echo "❌ OIDC provider not found in policy"
  exit 1
fi

if echo "$UPDATED_POLICY" | jq -e '.Statement[0].Condition.StringLike."token.actions.githubusercontent.com:sub" | contains("main")' > /dev/null; then
  echo "✅ GitHub main branch trust configured correctly"
else
  echo "❌ GitHub trust not found in policy"
  exit 1
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  ✅ OIDC TRUST POLICY FIXED                               ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "✅ GitHub Actions OIDC can now assume: $ROLE_NAME"
echo "✅ Trust scope: $GITHUB_ORG/$GITHUB_REPO main branch only"
echo ""
echo "Next steps:"
echo "1. Now GitHub Actions workflows will work with OIDC (no secrets needed)"
echo "2. Run: gh workflow run rotate-aws-credentials.yml --repo $GITHUB_ORG/$GITHUB_REPO"
echo "3. The rotation will succeed"
echo ""
