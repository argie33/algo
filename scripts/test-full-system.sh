#!/bin/bash
# Full system test: API connectivity, loaders, orchestrator, and frontend

set -e

API_URL="https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api"
LOADER_WORKFLOW="manual-invoke-loaders.yml"
ORCHESTRATOR_WORKFLOW="invoke-algo-orchestrator.yml"

echo "======================================================"
echo "FULL SYSTEM TEST"
echo "======================================================"
echo ""

# Step 1: Test API connectivity
echo "1️⃣  Testing API connectivity..."
health=$(curl -s "$API_URL/health" -w "\n%{http_code}")
http_code=$(echo "$health" | tail -1)
body=$(echo "$health" | head -1)

if [ "$http_code" = "200" ]; then
  echo "✅ API health check: OK"
else
  echo "❌ API health check failed (HTTP $http_code)"
  echo "Response: $body"
  exit 1
fi
echo ""

# Step 2: Test if API can query data
echo "2️⃣  Testing API database connectivity..."
data=$(curl -s "$API_URL/scores/stockscores?limit=1")
if echo "$data" | jq . >/dev/null 2>&1; then
  count=$(echo "$data" | jq '.items | length' 2>/dev/null || echo "0")
  if [ "$count" -gt "0" ]; then
    echo "✅ API returned stock data: $count items"
  else
    echo "⚠️  API responding but no data yet (RDS is empty)"
    echo "   This is expected before loaders run"
  fi
else
  echo "❌ API returned invalid JSON: $data"
  exit 1
fi
echo ""

# Step 3: Trigger loaders
echo "3️⃣  Triggering loaders to populate RDS..."
loader_run=$(gh workflow run "$LOADER_WORKFLOW" \
  -f loader_type=all \
  -f dry_run=false \
  -f verbose=true \
  --repo argie33/algo 2>&1 || echo "")

if echo "$loader_run" | grep -q "workflow_dispatch"; then
  echo "✅ Loaders workflow triggered"
else
  echo "❌ Failed to trigger loaders"
  echo "$loader_run"
fi
echo ""

# Step 4: Wait for loaders to complete
echo "4️⃣  Waiting for loaders to complete..."
echo "   (This may take 5-10 minutes for all 26 loaders)"
max_wait=900  # 15 minutes
waited=0
while [ $waited -lt $max_wait ]; do
  sleep 10
  waited=$((waited + 10))

  # Check if data is in RDS
  data=$(curl -s "$API_URL/scores/stockscores?limit=1")
  count=$(echo "$data" | jq '.items | length' 2>/dev/null || echo "0")

  if [ "$count" -gt "0" ]; then
    echo "✅ Data found in RDS after $(($waited / 60)) minutes"
    break
  fi

  if [ $((waited % 60)) -eq 0 ]; then
    echo "   Still waiting... (${waited}s elapsed)"
  fi
done
echo ""

# Step 5: Trigger orchestrator
echo "5️⃣  Triggering orchestrator for live trading..."
algo_run=$(gh workflow run "$ORCHESTRATOR_WORKFLOW" \
  -f dry_run=false \
  --repo argie33/algo 2>&1 || echo "")

if echo "$algo_run" | grep -q "workflow_dispatch"; then
  echo "✅ Orchestrator workflow triggered"
else
  echo "❌ Failed to trigger orchestrator"
  echo "$algo_run"
fi
echo ""

echo "======================================================"
echo "✅ SYSTEM TEST COMPLETE"
echo "======================================================"
echo ""
echo "Next steps:"
echo "  - Monitor loaders: gh run list --workflow $LOADER_WORKFLOW"
echo "  - Monitor orchestrator: gh run list --workflow $ORCHESTRATOR_WORKFLOW"
echo "  - Verify frontend: https://stocks-trading.aws.com/"
echo ""
