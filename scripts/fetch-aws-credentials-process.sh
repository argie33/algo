#!/bin/bash
# AWS credential_process script - fetches fresh credentials on-demand
# Used by ~/.aws/config to fetch credentials dynamically (no static files)
#
# Usage in ~/.aws/config:
# [algo-developer]
# credential_process = /path/to/fetch-aws-credentials-process.sh
#
# Then: aws s3 ls --profile algo-developer
# (credentials automatically fetched and cached by AWS SDK)

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="algo-developer"
REGION="us-east-1"

# Check if credentials are fresh (less than 50 minutes old)
CACHE_FILE="$HOME/.aws/.algo-creds-cache"
if [ -f "$CACHE_FILE" ]; then
    MTIME=$(stat -f%m "$CACHE_FILE" 2>/dev/null || stat -c%Y "$CACHE_FILE" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    AGE=$((NOW - MTIME))
    if [ $AGE -lt 3000 ]; then
        # Credentials still fresh, return from cache
        cat "$CACHE_FILE"
        exit 0
    fi
fi

# Credentials stale or missing - fetch fresh ones from GitHub Actions workflow
echo "Fetching fresh AWS credentials..." >&2

# Trigger the refresh workflow
REPO=$(cd "$REPO_ROOT" && git config --get remote.origin.url | sed 's/.*://;s/.git$//')
RUN_ID=$(gh workflow run refresh-dev-credentials.yml --repo "$REPO" 2>&1 | grep -oP 'workflow_id=\K[0-9]+' || echo "")

if [ -z "$RUN_ID" ]; then
    echo "ERROR: Could not trigger refresh workflow" >&2
    exit 1
fi

# Wait for workflow to complete (max 30 seconds)
for i in {1..30}; do
    STATUS=$(gh run view "$RUN_ID" --repo "$REPO" --json status --jq '.status' 2>/dev/null || echo "")
    if [ "$STATUS" = "completed" ]; then
        break
    fi
    sleep 1
done

# Download the credentials artifact
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

gh run download "$RUN_ID" --repo "$REPO" --name dev-credentials --dir "$TMPDIR" 2>/dev/null

if [ ! -f "$TMPDIR/credentials" ]; then
    echo "ERROR: Could not download credentials artifact" >&2
    exit 1
fi

# Parse and return in AWS credential_process format
ACCESS_KEY=$(grep aws_access_key_id "$TMPDIR/credentials" | awk '{print $3}')
SECRET_KEY=$(grep aws_secret_access_key "$TMPDIR/credentials" | awk '{print $3}')

if [ -z "$ACCESS_KEY" ] || [ -z "$SECRET_KEY" ]; then
    echo "ERROR: Could not parse credentials from artifact" >&2
    exit 1
fi

# Output in AWS credential_process JSON format
OUTPUT=$(cat <<EOF
{
  "Version": 1,
  "AccessKeyId": "$ACCESS_KEY",
  "SecretAccessKey": "$SECRET_KEY",
  "Expiration": "$(date -u -d '+59 minutes' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v+59M +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

# Cache the credentials
mkdir -p "$(dirname "$CACHE_FILE")"
echo "$OUTPUT" > "$CACHE_FILE"

# Return to AWS SDK
echo "$OUTPUT"
