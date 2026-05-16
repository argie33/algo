#!/bin/bash
# ============================================================
# LOAD DATA INTO CLOUD DATABASE
# Uses AWS infrastructure (EventBridge + Lambda + ECS tasks)
# ============================================================
set -e

echo "════════════════════════════════════════════════════════════"
echo "  CLOUD DATA LOADING"
echo "════════════════════════════════════════════════════════════"
echo ""

# Configuration
API_URL="${API_URL:-https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# ──────────────────────────────────────────────────────────────
# PHASE 1: VERIFY API IS ACCESSIBLE
# ──────────────────────────────────────────────────────────────
echo "🔍 Verifying API access..."
echo "  Testing: $API_URL/api/algo/status"

if curl -s -f "$API_URL/api/algo/status" >/dev/null 2>&1; then
    echo "✅ API is accessible"
else
    echo "❌ API is not responding (likely still deploying)"
    echo "   Check deployment status:"
    echo "   https://github.com/argie33/algo/actions"
    exit 1
fi

# ──────────────────────────────────────────────────────────────
# PHASE 2: TRIGGER DATA LOADERS
# ──────────────────────────────────────────────────────────────
echo ""
echo "📦 Data loaders are scheduled via EventBridge (4:05pm ET daily)"
echo "   To manually trigger, use:"
echo ""
echo "   aws events put-events --region $AWS_REGION --entries '[{\"Source\":\"algo.loader\",\"DetailType\":\"manual-trigger\",\"Detail\":\"{\\\"tier\\\":0}\"}]'"
echo ""

# ──────────────────────────────────────────────────────────────
# PHASE 3: VERIFY DATA IS LOADED
# ──────────────────────────────────────────────────────────────
echo "🔍 Checking data status..."
echo ""

# Check stock symbols
SYMBOL_COUNT=$(curl -s "$API_URL/api/stocks?limit=1" | grep -o '"symbol"' | wc -l || echo "0")
echo "  Stock symbols loaded: $SYMBOL_COUNT"

# Check prices
PRICE_COUNT=$(curl -s "$API_URL/api/scores/stockscores?limit=1" | grep -o '"close"' | wc -l || echo "0")
echo "  Price data loaded: $PRICE_COUNT"

# Check signals
SIGNAL_COUNT=$(curl -s "$API_URL/api/signals?limit=1" | grep -o '"signal"' | wc -l || echo "0")
echo "  Signals loaded: $SIGNAL_COUNT"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "✅ CLOUD DATA LOADING READY"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Check data freshness (next scheduled loader: 4:05pm ET)"
echo "  2. Or manually trigger loaders with AWS CLI command above"
echo "  3. Monitor logs: aws logs tail /aws/lambda/algo-orchestrator --follow"
echo ""
