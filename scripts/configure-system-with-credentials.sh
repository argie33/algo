#!/bin/bash
# Configure the system with Alpaca credentials from AWS Secrets Manager

set -e

echo "=== CONFIGURING SYSTEM WITH ALPACA CREDENTIALS ==="
echo ""

# Retrieve credentials from AWS
echo "[1/4] Retrieving Alpaca credentials from AWS Secrets Manager..."
CREDS=$(aws secretsmanager get-secret-value \
  --secret-id algo/alpaca \
  --region us-east-1 \
  --query SecretString \
  --output text)

API_KEY=$(echo "$CREDS" | jq -r .api_key)
API_SECRET=$(echo "$CREDS" | jq -r .api_secret)

if [ -z "$API_KEY" ] || [ -z "$API_SECRET" ]; then
  echo "[FAILED] Could not retrieve credentials from AWS"
  exit 1
fi

echo "[OK] Retrieved credentials from AWS"
echo "     Key: ${API_KEY:0:20}..."

# Set environment variables for current session
echo ""
echo "[2/4] Setting environment variables..."
export APCA_API_KEY_ID="$API_KEY"
export APCA_API_SECRET_KEY="$API_SECRET"
echo "[OK] Environment variables set"

# Validate credentials
echo ""
echo "[3/4] Validating credentials..."
python3 << 'PYTHON'
import sys
sys.path.insert(0, '.')
from config.credential_manager import CredentialManager
cm = CredentialManager()
try:
    creds = cm.get_alpaca_credentials()
    if creds and creds.get('key'):
        print(f"[OK] Credentials validated: {creds['key'][:20]}...")
    else:
        print("[FAILED] Credentials are empty")
        sys.exit(1)
except Exception as e:
    print(f"[FAILED] {e}")
    sys.exit(1)
PYTHON

# Ready for deployment
echo ""
echo "[4/4] System ready for deployment"
echo ""
echo "=== NEXT STEPS ==="
echo "1. Deploy to AWS: cd terraform && terraform apply"
echo "2. Verify: python scripts/validate-trading-setup.py"
echo "3. Monitor: python -m dashboard -w"
