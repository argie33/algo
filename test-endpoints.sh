#!/bin/bash
echo "Testing critical endpoints..."

test_endpoint() {
  local url=$1
  local name=$2
  echo -n "$name ... "
  code=$(curl -s -w "%{http_code}" -o /tmp/test-response.json "$url" 2>&1)
  if [ "$code" = "200" ]; then
    count=$(jq '.items | length // .data | length // 0' /tmp/test-response.json 2>/dev/null || echo "?")
    echo "✅ ($count items)"
  else
    echo "❌ (HTTP $code)"
    head -c 200 /tmp/test-response.json
    echo ""
  fi
}

test_endpoint "http://localhost:3001/api/stocks?limit=5" "Stocks"
test_endpoint "http://localhost:3001/api/signals/stocks?timeframe=daily&limit=2" "Signals"
test_endpoint "http://localhost:3001/api/price/history/AAPL?timeframe=daily&limit=5" "Price history"
test_endpoint "http://localhost:3001/api/earnings/info?symbol=AAPL" "Earnings"
test_endpoint "http://localhost:3001/api/financials/AAPL/balance-sheet?period=annual" "Financials"
test_endpoint "http://localhost:3001/api/market/data" "Market data"
test_endpoint "http://localhost:3001/api/sectors/sectors" "Sectors"
test_endpoint "http://localhost:3001/api/technicals?symbol=AAPL&timeframe=daily" "Technicals"

