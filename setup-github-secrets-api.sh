#!/bin/bash
set -e

# This script adds GitHub secrets via the REST API
# Requires: GITHUB_TOKEN environment variable with repo scope

if [ -z "$GITHUB_TOKEN" ]; then
    echo "ERROR: GITHUB_TOKEN not set"
    echo "Set it with: export GITHUB_TOKEN='your_token_here'"
    echo ""
    echo "To create a token:"
    echo "1. Go to https://github.com/settings/tokens"
    echo "2. Create new token with 'repo' scope"
    echo "3. export GITHUB_TOKEN='ghp_...'"
    exit 1
fi

REPO="argie33/algo"
BASE_URL="https://api.github.com/repos/$REPO/actions/secrets"

echo "=========================================="
echo "ADDING GITHUB SECRETS"
echo "=========================================="
echo ""

# Function to add a secret
add_secret() {
    local NAME=$1
    local VALUE=$2
    
    echo -n "Adding $NAME... "
    
    # Encode the secret value in base64
    ENCODED=$(echo -n "$VALUE" | base64 -w0)
    
    # Get the public key
    PUBLIC_KEY=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
        "$BASE_URL/public-key" | grep -o '"key":"[^"]*' | cut -d'"' -f4)
    
    KEY_ID=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
        "$BASE_URL/public-key" | grep -o '"key_id":"[^"]*' | cut -d'"' -f4)
    
    # Create JSON payload
    PAYLOAD=$(cat <<EOF
{
  "encrypted_value": "$ENCODED",
  "key_id": "$KEY_ID"
}
EOF
)
    
    # Add the secret
    RESPONSE=$(curl -s -X PUT -H "Authorization: token $GITHUB_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        "$BASE_URL/$NAME")
    
    if echo "$RESPONSE" | grep -q "error"; then
        echo "FAILED"
        echo "$RESPONSE"
    else
        echo "✓"
    fi
}

# Add all 4 secrets
add_secret "AWS_ACCOUNT_ID" "626216981288"
add_secret "RDS_USERNAME" "stocks"
add_secret "RDS_PASSWORD" "bed0elAn"
add_secret "FRED_API_KEY" "4f87c213871ed1a9508c06957fa9b577"

echo ""
echo "=========================================="
echo "SECRETS ADDED"
echo "=========================================="
echo ""

