#!/bin/bash

# Test all 11 dashboard API endpoints with dev-admin token
BASE_URL="http://localhost:3001"
TOKEN="dev-admin"

declare -a ENDPOINTS=(
    "/api/algo/status"
    "/api/algo/positions"
    "/api/algo/performance"
    "/api/algo/trades?limit=200"
    "/api/algo/markets"
    "/api/algo/equity-curve?limit=180"
    "/api/algo/circuit-breakers"
    "/api/algo/daily-return-histogram"
    "/api/algo/trade-distribution"
    "/api/algo/holding-period-distribution"
    "/api/algo/stage-distribution"
)

echo "Testing all dashboard API endpoints..."
echo ""

for endpoint in "${ENDPOINTS[@]}"; do
    echo "Testing: $endpoint"
    RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint" -H "Authorization: Bearer $TOKEN")
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | head -n-1)

    if [ "$HTTP_CODE" = "200" ]; then
        # Count items if it's an array response
        ITEM_COUNT=$(echo "$BODY" | python -c "import json, sys; data = json.load(sys.stdin); print(len(data.get('items', [])))" 2>/dev/null)
        if [ -z "$ITEM_COUNT" ]; then
            echo "  ✓ HTTP 200 (response received)"
        else
            echo "  ✓ HTTP 200 ($ITEM_COUNT items)"
        fi
    else
        echo "  ✗ HTTP $HTTP_CODE"
        echo "  Error: $(echo "$BODY" | python -c "import json, sys; print(json.load(sys.stdin).get('error', 'unknown'))" 2>/dev/null || echo $BODY)"
    fi
    echo ""
done

echo "Done."
