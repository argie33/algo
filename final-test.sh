#!/bin/bash
echo "FINAL COMPREHENSIVE SYSTEM TEST"
echo "========================================"
echo ""

endpoints=(
  "http://localhost:3001/api/health"
  "http://localhost:3001/api/stocks?limit=5"
  "http://localhost:3001/api/signals/stocks?timeframe=daily&limit=5"
  "http://localhost:3001/api/signals/stocks?timeframe=weekly&limit=5"
  "http://localhost:3001/api/signals/stocks?timeframe=monthly&limit=5"
  "http://localhost:3001/api/price/history/AAPL?timeframe=daily&limit=10"
  "http://localhost:3001/api/earnings/info?symbol=AAPL"
  "http://localhost:3001/api/financials/AAPL/income-statement?period=annual"
  "http://localhost:3001/api/sectors/sectors?limit=5"
  "http://localhost:3001/api/technicals?symbol=AAPL"
)

passed=0
failed=0

for endpoint in "${endpoints[@]}"; do
  code=$(curl -s -w "%{http_code}" -o /dev/null "$endpoint")
  name=$(echo "$endpoint" | sed 's|.*api/||' | cut -d'?' -f1 | head -c 40)
  if [ "$code" = "200" ]; then
    echo "✓ $name"
    ((passed++))
  else
    echo "✗ $name (HTTP $code)"
    ((failed++))
  fi
done

echo ""
echo "Results: $passed passed, $failed failed out of ${#endpoints[@]} total"
