#!/bin/bash
# ============================================================
# Sync Local Secrets Vault to GitHub Actions
# ============================================================
# Usage: ./scripts/sync-secrets.sh
# This script reads .env.vault and pushes secrets to GitHub

set -e

REPO="argie33/algo"
VAULT_FILE=".env.vault"

if [ ! -f "$VAULT_FILE" ]; then
  echo "❌ Error: $VAULT_FILE not found"
  echo "Create it from template: cp .env.vault.template .env.vault"
  exit 1
fi

echo "🔐 Syncing secrets to GitHub repository..."
echo "   Repository: $REPO"
echo ""

# List of all secret names
SECRETS=(
  "AWS_ACCESS_KEY_ID"
  "AWS_SECRET_ACCESS_KEY"
  "AWS_ACCOUNT_ID"
  "RDS_PASSWORD"
  "ALPACA_API_KEY_ID"
  "ALPACA_API_SECRET_KEY"
  "ALERT_EMAIL_ADDRESS"
  "API_GATEWAY_URL"
)

# Parse .env.vault and push each secret
while IFS='=' read -r KEY VALUE; do
  # Skip comments and empty lines
  [[ "$KEY" =~ ^[[:space:]]*# ]] && continue
  [ -z "$KEY" ] && continue
  [ -z "$VALUE" ] && continue

  # Trim whitespace
  KEY=$(echo "$KEY" | xargs)
  VALUE=$(echo "$VALUE" | xargs)

  # Only process known secrets
  if [[ " ${SECRETS[@]} " =~ " ${KEY} " ]]; then
    if [ -z "$VALUE" ]; then
      echo "⚠️  Skipping $KEY (empty value)"
    else
      echo "📝 Pushing $KEY..."
      gh secret set "$KEY" --body "$VALUE" --repo "$REPO" 2>/dev/null && echo "   ✅ $KEY set" || echo "   ⚠️  $KEY may already exist"
    fi
  fi
done < "$VAULT_FILE"

echo ""
echo "✅ Secrets sync complete!"
echo ""
echo "Verify in GitHub: https://github.com/$REPO/settings/secrets/actions"
