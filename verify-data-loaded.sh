#!/bin/bash
# Verify data was loaded into AWS RDS via API

set -e

API_URL="https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"
MAX_ATTEMPTS=60
ATTEMPT=0

echo "════════════════════════════════════════════════════════════"
echo "  VERIFYING DATA LOADED INTO AWS"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "API Endpoint: $API_URL"
echo ""

# Wait for API to respond
echo "⏳ Waiting for API to respond..."
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -s -f "$API_URL/api/health" > /dev/null 2>&1; then
        echo "✅ API is responding"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    if [ $((ATTEMPT % 10)) -eq 0 ]; then
        echo "   Still waiting... (${ATTEMPT}0s elapsed)"
    fi
    sleep 1
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "❌ API not responding after $((MAX_ATTEMPTS))s"
    exit 1
fi

echo ""
echo "📊 Checking data load status..."
echo ""

# Check stock symbols
echo -n "  Stock Symbols: "
SYMBOL_COUNT=$(curl -s "$API_URL/api/stocks?limit=1" 2>/dev/null | grep -o '"symbol"' | wc -l || echo "0")
if [ "$SYMBOL_COUNT" -gt 0 ]; then
    echo "✅ Data loaded"
else
    echo "⏳ Not loaded yet"
fi

# Check if we can get stock data
echo -n "  Stock Data: "
STOCK_DATA=$(curl -s "$API_URL/api/stocks?limit=1" 2>/dev/null || echo "{}")
if echo "$STOCK_DATA" | grep -q "symbol"; then
    echo "✅ Accessible"
else
    echo "⏳ Not loaded yet"
fi

# Check prices
echo -n "  Price History: "
PRICE_DATA=$(curl -s "$API_URL/api/scores/stockscores?limit=1" 2>/dev/null || echo "{}")
if echo "$PRICE_DATA" | grep -q "close"; then
    echo "✅ Loaded"
else
    echo "⏳ Not loaded yet"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo ""

# Get more details
echo "Sample data from API:"
curl -s "$API_URL/api/stocks?limit=1" 2>/dev/null | jq '.' 2>/dev/null || echo "(Could not parse data)"

echo ""
echo "✅ Verification complete"
echo ""
echo "Next steps:"
echo "  1. If data is loaded: Run orchestrator to test algo"
echo "  2. Check CloudWatch logs for execution details"
echo "  3. Monitor: aws logs tail /ecs/algo-algo-orchestrator --follow --region us-east-1"
